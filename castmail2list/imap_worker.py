import email
import imaplib
import threading
import time
from email.policy import default

from flask import current_app
from mailer import send_mail
from models import List, Message, db


def poll_imap(app):
    """Runs forever in a thread, polling once per minute."""
    with app.app_context():
        while True:
            try:
                process_new_messages(app)
            except Exception as e:
                print("IMAP worker error:", e)
            time.sleep(10)


def process_new_messages(app):
    cfg = app.config
    imap = imaplib.IMAP4_SSL(cfg["IMAP_HOST"])
    imap.login(cfg["IMAP_USER"], cfg["IMAP_PASS"])
    imap.select(cfg["IMAP_FOLDER"])
    typ, data = imap.search(None, "UNSEEN")
    for num in data[0].split():
        typ, msg_data = imap.fetch(num, "(RFC822)")
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
                msg.get_body(preferencelist=("plain")).get_content(),
                cfg["IMAP_USER"],
            )

        imap.store(num, "+FLAGS", "\\Seen")

    imap.close()
    imap.logout()
