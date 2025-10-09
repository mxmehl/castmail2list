"""IMAP worker for CastMail2List"""

import logging
import os
import time

from imap_tools import MailBox
from sqlalchemy.exc import IntegrityError

from .mailer import Mail
from .models import List, Message, Subscriber, db


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
    Check IMAP for new messages for all lists, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    logging.info("Checking for new messages...")

    # Iterate over all configured lists
    lists = List.query.all()
    for l in lists:
        logging.info("Checking list: %s (%s)", l.name, l.address)
        try:
            with MailBox(host=l.imap_host, port=int(l.imap_port)).login(
                username=l.imap_user, password=l.imap_pass
            ) as mailbox:
                # Create required folders
                create_folders(
                    mailbox,
                    [
                        app.config["IMAP_FOLDER_INBOX"],
                        app.config["IMAP_FOLDER_PROCESSED"],
                        app.config["IMAP_FOLDER_BOUNCES"],
                    ],
                )
                # Select INBOX folder
                mailbox.folder.set(app.config["IMAP_FOLDER_INBOX"])

                # Fetch unseen messages
                for msg in mailbox.fetch():
                    logging.debug("Processing message: %s", msg.subject)

                    # Store message in database
                    m = Message()
                    m.list_id = l.id
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
                        # Mark message as seen and move to avoid reprocessing
                        mailbox.flag(msg.uid, ["\\Seen"], True)
                        mailbox.move(msg.uid, app.config["IMAP_FOLDER_PROCESSED"])
                        continue

                    # Get subscribers for this list
                    subscribers = Subscriber.query.filter_by(list_id=l.id).all()
                    logging.debug("Found %d subscribers: %s", len(subscribers), subscribers)

                    # Send to subscribers
                    for subscriber in subscribers:
                        try:
                            # Get plain text content
                            content = msg.text or msg.html or "No content available"

                            mail = Mail(
                                smtp_server=app.config["SMTP_HOST"],
                                smtp_port=587,
                                smtp_user=app.config["SMTP_USER"],
                                smtp_password=app.config["SMTP_PASS"],
                                smtp_starttls=True,
                                smtp_from=l.from_addr,
                            )
                            mail.send_email(
                                subject=msg.subject,
                                message=content,
                                recipient=subscriber.email,
                            )
                            logging.debug("Sent message to %s", subscriber.email)
                        except Exception as e:  # pylint: disable=broad-except
                            logging.error("Failed to send message to %s: %s", subscriber.email, e)

                    # Mark message as seen and move to Processed folder
                    mailbox.flag(msg.uid, ["\\Seen"], True)
                    mailbox.move(msg.uid, app.config["IMAP_FOLDER_PROCESSED"])
                    logging.debug("Marked message %s as seen", msg.uid)
        except Exception as e:  # pylint: disable=broad-except
            logging.error("Error processing list %s: %s", l.name, e)

    logging.debug("Finished checking for new messages")
