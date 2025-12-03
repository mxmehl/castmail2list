"""Database models for CastMail2List"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import Mapped, validates

db = SQLAlchemy()
if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model
else:
    Model = db.Model


class AlembicVersion(Model):  # pylint: disable=too-few-public-methods
    """Alembic version table mapping"""

    def __init__(self, version_num: str):
        self.version_num = version_num

    version_num: str = db.Column(db.String(32), primary_key=True, nullable=False)


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
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String, nullable=False)
    api_key: str = db.Column(db.String, nullable=True)
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
    name: str = db.Column(db.String, nullable=False)
    address: str = db.Column(db.String, unique=True, nullable=False)  # Ensure it's not null
    from_addr: str = db.Column(db.String)
    avoid_duplicates: bool = db.Column(db.Boolean, default=True)

    # Mode settings
    mode: str = db.Column(db.String, nullable=False)  # "broadcast" or "group"
    only_subscribers_send: bool = db.Column(db.Boolean, default=False)
    allowed_senders: list = db.Column(db.JSON, default=list)
    sender_auth: list = db.Column(db.JSON, default=list)

    # IMAP settings for fetching emails
    imap_host: str = db.Column(db.String, nullable=False)
    imap_port: int = db.Column(db.Integer, nullable=False)
    imap_user: str = db.Column(db.String, nullable=False)
    imap_pass: str = db.Column(db.String, nullable=False)

    # Subscribers and messages relationships
    subscribers = db.relationship(
        "Subscriber", backref="list", lazy="joined", cascade="all, delete-orphan"
    )
    emailin = db.relationship(
        "EmailIn", backref="list", lazy="joined", cascade="all, delete-orphan"
    )
    emailout = db.relationship(
        "EmailOut", backref="list", lazy="joined", cascade="all, delete-orphan"
    )

    # Soft-delete flag: mark list as deleted instead of removing row from DB
    deleted: bool = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def deactivate(self):
        """Mark the mailing list as deleted"""
        self.deleted = True
        self.deleted_at = datetime.now(timezone.utc)

    def reactivate(self):
        """Reactivate a soft-deleted mailing list"""
        self.deleted = False
        self.deleted_at = None

    @validates("address")
    def _validate_address(self, _, value):
        """Validate that the address is a valid email address"""
        if "@" not in value:
            raise ValueError(f"Invalid email address: {value}")
        return value.lower()

    @validates("mode")
    def _validate_mode(self, _, value):
        """Validate that the mode is either 'broadcast' or 'group'"""
        if value not in {"broadcast", "group"}:
            raise ValueError(f"Invalid mode: {value}")
        return value


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
    name: str = db.Column(db.String, nullable=True)
    email: str = db.Column(db.String, nullable=False)
    comment: str = db.Column(db.String, nullable=True)
    subscriber_type: str = db.Column(db.String, default="normal")  # subscriber or list

    @validates("email")
    def _validate_email(self, _, value):
        """Normalize email to lowercase on set so comparisons/queries are case-insensitive, and
        validate format."""
        if "@" not in value:
            raise ValueError(f"Invalid email address: {value}")
        return value.lower() if isinstance(value, str) else value


class EmailIn(Model):  # pylint: disable=too-few-public-methods
    """An email message sent to a mailing list"""

    __tablename__ = "email_in"

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    message_id: str = db.Column(db.String, unique=True, nullable=False, primary_key=True)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"))
    subject: str = db.Column(db.String, nullable=True)
    from_addr: str = db.Column(db.String, nullable=True)
    headers: str = db.Column(db.Text, nullable=False)
    raw: str = db.Column(db.Text)  # store full RFC822 text
    received_at: Mapped[datetime] = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    status: str = db.Column(
        db.String
    )  # "ok", "bounce-msg", "sender-not-allowed", "sender-auth-failed", "duplicate"
    error_info: dict = db.Column(db.JSON, default=dict)


class EmailOut(Model):  # pylint: disable=too-few-public-methods
    """An email message sent out to subscribers"""

    __tablename__ = "email_out"

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    message_id: str = db.Column(db.String, unique=True, nullable=False, primary_key=True)
    email_in_mid: str = db.Column(db.String, db.ForeignKey("email_in.message_id"), nullable=False)
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=True)
    subject: str = db.Column(db.String, nullable=True)
    recipients: list = db.Column(db.JSON, default=list)
    raw: str = db.Column(db.Text)  # store full RFC822 text
    sent_at: Mapped[datetime] = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    sent_successful: list = db.Column(db.JSON, default=list)
    sent_failed: list = db.Column(db.JSON, default=list)


class Logs(Model):  # pylint: disable=too-few-public-methods
    """Application event log"""

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id: int = db.Column(db.Integer, primary_key=True)
    timestamp: Mapped[datetime] = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    level: str = db.Column(db.String, nullable=False)  # Severity: "info", "warning", "error"
    event: str = db.Column(db.String, nullable=False)  # Event type: "sent-msg", "login-attempt"
    message: str = db.Column(db.Text, nullable=False)  # Short log message
    details: dict = db.Column(db.JSON, nullable=True)  # Optional detailed log message in JSON
    list_id: int = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=True)  # Associated list
