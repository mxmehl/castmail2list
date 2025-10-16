"""IMAP worker for CastMail2List"""

import logging
import os
import time
import traceback
import uuid

from flask import Flask
from imap_tools import MailBox
from imap_tools.message import MailMessage
from sqlalchemy.exc import IntegrityError

from .mailer import send_msg_to_subscribers
from .models import List, Message, Subscriber, db

REQUIRED_FOLDERS_ENVS = ["IMAP_FOLDER_INBOX", "IMAP_FOLDER_PROCESSED", "IMAP_FOLDER_BOUNCES"]


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
            time.sleep(app.config["POLL_INTERVAL"])


def create_required_folders(app: Flask, mailbox: MailBox) -> None:
    """Create required IMAP folders if they don't exist."""
    for folder in [app.config[env] for env in REQUIRED_FOLDERS_ENVS]:
        if not mailbox.folder.exists(folder):
            mailbox.folder.create(folder=folder)
            logging.info("Created IMAP folder: %s", folder)


def mark_msg_as_processed(app: Flask, mailbox: MailBox, msg: MailMessage) -> None:
    """Mark message as seen and move to Processed folder."""
    mailbox.flag(msg.uid, ["\\Seen"], True)  # type: ignore
    mailbox.move(msg.uid, app.config["IMAP_FOLDER_PROCESSED"])  # type: ignore
    logging.debug("Marked message %s as seen and moved to Processed folder", msg.uid)


def process_imap_msg(app: Flask, msg: MailMessage, mailbox: MailBox, ml: List) -> bool:
    """Process a single IMAP message: store in DB and check for duplicates

    Args:
        app (Flask): Flask app context
        msg (MailMessage): IMAP message to process
        mailbox (Mailbox): IMAP mailbox
        ml (List): Mailing list the message belongs to

    Returns:
        bool: True if message was new and processed, False if it was a duplicate and skipped

    """
    logging.debug("Processing message: %s", msg.subject)

    # Store message in database
    m = Message()
    m.list_id = ml.id
    m.message_id = next(iter(msg.headers.get("message-id", ())), str(uuid.uuid4())).strip("<>")
    m.subject = msg.subject
    m.from_addr = msg.from_
    m.headers = str(msg.headers)
    m.raw = str(msg.obj)  # Get raw RFC822 message
    db.session.add(m)
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        logging.warning(
            "Message %s already processed (Message-ID %s exists in DB), skipping",
            msg.uid,
            m.message_id,
        )
        # Mark message as seen and move to avoid reprocessing
        mark_msg_as_processed(app=app, mailbox=mailbox, msg=msg)
        return False


def check_all_lists_for_messages(app: Flask) -> None:
    """
    Check IMAP for new messages for all lists, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    logging.info("Checking for new messages...")

    # Iterate over all configured lists
    maillists = List.query.all()
    for ml in maillists:
        logging.debug("Checking list: %s (%s)", ml.name, ml.address)
        try:
            with MailBox(host=ml.imap_host, port=int(ml.imap_port)).login(
                username=ml.imap_user, password=ml.imap_pass
            ) as mailbox:
                # Create required folders
                create_required_folders(app, mailbox)
                # Select INBOX folder
                mailbox.folder.set(app.config["IMAP_FOLDER_INBOX"])

                # Fetch unseen messages
                for msg in mailbox.fetch():
                    # Process new message (store in DB) and abort if duplicate
                    msg_ok = process_imap_msg(app=app, msg=msg, mailbox=mailbox, ml=ml)
                    if not msg_ok:
                        continue

                    # Get subscribers for this list, and send the message to them
                    subscribers = Subscriber.query.filter_by(list_id=ml.id).all()
                    logging.debug("Found %d subscribers: %s", len(subscribers), subscribers)
                    send_msg_to_subscribers(
                        app=app, msg=msg, ml=ml, subscribers=subscribers, mailbox=mailbox
                    )

                    # Mark message as seen and move to Processed folder
                    mark_msg_as_processed(app=app, mailbox=mailbox, msg=msg)
        except Exception as e:  # pylint: disable=broad-except
            logging.error(
                "Error processing list %s: %s\nTraceback: %s", ml.name, e, traceback.format_exc()
            )

    logging.debug("Finished checking for new messages")
