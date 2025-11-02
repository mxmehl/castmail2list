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

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String, unique=True)
    address: str = db.Column(db.String)
    subscribers = db.relationship(
        "Subscriber", backref="list", lazy=True, cascade="all, delete-orphan"
    )
    # Cascade delete messages as well
    messages = db.relationship("Message", backref="list", lazy=True, cascade="all, delete-orphan")

    # Technical settings per list
    mode: str = db.Column(db.String)  # "broadcast" or "group"
    imap_host: str = db.Column(db.String)
    imap_port: str | int = db.Column(db.String)
    imap_user: str = db.Column(db.String)
    imap_pass: str = db.Column(db.String)
    from_addr: str = db.Column(db.String)
    allowed_senders: str = db.Column(db.Text)  # Comma-separated list of allowed sender emails
    only_subscribers_send: bool = db.Column(
        db.Boolean, default=False
    )  # Only allow subscribers to send


class Subscriber(Model):  # pylint: disable=too-few-public-methods
    """A subscriber to a mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=False)
    name: str = db.Column(db.String)
    email: str = db.Column(db.String, nullable=False)
    comment: str = db.Column(db.String)


class Message(Model):  # pylint: disable=too-few-public-methods
    """A message sent to a mailing list"""

    id: int = db.Column(db.Integer, primary_key=True)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"))
    message_id: str = db.Column(db.String, unique=True)
    subject: str = db.Column(db.String)
    from_addr: str = db.Column(db.String)
    headers: dict[str, tuple[str, ...]] = db.Column(db.Text)
    raw: str = db.Column(db.Text)  # for now, store full RFC822 text
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
