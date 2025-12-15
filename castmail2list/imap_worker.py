"""IMAP worker for CastMail2List"""

import logging
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from email.utils import make_msgid

from flask import Flask
from flask_babel import gettext as _
from flufl.bounce import scan_message
from imap_tools import MailBox, MailboxLoginError
from imap_tools.message import MailMessage

from .mailer import send_msg_to_subscribers, send_rejection_notification
from .models import EmailIn, MailingList, Subscriber, db
from .utils import (
    create_log_entry,
    get_all_messages_id_from_raw_email,
    get_list_recipients_recursive,
    get_message_id_from_incoming,
    get_message_id_in_db,
    get_plus_suffix,
    is_email_a_list,
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

    def _validate_email_sender_authentication(self) -> bool:
        """
        Validate sender authentication for a mailing list, if a sender authentication password is
        configured. The password is expected to be provided as a +suffix in the To address.

        Notes:
        * the password is case-sensitive.
        * the +suffix is not removed from the To address here; that is done separately

        Returns:
            bool: True if authentication passed, else False
        """
        sender_email = self.msg.from_values.email if self.msg.from_values else ""

        # Iterate over all To addresses to find the string that matches the list address
        for to_addr in self.msg.to:
            if is_expanded_address_the_mailing_list(to_addr, self.ml.address):
                plus_suffix = get_plus_suffix(to_addr)
                if plus_suffix and plus_suffix in self.ml.sender_auth:
                    logging.debug(
                        "Sender <%s> provided valid authentication password for list <%s>: %s",
                        sender_email,
                        self.ml.address,
                        plus_suffix,
                    )
                    return True
        return False

    def _remove_suffixes_in_to_addresses(self) -> None:
        """
        Replace any +suffix in any To address which corresponds to a known email list, to avoid
        leaking authentication passwords to subscribers.

        Edits self.msg.to and self.msg.to_values in place.
        """
        # Replace in msg.to
        to_addresses = list(self.msg.to)
        to_addresses = [
            remove_plus_suffix(to) if is_email_a_list(to) else to for to in to_addresses
        ]
        self.msg.to = tuple(to_addresses)

        # Replace in msg.to_values
        to_value_addresses = list(self.msg.to_values)
        for to_value in to_value_addresses:
            if is_email_a_list(to_value.email):
                to_value.email = remove_plus_suffix(to_value.email)
        self.msg.to_values = tuple(to_value_addresses)

    def _check_broadcast_sender_authorization(self) -> bool:
        """
        Check if sender is authorized in broadcast mode.

        In broadcast mode, sender must either be in allowed_senders OR provide valid sender_auth.
        If neither is configured, any sender is allowed.

        Returns:
            bool: True if sender is authorized, False otherwise
        """
        # Avoid NoneType error, but handled before already
        if self.msg.from_values is None:
            return False

        # Check if any restrictions are configured
        if not (self.ml.allowed_senders or self.ml.sender_auth):
            # No restrictions configured, allow all senders
            return True

        sender_allowed = False  # Initialize as not allowed

        # Check if sender is in allowed_senders list
        if (
            self.ml.allowed_senders
            and self.msg.from_values.email.lower() in self.ml.allowed_senders
        ):
            sender_allowed = True
            logging.debug(
                "Sender <%s> is in allowed senders for list <%s>",
                self.msg.from_values.email,
                self.ml.address,
            )

        # Check if sender provided valid authentication password
        elif self.ml.sender_auth and self._validate_email_sender_authentication():
            sender_allowed = True

        # Log rejection if sender is not allowed
        if not sender_allowed:
            logging.warning(
                "Sender <%s> not authorized for broadcast list <%s>, skipping message %s",
                self.msg.from_values.email,
                self.ml.address,
                self.msg.uid,
            )

        return sender_allowed

    def _check_group_sender_authorization(self) -> bool:
        """
        Check if sender is authorized in group mode.

        In group mode with only_subscribers_send enabled, sender must be a subscriber OR
        in allowed_senders OR provide valid sender_auth.

        Returns:
            bool: True if sender is authorized, False otherwise
        """
        # Avoid NoneType error, but handled before already
        if self.msg.from_values is None:
            return False

        # Check if any restrictions are configured
        if not self.ml.only_subscribers_send:
            # No restrictions
            return True

        # Get list of subscriber emails
        subscriber_emails: list[str] = list(get_list_recipients_recursive(self.ml.id).keys())
        # No subscribers configured, allow all
        if not subscriber_emails:
            return True

        sender_allowed = False  # Initialize as not allowed

        # Sender is a subscriber
        if self.msg.from_values.email.lower() in subscriber_emails:
            sender_allowed = True
            logging.debug(
                "Sender <%s> is a subscriber of list <%s>",
                self.msg.from_values.email,
                self.ml.address,
            )

        # Allow sender if in Allowed Senders
        elif (
            self.ml.allowed_senders
            and self.msg.from_values.email.lower() in self.ml.allowed_senders
        ):
            sender_allowed = True
            logging.debug(
                "Sender <%s> is not a subscriber, but in allowed senders for list <%s>",
                self.msg.from_values.email,
                self.ml.address,
            )

        # Bypass check if sender provided valid sender authentication password
        elif self.ml.sender_auth and self._validate_email_sender_authentication():
            sender_allowed = True
            logging.debug(
                "Sender <%s> is not a subscriber but provided valid authentication password "
                "for list <%s>",
                self.msg.from_values.email,
                self.ml.address,
            )

        # Log rejection if sender is not allowed
        if not sender_allowed:
            logging.warning(
                "Sender %s not a subscriber of list %s and did not authenticate otherwise, "
                "skipping message %s",
                self.msg.from_values.email,
                self.ml.display,
                self.msg.uid,
            )

        return sender_allowed

    def _check_duplicate_from_self(self) -> bool:
        """
        Check if message is from this CastMail2List instance itself.

        Returns:
            bool: True if message is from same instance (duplicate), False otherwise
        """
        x_domain_headers = self.msg.headers.get("x-castmail2list-domain", "")
        if self.app.config["DOMAIN"] in x_domain_headers:
            logging.warning(
                "Message %s is from this CastMail2List instance itself "
                "(X-CastMail2List-Domain: %s), skipping",
                self.msg.uid,
                x_domain_headers,
            )
            return True
        return False

    def _validate_email_all_checks(self) -> tuple[str, dict[str, str | list]]:
        """
        Check a new single IMAP message from the Inbox:
            * Empty from address
            * Bounce detection
            * Allowed sender (both modes: required in broadcast, bypass in group)
            * Sender authentication (both modes: required in broadcast, bypass in group)
            * Subscriber check (group mode)

        Returns:
            tuple (str, dict): Status of the message processing and error information
        """
        logging.debug("Processing message: %s", self.msg.subject)
        status = "ok"
        error_info: dict[str, str | list] = {}

        # --- Empty From header ---
        if not self.msg.from_values or not self.msg.from_values.email:
            logging.error("Message %s has empty From address, skipping", self.msg.uid)
            status = "no-from-header"
            return status, error_info

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

            # Increment bounce count for affected subscriber(s)
            subscriber: Subscriber | None = Subscriber.query.filter_by(
                list_id=self.ml.id, email=bounced_recipients.lower().strip()
            ).first()
            if subscriber and isinstance(subscriber, Subscriber):
                subscriber.increase_bounce()

            return status, error_info

        # --- Sender authorization (mode-specific) ---
        if self.ml.mode == "broadcast":
            if not self._check_broadcast_sender_authorization():
                status = "sender-not-allowed"
                reason = _(
                    "This is a broadcast list. Only authorized senders can send messages to "
                    "%(address)s.",
                    address=self.ml.address,
                )
                # Send rejection notification
                send_rejection_notification(
                    app=self.app,
                    sender_email=self.msg.from_values.email,
                    recipient=self.ml.address,
                    reason=reason,
                    in_reply_to=get_message_id_from_incoming(self.msg),
                )
                # Log rejection event
                create_log_entry(
                    level="warning",
                    event="email_in",
                    message=(
                        f"Rejection of {self.msg.from_values.email} "
                        f"for message to {self.ml.address}"
                    ),
                    details={
                        "status": status,
                        "reason": reason,
                        "in-reply-to": get_message_id_from_incoming(self.msg),
                    },
                    list_id=self.ml.id,
                )
                return status, error_info
        elif self.ml.mode == "group":
            if not self._check_group_sender_authorization():
                status = "sender-not-allowed"
                reason = _(
                    "This is a group list that only accepts messages from subscribers of "
                    "%(address)s.",
                    address=self.ml.address,
                )
                # Send rejection notification
                send_rejection_notification(
                    app=self.app,
                    sender_email=self.msg.from_values.email,
                    recipient=self.ml.address,
                    reason=reason,
                    in_reply_to=get_message_id_from_incoming(self.msg),
                )
                # Log rejection event
                create_log_entry(
                    level="warning",
                    event="email_in",
                    message=(
                        f"Rejection of {self.msg.from_values.email} "
                        f"for message to {self.ml.address}"
                    ),
                    details={
                        "status": status,
                        "reason": reason,
                        "in-reply-to": get_message_id_from_incoming(self.msg),
                    },
                    list_id=self.ml.id,
                )
                return status, error_info

        # --- Email is actually a message by this CastMail2List instance itself (duplicate) ---
        if self._check_duplicate_from_self():
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
        # Check if message already exists in database to avoid identity conflicts
        message_id = get_message_id_from_incoming(self.msg)
        existing = db.session.get(EmailIn, message_id)

        if existing:
            # Message is a duplicate. Log, set a random Message-ID to avoid conflicts, save in DB
            # with status "duplicate" (which moves it to the duplicate folder later)
            logging.warning(
                "Message %s already processed (Message-ID %s exists in DB), skipping",
                self.msg.uid,
                message_id,
            )
            create_log_entry(
                level="warning",
                event="email_in",
                message=(f"Duplicate message detected to {self.ml.address}"),
                details={
                    "status": "duplicate",
                    "original-message-id": message_id,
                    "sender": self.msg.from_values.email if self.msg.from_values else "",
                },
                list_id=self.ml.id,
            )
            # Set new random Message-ID to avoid DB conflicts
            message_id = "duplicate-" + make_msgid(domain=self.app.config["DOMAIN"]).strip("<>")
            status = "duplicate"

        # Store new message in database
        m = EmailIn()
        m.list_id = self.ml.id
        m.message_id = message_id
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
        db.session.commit()

        # Mark message as seen
        self.mailbox.flag(uid_list=self.msg.uid, flag_set=["\\Seen"], value=True)  # type: ignore

        # Move message to appropriate folder based on status
        if status == "ok":
            target_folder = self.app.config["IMAP_FOLDER_PROCESSED"]
        elif status == "bounce-msg":
            target_folder = self.app.config["IMAP_FOLDER_BOUNCES"]
        elif status == "duplicate":
            target_folder = self.app.config["IMAP_FOLDER_DUPLICATE"]
        else:
            target_folder = self.app.config["IMAP_FOLDER_DENIED"]
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

        # Remove all plus suffixes from To addresses to avoid leaking passwords to subscribers
        self._remove_suffixes_in_to_addresses()

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
        logging.info("Polling '%s' (%s) (%s)", ml.display, ml.address, run_id)
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
                ml.display,
                ml.address,
                str(e),
            )
        except Exception as e:  # pylint: disable=broad-except
            logging.error(
                "Error processing list %s: %s\nTraceback: %s", ml.display, e, traceback.format_exc()
            )

    logging.debug("Finished checking for new messages")
