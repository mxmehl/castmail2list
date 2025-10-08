"""IMAP worker for CastMail2List"""

import email
import imaplib
import logging
import time
from email.policy import default

from .mailer import send_mail
from .models import Message, db


def poll_imap(app):
    """Runs forever in a thread, polling once per minute."""
    with app.app_context():
        while True:
            try:
                process_new_messages(app)
            except Exception as e:  # pylint: disable=broad-except
                logging.error("IMAP worker error: %s", e)
            time.sleep(app.config["POLL_INTERVAL"])


def process_new_messages(app) -> None:
    """
    Check IMAP for new messages, store them in the DB, and send to subscribers.
    Called periodically by poll_imap().

    Args:
        app: Flask app context
    """
    logging.debug("Checking for new messages...")
    cfg = app.config
    imap = imaplib.IMAP4_SSL(cfg["IMAP_HOST"])
    imap.login(cfg["IMAP_USER"], cfg["IMAP_PASS"])
    imap.select(cfg["IMAP_FOLDER"])
    _, data = imap.search(None, "UNSEEN")
    for num in data[0].split():
        _, msg_data = imap.fetch(num, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw, policy=default)

        # store message
        m = Message(
            list_id=1,  # for now, single list
            subject=msg["subject"],
            from_addr=msg["from"],
            raw=raw.decode(errors="ignore"),
        )
        db.session.add(m)
        db.session.commit()

        # send to subscribers
        subscribers = app.db_session.query(app.models.Subscriber).filter_by(list_id=1).all()
        for s in subscribers:
            send_mail(
                cfg,
                s.email,
                msg["subject"],
                msg.get_body(preferencelist="plain").get_content(),
                cfg["IMAP_USER"],
            )

        imap.store(num, "+FLAGS", "\\Seen")

    imap.close()
    imap.logout()
