"""IMAP worker for CastMail2List"""

import logging
import os
import time
import traceback
import uuid

from flask import Flask
from flufl.bounce import scan_message
from imap_tools import MailBox
from imap_tools.message import MailMessage
from sqlalchemy.exc import IntegrityError

from .mailer import send_msg_to_subscribers
from .models import List, Message, Subscriber, db
from .utils import (
    get_list_subscribers,
    get_plus_suffix,
    is_expanded_address_the_mailing_list,
    json_array_to_list,
    parse_bounce_address,
)

REQUIRED_FOLDERS_ENVS = [
    "IMAP_FOLDER_INBOX",
    "IMAP_FOLDER_PROCESSED",
    "IMAP_FOLDER_BOUNCES",
    "IMAP_FOLDER_DENIED",
    "IMAP_FOLDER_DUPLICATE",
]


def run_only_once(app):
    """Ensure that something is only run once if Flask is run in Debug mode. Check if Flask is run
    in Debug mode and what the value of env variable WERKZEUG_RUN_MAIN is"""
    logging.debug("FLASK_DEBUG=%s, WERKZEUG_RUN_MAIN=%s", app.debug, os.getenv("WERKZEUG_RUN_MAIN"))

    if not app.debug:
        return True
    if app.debug and os.getenv("WERKZEUG_RUN_MAIN") == "true":
        return True
    return False


def poll_imap(app):
    """Runs forever in a thread, polling once per minute."""
    with app.app_context():
        while run_only_once(app):
            try:
                check_all_lists_for_messages(app)
            except Exception as e:  # pylint: disable=broad-except
                logging.error("IMAP worker error: %s\nTraceback: %s", e, traceback.format_exc())
            time.sleep(app.config["POLL_INTERVAL_SECONDS"])


def create_required_folders(app: Flask, mailbox: MailBox) -> None:
    """Create required IMAP folders if they don't exist."""
    for folder in [app.config[env] for env in REQUIRED_FOLDERS_ENVS]:
        if not mailbox.folder.exists(folder):
            mailbox.folder.create(folder=folder)
            logging.info("Created IMAP folder: %s", folder)


def store_msg_in_db_and_imap(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    app: Flask,
    ml: List,
    mailbox: MailBox,
    msg: MailMessage,
    status: str,
    error_info: dict | None = None,
) -> bool:
    """Store a message in the database and move it to the appropriate folder based on status.

    Args:
        app (Flask): Flask app context
        msg (MailMessage): IMAP message to store
        mailbox (MailBox): IMAP mailbox to operate on
        ml (List): Mailing list the message belongs to
        status (str): Status of the message.
        error_info (dict | None): Optional error diagnostic information to store, e.g. about bounce

    Returns:
        bool: True if message was new and stored, False if it was a duplicate
    """
    if status == "ok":
        target_folder = app.config["IMAP_FOLDER_PROCESSED"]
    elif status == "bounce-msg":
        target_folder = app.config["IMAP_FOLDER_BOUNCES"]
    elif status == "duplicate":
        target_folder = app.config["IMAP_FOLDER_DUPLICATE"]
    else:
        target_folder = app.config["IMAP_FOLDER_DENIED"]

    # Store message in database
    m = Message()
    m.list_id = ml.id
    m.message_id = next(iter(msg.headers.get("message-id", ())), str(uuid.uuid4())).strip("<>")
    m.subject = msg.subject
    m.from_addr = msg.from_
    m.headers = str(dict(msg.headers.items()))
    m.raw = str(msg.obj)  # Get raw RFC822 message
    m.status = status
    m.error_info = error_info or {}
    db.session.add(m)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logging.warning(
            "Message %s already processed (Message-ID %s exists in DB), skipping",
            msg.uid,
            m.message_id,
        )
        target_folder = "duplicate"

    # Mark message as seen and move to target folder
    mailbox.flag(msg.uid, ["\\Seen"], True)  # type: ignore
    mailbox.move(msg.uid, target_folder)  # type: ignore
    logging.debug("Marked message %s as seen and moved to folder '%s'", msg.uid, target_folder)

    return target_folder != "duplicate"


def detect_bounce(msg: MailMessage) -> str:
    """Detect whether the message is a bounce message. This is detected by two methods:
    1. If the To address contains "+bounces--"
    2. If the message is detected as a bounce by flufl.bounce

    Args:
        msg (MailMessage): IMAP message to check

    Returns:
        str: Original recipient email address(es) if bounce detected, else empty string

    """
    # Check To addresses for bounce marker
    for to in msg.to:
        if bounced_recipients := parse_bounce_address(to):
            logging.debug(
                "Bounce detected by parse_bounce_address() for message %s, recipient: %s",
                msg.uid,
                bounced_recipients,
            )
            return bounced_recipients

    # Use flufl.bounce to scan message
    bounced_recipients = scan_message(msg.obj)  # type: ignore
    if bounced_recipients:
        logging.debug(
            "Bounce detected by flufl.bounce.scan_message() for message %s, recipients: %s",
            msg.uid,
            bounced_recipients,
        )
        return ",".join(bounced_recipients)

    return ""


