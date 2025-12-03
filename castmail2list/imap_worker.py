"""IMAP worker for CastMail2List"""

import logging
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

from flask import Flask
from flufl.bounce import scan_message
from imap_tools import MailBox, MailboxLoginError
from imap_tools.message import MailMessage
from sqlalchemy.exc import IntegrityError

from .mailer import send_msg_to_subscribers
from .models import EmailIn, MailingList, Subscriber, db
from .utils import (
    get_all_messages_id_from_raw_email,
    get_list_subscribers,
    get_message_id_from_incoming,
    get_message_id_in_db,
    get_plus_suffix,
    is_expanded_address_the_mailing_list,
    parse_bounce_address,
    remove_plus_suffix,
    run_only_once,
)

REQUIRED_FOLDERS_ENVS = [
    "IMAP_FOLDER_INBOX",
    "IMAP_FOLDER_PROCESSED",
    "IMAP_FOLDER_BOUNCES",
    "IMAP_FOLDER_DENIED",
    "IMAP_FOLDER_DUPLICATE",
]


def _poll_imap(app):
    """Runs forever in a thread, polling once per minute."""
    with app.app_context():
        while run_only_once(app):
            try:
                check_all_lists_for_messages(app)
            except Exception as e:  # pylint: disable=broad-except
                logging.error("IMAP worker error: %s\nTraceback: %s", e, traceback.format_exc())
            time.sleep(app.config["POLL_INTERVAL_SECONDS"])


def initialize_imap_polling(app: Flask):
    """Start IMAP polling thread if not in testing mode"""
    if not app.config.get("TESTING", True):
        logging.info("Starting IMAP polling thread...")
        t = threading.Thread(target=_poll_imap, args=(app,), daemon=True)
        t.start()


def create_required_folders(app: Flask, mailbox: MailBox) -> None:
    """Create required IMAP folders if they don't exist."""
    for folder in [app.config[env] for env in REQUIRED_FOLDERS_ENVS]:
        if not mailbox.folder.exists(folder):
            mailbox.folder.create(folder=folder)
            logging.info("Created IMAP folder: %s", folder)


