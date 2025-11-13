"""Database models for CastMail2List"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import validates

db = SQLAlchemy()
if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class AlembicVersion(Model):  # pylint: disable=too-few-public-methods
    """Alembic version table mapping"""

    def __init__(self, version_num: str):
        self.version_num = version_num

    version_num: str = db.Column(db.String(32), primary_key=True)


class User(Model, UserMixin):  # pylint: disable=too-few-public-methods
    """A user of the CastMail2List application"""

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String)  # Hashed password
    role = db.Column(db.String, default="admin")


class MailingList(Model):  # pylint: disable=too-few-public-methods
    """A mailing list"""

    __tablename__ = "list"

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String)
    address: str = db.Column(db.String, unique=True)
    from_addr: str = db.Column(db.String)

    # Mode settings
    mode: str = db.Column(db.String)  # "broadcast" or "group"
    only_subscribers_send: bool = db.Column(
        db.Boolean, default=False
    )  # Only allow subscribers to send
    allowed_senders: str = db.Column(
        db.JSON, default="[]"
    )  # Stores allowed sender emails as JSON array
    sender_auth: str = db.Column(
        db.JSON, default="[]"
    )  # Stores list of sender passwords as JSON array

    # IMAP settings for fetching emails
    imap_host: str = db.Column(db.String)
    imap_port: str | int = db.Column(db.String)
    imap_user: str = db.Column(db.String)
    imap_pass: str = db.Column(db.String)

    # Subscribers and messages relationships
    subscribers = db.relationship(
        "Subscriber", backref="list", lazy=True, cascade="all, delete-orphan"
    )
    # Cascade delete messages as well
    messages = db.relationship("Message", backref="list", lazy=True, cascade="all, delete-orphan")

    # Soft-delete flag: mark list as deleted instead of removing row from DB
    deleted: bool = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)


class Subscriber(Model):  # pylint: disable=too-few-public-methods
    """A subscriber to a mailing list"""

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id = db.Column(db.Integer, primary_key=True)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=False)
    name: str = db.Column(db.String)
    email: str = db.Column(db.String, nullable=False)
    comment: str = db.Column(db.String)
    subscriber_type: str = db.Column(db.String, default="normal")  # subscriber or list

    @validates("email")
    def _validate_email(self, _, value):
        """Normalize email to lowercase on set so comparisons/queries are case-insensitive."""
        return value.lower() if isinstance(value, str) else value


class Message(Model):  # pylint: disable=too-few-public-methods
    """A message sent to a mailing list"""

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id: int = db.Column(db.Integer, primary_key=True)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"))
    message_id: str = db.Column(db.String, unique=True)
    subject: str = db.Column(db.String)
    from_addr: str = db.Column(db.String)
    headers: str = db.Column(db.Text)
    raw: str = db.Column(db.Text)  # for now, store full RFC822 text
    received_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    status: str = db.Column(
        db.String
    )  # "ok", "bounce-msg", "sender-not-allowed", "sender-auth-failed", "duplicate"
    error_info: dict = db.Column(db.JSON, default="{}")  # Store diagnostic info as JSON