def validate_email(
    msg: MailMessage, ml: List
) -> tuple[str, dict[str, str]]:
    """
    Check a new single IMAP message from the Inbox:
        * Bounce detection
        * Allowed sender (broadcast mode)
        * Sender authentication (broadcast mode)
        * Subscriber check (group mode)

    Args:
        msg (MailMessage): IMAP message to process
        ml (List): Mailing list the message belongs to

    Returns:
        tuple (str, dict): Status of the message processing and error information
    """
    logging.debug("Processing message: %s", msg.subject)
    status = "ok"
    error_info: dict[str, str] = {}

    # --- Bounced message detection ---
    if bounced_recipients := detect_bounce(msg):
        logging.info("Message %s is a bounce for recipients: %s", msg.uid, bounced_recipients)
        status = "bounce-msg"
        error_info = {"bounced_recipients": bounced_recipients}
        return status, error_info

    # --- Sender not allowed checks ---
    # In broadcast mode, ensure the original sender of the message is in the allowed senders list
    if ml.mode == "broadcast" and ml.allowed_senders:
        allowed_senders = json_array_to_list(ml.allowed_senders)
        if not msg.from_values or msg.from_values.email not in allowed_senders:
            logging.warning(
                "Sender <%s> not in allowed senders for list <%s>, skipping message %s",
                msg.from_values.email if msg.from_values else "unknown",
                ml.address,
                msg.uid,
            )
            status = "sender-not-allowed"
            return status, error_info

    # In broadcast mode, check sender authentication if configured
    # The password is provided via a +password suffix in the To address of the mailing list
    if ml.mode == "broadcast" and ml.sender_auth:
        sender_auth_passwords = json_array_to_list(ml.sender_auth)
        sender_email = msg.from_values.email if msg.from_values else ""

        # Iterate over all To addresses to find the string that matches the list address
        for to_addr in msg.to:
            if is_expanded_address_the_mailing_list(to_addr, ml.address):
                plus_suffix = get_plus_suffix(to_addr)
                if plus_suffix in sender_auth_passwords:
                    logging.debug(
                        "Sender <%s> provided valid authentication password for list <%s>",
                        sender_email,
                        ml.address,
                    )
                    continue  # Valid password found, continue processing
        logging.warning(
            "Sender <%s> failed authentication for list <%s>, skipping message %s",
            sender_email,
            ml.address,
            msg.uid,
        )
        status = "sender-auth-failed"
        return status, error_info

    # In group mode, ensure the original sender is one of the subscribers
    subscribers: list[Subscriber] = get_list_subscribers(ml)
    if ml.mode == "group" and subscribers and ml.only_subscribers_send:
        subscriber_emails = [sub.email for sub in subscribers]
        if not msg.from_values or msg.from_values.email not in subscriber_emails:
            logging.error(
                "Sender %s not a subscriber of list %s, skipping message %s",
                msg.from_values.email if msg.from_values else "unknown",
                ml.name,
                msg.uid,
            )
            status = "sender-not-allowed"
            return status, error_info

    # --- Fallback return: all seems to be OK ---
    return status, error_info


def check_all_lists_for_messages(app: Flask) -> None:
    """
    Check IMAP for new messages for all lists, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    logging.info("Checking for new messages...")

    # Iterate over all configured lists
    maillists = List.query.filter_by(deleted=False).all()
    for ml in maillists:
        logging.debug("Checking list: %s (%s)", ml.name, ml.address)
        try:
            with MailBox(host=ml.imap_host, port=int(ml.imap_port)).login(
                username=ml.imap_user, password=ml.imap_pass
            ) as mailbox:
                # Create required folders
                create_required_folders(app, mailbox)

                # --- INBOX processing ---
                mailbox.folder.set(app.config["IMAP_FOLDER_INBOX"])
                # Fetch unseen messages
                for msg in mailbox.fetch():
                    # Process new message: check for bounce, store in DB, and abort if duplicate
                    status, error_info = validate_email(msg=msg, ml=ml)
                    no_duplicate = store_msg_in_db_and_imap(
                        app=app,
                        ml=ml,
                        mailbox=mailbox,
                        msg=msg,
                        status=status,
                        error_info=error_info,
                    )
                    # If status is not "ok" or message is duplicate, skip sending
                    if status != "ok" or not no_duplicate:
                        continue

                    # Send the message to all subscribers of the list
                    send_msg_to_subscribers(app=app, msg=msg, ml=ml, mailbox=mailbox)
        except Exception as e:  # pylint: disable=broad-except
            logging.error(
                "Error processing list %s: %s\nTraceback: %s", ml.name, e, traceback.format_exc()
            )

    logging.debug("Finished checking for new messages")