class IncomingEmail:  # pylint: disable=too-few-public-methods
    """Class representing an incoming message and its handling"""

    def __init__(self, app: Flask, mailbox: MailBox, msg: MailMessage, ml: MailingList) -> None:
        self.app: Flask = app
        self.mailbox: MailBox = mailbox
        self.msg: MailMessage = msg
        self.ml: MailingList = ml

    def _detect_bounce(self) -> tuple[str, list[str]]:
        """Detect whether the message is a bounce message. This is detected by two methods:
        1. If the To address contains "+bounces--"
        2. If the message is detected as a bounce by flufl.bounce

        Returns:
            tuple: A Tuple containing
                - (str) Original recipient email address(es) if bounce detected, else empty string
                - (list) The possible Message IDs that caused the bounce, else empty list
        """
        bounced_recipient: str = ""
        # Check To addresses for bounce marker
        for to in self.msg.to:
            if recipient := parse_bounce_address(to):
                logging.debug(
                    "Bounce detected by parse_bounce_address() for message %s, recipient: %s",
                    self.msg.uid,
                    recipient,
                )
                bounced_recipient = recipient

        # Use flufl.bounce to scan message
        bounced_recipients_flufl: set[bytes] = scan_message(self.msg.obj)  # type: ignore
        if bounced_recipients_flufl:
            logging.debug(
                "Bounce detected by flufl.bounce.scan_message() for message %s, recipients: %s",
                self.msg.uid,
                bounced_recipients_flufl,
            )
            bounced_recipient = ", ".join(addr.decode("utf-8") for addr in bounced_recipients_flufl)

        if bounced_recipient:
            # Return the Message-ID of the original message that bounced, if available
            return bounced_recipient, get_all_messages_id_from_raw_email(str(self.msg.obj))

        return "", []

    def _validate_email_sender_authentication(self) -> str:
        """
        Validate sender authentication for a broadcast mailing list, if a sender authentication
        password is configured. The password is expected to be provided as a +suffix in the To
        address.

        Returns:
            str: The successful To address if authentication passed, else empty string
        """
        sender_email = self.msg.from_values.email if self.msg.from_values else ""

        # Iterate over all To addresses to find the string that matches the list address
        for to_addr in self.msg.to:
            if is_expanded_address_the_mailing_list(to_addr, self.ml.address):
                plus_suffix = get_plus_suffix(to_addr)
                if plus_suffix in self.ml.sender_auth:
                    logging.debug(
                        "Sender <%s> provided valid authentication password for list <%s>",
                        sender_email,
                        self.ml.address,
                    )
                    return to_addr
        return ""

    def _remove_password_in_to_address(self, old_to: str, new_to: str) -> None:
        """
        Replace the To address in the MailMessage object.

        Args:
            old_to (str): The old To address to be replaced
            new_to (str): The new To address to set
        """
        # Replace in msg.to
        to_addresses = list(self.msg.to)
        to_addresses = [new_to if old_to else to for to in to_addresses]
        self.msg.to = tuple(to_addresses)

        # Replace in msg.to_values
        to_value_addresses = list(self.msg.to_values)
        for to in to_value_addresses:
            if to.email == old_to:
                to.email = new_to
        self.msg.to_values = tuple(to_value_addresses)

    def _validate_email_all_checks(self) -> tuple[str, dict[str, str | list]]:
        """
        Check a new single IMAP message from the Inbox:
            * Bounce detection
            * Allowed sender (broadcast mode)
            * Sender authentication (broadcast mode)
            * Subscriber check (group mode)

        Returns:
            tuple (str, dict): Status of the message processing and error information
        """
        logging.debug("Processing message: %s", self.msg.subject)
        status = "ok"
        error_info: dict[str, str | list] = {}

        # --- Bounced message detection ---
        bounced_recipients, bounced_mids = self._detect_bounce()
        if bounced_recipients:
            if _causing_msg := get_message_id_in_db(bounced_mids, only="out"):
                causing_mid = _causing_msg.message_id
            else:
                causing_mid = "unknown"
            logging.info(
                "Message %s is a bounce for recipients: %s", self.msg.uid, bounced_recipients
            )
            status = "bounce-msg"
            error_info = {"bounced_recipients": bounced_recipients, "bounced_mid": causing_mid}
            return status, error_info

        # --- Sender not allowed checks ---
        # In broadcast mode, ensure the original sender of the message is in the allowed senders
        # list
        if self.ml.mode == "broadcast" and self.ml.allowed_senders:
            if (
                not self.msg.from_values
                or self.msg.from_values.email not in self.ml.allowed_senders
            ):
                logging.warning(
                    "Sender <%s> not in allowed senders for list <%s>, skipping message %s",
                    self.msg.from_values.email if self.msg.from_values else "unknown",
                    self.ml.address,
                    self.msg.uid,
                )
                status = "sender-not-allowed"
                return status, error_info

        # In broadcast mode, check sender authentication if configured
        # The password is provided via a +password suffix in the To address of the mailing list
        if self.ml.mode == "broadcast" and self.ml.sender_auth:
            if passed_to_address := self._validate_email_sender_authentication():
                # Remove the +password suffix from the To address so subscribers don't see it
                self._remove_password_in_to_address(
                    old_to=passed_to_address, new_to=remove_plus_suffix(passed_to_address)
                )
            else:
                logging.warning(
                    "Sender failed authentication for list <%s>, skipping message %s",
                    self.ml.address,
                    self.msg.uid,
                )
                status = "sender-auth-failed"
                return status, error_info

        # In group mode, ensure the original sender is one of the subscribers
        subscribers: list[Subscriber] = get_list_subscribers(self.ml)
        if self.ml.mode == "group" and self.ml.only_subscribers_send and subscribers:
            subscriber_emails = [sub.email for sub in subscribers]
            if not self.msg.from_values or self.msg.from_values.email not in subscriber_emails:
                logging.error(
                    "Sender %s not a subscriber of list %s, skipping message %s",
                    self.msg.from_values.email if self.msg.from_values else "unknown",
                    self.ml.name,
                    self.msg.uid,
                )
                status = "sender-not-allowed"
                return status, error_info

        # --- Email is actually a message by this CastMail2List instance itself (duplicate) ---
        # Get X-CastMail2List-Domain header
        x_domain_headers = self.msg.headers.get("x-castmail2list-domain", "")
        if self.app.config["DOMAIN"] in x_domain_headers:
            logging.warning(
                "Message %s is from this CastMail2List instance itself "
                "(X-CastMail2List-Domain: %s), skipping",
                self.msg.uid,
                x_domain_headers,
            )
            status = "duplicate-from-same-instance"
            return status, error_info

        # --- Fallback return: all seems to be OK ---
        return status, error_info

    def _store_msg_in_db_and_imap(
        self,
        status: str,
        error_info: dict | None = None,
    ) -> bool:
        """Store a message in the database and move it to the appropriate folder based on status.

        Args:
            status (str): Status of the message.
            error_info (dict | None): Optional error diagnostic information to store,
                e.g. about bounce

        Returns:
            bool: True if message was new and stored, False if it was a duplicate
        """
        if status == "ok":
            target_folder = self.app.config["IMAP_FOLDER_PROCESSED"]
        elif status == "bounce-msg":
            target_folder = self.app.config["IMAP_FOLDER_BOUNCES"]
        elif status == "duplicate":
            target_folder = self.app.config["IMAP_FOLDER_DUPLICATE"]
        else:
            target_folder = self.app.config["IMAP_FOLDER_DENIED"]

        # Store message in database
        m = EmailIn()
        m.list_id = self.ml.id
        m.message_id = get_message_id_from_incoming(self.msg)
        m.subject = self.msg.subject
        m.from_addr = self.msg.from_
        m.headers = str(dict(self.msg.headers.items()))
        m.raw = str(self.msg.obj)  # Get raw RFC822 message
        m.received_at = datetime.now(timezone.utc)
        m.status = status
        m.error_info = error_info or {}
        if self.app.config.get("DRY", False):
            logging.info(
                "[DRY MODE] Would store message uid %s in DB: %s", self.msg.uid, m.__dict__
            )
            return True
        db.session.add(m)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            logging.warning(
                "Message %s already processed (Message-ID %s exists in DB), skipping",
                self.msg.uid,
                m.message_id,
            )
            target_folder = self.app.config["IMAP_FOLDER_DUPLICATE"]

        # Mark message as seen and move to target folder
        self.mailbox.flag(uid_list=self.msg.uid, flag_set=["\\Seen"], value=True)  # type: ignore
        self.mailbox.move(uid_list=self.msg.uid, destination_folder=target_folder)  # type: ignore
        logging.debug(
            "Marked message %s as seen and moved to folder '%s'", self.msg.uid, target_folder
        )

        return target_folder != self.app.config["IMAP_FOLDER_DUPLICATE"]

    def process_incoming_msg(self) -> bool:
        """
        Handle the incoming mail: validate, store in DB, and move in IMAP. If the message is valid
        and no duplicate, send to subscribers.

        Returns:
            bool: True if message is OK and can be sent to subscribers, False otherwise
        """
        # Check for bounces, allowed senders, sender auth, and subscribers
        status, error_info = self._validate_email_all_checks()

        # Store message in DB and IMAP, return whether it was new (not duplicate)
        no_duplicate = self._store_msg_in_db_and_imap(
            status=status,
            error_info=error_info,
        )

        # If status is not "ok" or message is duplicate, signal to skip sending
        if status != "ok" or not no_duplicate:
            return False

        # Message OK, can be sent to all subscribers of the list
        return True


