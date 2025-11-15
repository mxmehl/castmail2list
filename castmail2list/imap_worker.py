"""IMAP worker for CastMail2List"""

import logging
import time

from imap_tools import MailBox
from sqlalchemy.exc import IntegrityError

from .mailer import send_mail
from .models import Message, Subscriber, db


def poll_imap(app):
    """Runs forever in a thread, polling once per minute."""
    with app.app_context():
        while True:
            try:
                process_new_messages(app)
            except Exception as e:  # pylint: disable=broad-except
                logging.error("IMAP worker error: %s", e)
            time.sleep(app.config["POLL_INTERVAL"])


def create_folders(mailbox: MailBox, folder_names: list[str]) -> None:
    """Create IMAP folders if they don't exist."""
    for folder in folder_names:
        if not mailbox.folder.exists(folder):
            mailbox.folder.create(folder=folder)
            logging.info("Created IMAP folder: %s", folder)


def process_new_messages(app) -> None:
    """
    Check IMAP for new messages, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    logging.info("Checking for new messages...")
    cfg = app.config

    # Use imap_tools MailBox instead of imaplib
    with MailBox(host=cfg["IMAP_DEFAULT_HOST"], port=cfg["IMAP_DEFAULT_PORT"]).login(
        username=cfg["IMAP_LIST_USER"], password=cfg["IMAP_DEFAULT_PASS"]
    ) as mailbox:
        # Create required folders
        create_folders(
            mailbox,
            [cfg["IMAP_FOLDER_INBOX"], cfg["IMAP_FOLDER_PROCESSED"], cfg["IMAP_FOLDER_BOUNCES"]],
        )
        # Select INBOX folder
        mailbox.folder.set(cfg["IMAP_FOLDER_INBOX"])

        # Fetch unseen messages
        for msg in mailbox.fetch():
            logging.debug("Processing message: %s", msg.subject)

            # Store message in database
            m = Message()
            m.list_id = 1  # for now, single list
            m.message_id = msg.headers.get("message-id", ())[0].strip("<>")
            m.subject = msg.subject
            m.from_addr = msg.from_
            m.raw = str(msg.obj)  # Get raw RFC822 message
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
                # Mark message as seen to avoid reprocessing
                mailbox.flag(msg.uid, ["\\Seen"], True)
                continue

            # Get subscribers for this list
            subscribers = Subscriber.query.filter_by(list_id=1).all()

            # Send to subscribers
            for subscriber in subscribers:
                try:
                    # Get plain text content
                    content = msg.text or msg.html or "No content available"

                    send_mail(
                        cfg,
                        subscriber.email,
                        msg.subject,
                        content,
                        cfg["IMAP_USER"],
                    )
                    logging.debug("Sent message to %s", subscriber.email)
                except Exception as e:  # pylint: disable=broad-except
                    logging.error("Failed to send message to %s: %s", subscriber.email, e)

            # Mark message as seen and move to Processed folder
            mailbox.flag(msg.uid, ["\\Seen"], True)
            mailbox.move(msg.uid, cfg["IMAP_FOLDER_PROCESSED"])
            logging.debug("Marked message %s as seen", msg.uid)

    logging.debug("Finished checking for new messages")
