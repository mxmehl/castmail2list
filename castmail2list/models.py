"""Database models for CastMail2List"""

from datetime import datetime
from typing import TYPE_CHECKING

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class List(Model):  # pylint: disable=too-few-public-methods
    """A mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    address = db.Column(db.String)
    subscribers = db.relationship(
        "Subscriber", backref="list", lazy=True, cascade="all, delete-orphan"
    )
    # Cascade delete messages as well
    messages = db.relationship("Message", backref="list", lazy=True, cascade="all, delete-orphan")

    # Technical settings per list
    mode = db.Column(db.String)
    imap_host = db.Column(db.String)
    imap_port = db.Column(db.String)
    imap_user = db.Column(db.String)
    imap_pass = db.Column(db.String)
    from_addr = db.Column(db.String)


class Subscriber(Model):  # pylint: disable=too-few-public-methods
    """A subscriber to a mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=False)
    name = db.Column(db.String)
    email = db.Column(db.String, nullable=False)
    comment = db.Column(db.String)


class Message(Model):  # pylint: disable=too-few-public-methods
    """A message sent to a mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("list.id"))
    message_id = db.Column(db.String, unique=True)
    subject = db.Column(db.String)
    from_addr = db.Column(db.String)
    headers = db.Column(db.Text)
    raw = db.Column(db.Text)  # for now, store full RFC822 text
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