def check_all_lists_for_messages(app: Flask) -> None:
    """
    Check IMAP for new messages for all lists, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    run_id = uuid.uuid4().hex[:8]
    logging.debug("Checking all lists for new messages in run (%s)", run_id)

    # Iterate over all configured lists
    maillists: list[MailingList] = MailingList.query.filter_by(deleted=False).all()
    for ml in maillists:
        logging.info("Polling '%s' (%s) (%s)", ml.name, ml.address, run_id)
        try:
            with MailBox(host=ml.imap_host, port=int(ml.imap_port)).login(
                username=ml.imap_user, password=ml.imap_pass
            ) as mailbox:
                # Create required folders
                create_required_folders(app, mailbox)

                # --- INBOX processing ---
                mailbox.folder.set(app.config["IMAP_FOLDER_INBOX"])
                # Fetch unseen messages
                for msg in mailbox.fetch(mark_seen=False):
                    incoming_msg = IncomingEmail(app, mailbox, msg, ml)
                    # Check if incoming message has a UID. If not, we abort the process as this
                    # would break multiple operations
                    if msg.uid is None:
                        logging.error(
                            "Incoming message has no UID, cannot process message: %s", msg.subject
                        )
                        continue
                    # Process incoming message. If OK, send to subscribers
                    if incoming_msg.process_incoming_msg():
                        send_msg_to_subscribers(app=app, msg=msg, ml=ml, mailbox=mailbox)
                    else:
                        logging.debug(
                            "Message %s not sent to subscribers due to errors or duplication "
                            "during processing",
                            msg.uid,
                        )
                        return
        except MailboxLoginError as e:
            logging.error(
                "IMAP login failed for list %s (%s): %s",
                ml.name,
                ml.address,
                str(e),
            )
        except Exception as e:  # pylint: disable=broad-except
            logging.error(
                "Error processing list %s: %s\nTraceback: %s", ml.name, e, traceback.format_exc()
            )

    logging.debug("Finished checking for new messages")
