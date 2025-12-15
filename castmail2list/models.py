"""Database models for CastMail2List"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, validates


class Base(DeclarativeBase):  # pylint: disable=too-few-public-methods
    """Base class for all models with naming convention for constraints"""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


db = SQLAlchemy(model_class=Base)
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
    """A user of the CastMail2List application

    Attributes:
        id (int): Primary key of the user.
        username (str): Unique username for login.
        password (str): Hashed password for authentication.
        api_key (str): Optional API key for programmatic access.
        role (str): Role of the user, e.g., "admin".
    """

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
    """A mailing list

    Attributes:
        id (str): Primary key of the mailing list.
        display (str): Display name of the mailing list.
        address (str): Email address of the mailing list.
        from_addr (str): Default From address for outgoing emails.
        avoid_duplicates (bool): Whether to avoid sending duplicate emails.
        mode (str): Mode of the mailing list, either "broadcast" or "group".
        only_subscribers_send (bool): Whether only subscribers can send emails to the list.
        allowed_senders (list): List of email addresses allowed to send to the list.
        sender_auth (list): List of authentication passwords for senders.
        imap_host (str): IMAP server host for fetching emails.
        imap_port (int): IMAP server port.
        imap_user (str): IMAP username.
        imap_pass (str): IMAP password.
        subscribers (relationship): Relationship to Subscriber model.
        emailin (relationship): Relationship to EmailIn model.
        emailout (relationship): Relationship to EmailOut model.
        deleted (bool): Soft-delete flag for the mailing list.
        deleted_at (datetime): Timestamp of when the list was soft-deleted.
    """

    __tablename__ = "list"

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id: str = db.Column(db.String, primary_key=True)
    display: str = db.Column(db.String, nullable=True)
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
    """A subscriber to a mailing list

    Attributes:
        id (int): Primary key of the subscriber.
        list_id (str): Foreign key to the associated mailing list.
        name (str): Name of the subscriber.
        email (str): Email address of the subscriber.
        comment (str): Optional comment about the subscriber.
        subscriber_type (str): Type of subscriber, either "normal" or "list".
    """

    def __init__(self, **kwargs):
        # Only set attributes that actually exist on the mapped class
        for key, value in kwargs.items():
            if not hasattr(self.__class__, key):
                raise TypeError(
                    f"Unexpected keyword argument {key!r} for {self.__class__.__name__}"
                )
            setattr(self, key, value)

    id = db.Column(db.Integer, primary_key=True)
    list_id: str = db.Column(
        db.String, db.ForeignKey("list.id", onupdate="CASCADE"), nullable=False
    )
    name: str = db.Column(db.String, nullable=True)
    email: str = db.Column(db.String, nullable=False)
    comment: str = db.Column(db.String, nullable=True)
    subscriber_type: str = db.Column(db.String, default="normal")  # subscriber or list
    bounces: int = db.Column(db.Integer, nullable=False, default=0)

    @validates("email")
    def _validate_email(self, _, value):
        """Normalize email to lowercase on set so comparisons/queries are case-insensitive, and
        validate format."""
        if "@" not in value:
            raise ValueError(f"Invalid email address: {value}")
        return value.lower() if isinstance(value, str) else value

    def increase_bounce(self):
        """Increase bounce count by 1"""
        self.bounces += 1


class EmailIn(Model):  # pylint: disable=too-few-public-methods
    """An email message sent to a mailing list

    Attributes:
        message_id (str): Unique message ID of the email.
        list_id (str): Foreign key to the associated mailing list.
        subject (str): Subject of the email.
        from_addr (str): From address of the email.
        headers (str): Raw email headers as provided by imap_tools.
        raw (str): Full RFC822 text of the email.
        received_at (datetime): Timestamp when the email was received.
        status (str): Processing status of the email.
        error_info (dict): Optional error information if processing failed.
    """

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
    list_id: str = db.Column(
        db.String, db.ForeignKey("list.id", onupdate="CASCADE"), nullable=False
    )
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
    """An email message sent out to subscribers

    Attributes:
        message_id (str): Unique message ID of the outgoing email.
        email_in_mid (str): Foreign key to the associated incoming email message.
        list_id (str): Foreign key to the associated mailing list.
        subject (str): Subject of the outgoing email.
        recipients (list): List of recipient email addresses.
        raw (str): Full RFC822 text of the outgoing email.
        sent_at (datetime): Timestamp when the email was sent.
        sent_successful (list): List of email addresses the email was successfully sent to.
        sent_failed (list): List of email addresses the email failed to send to.
    """

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
    list_id: str = db.Column(db.String, db.ForeignKey("list.id", onupdate="CASCADE"), nullable=True)
    subject: str = db.Column(db.String, nullable=True)
    recipients: list = db.Column(db.JSON, default=list)
    raw: str = db.Column(db.Text)  # store full RFC822 text
    sent_at: Mapped[datetime] = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    sent_successful: list = db.Column(db.JSON, default=list)
    sent_failed: list = db.Column(db.JSON, default=list)


class Logs(Model):  # pylint: disable=too-few-public-methods
    """Application event log

    Attributes:
        id (int): Primary key of the log entry.
        timestamp (datetime): Timestamp of the log entry.
        level (str): Severity level of the log entry, e.g., "info", "warning", "error".
        event (str): Type of event being logged, e.g., "sent-msg", "login-attempt".
        message (str): Short log message.
        details (dict): Optional detailed log message in JSON format.
        list_id (str): Foreign key to the associated mailing list, if applicable.
    """

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
    list_id: str = db.Column(
        db.String, db.ForeignKey("list.id", onupdate="CASCADE"), nullable=True
    )  # Associated list
