"""Configuration for CastMail2List"""

import os


class Config:  # pylint: disable=too-few-public-methods
    """Flask configuration from environment variables with defaults"""

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///castmail2list.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

    # IMAP settings and defaults (used as defaults for new lists)
    IMAP_DEFAULT_HOST = os.getenv("IMAP_DEFAULT_HOST", "***REMOVED***")
    IMAP_DEFAULT_PORT = os.getenv("IMAP_DEFAULT_PORT", "993")
    IMAP_DEFAULT_PASS = os.getenv("IMAP_DEFAULT_PASS", "testtest123")
    IMAP_FOLDER_INBOX = os.getenv("IMAP_FOLDER_INBOX", "INBOX")
    IMAP_FOLDER_PROCESSED = os.getenv("IMAP_FOLDER_PROCESSED", "Processed")
    IMAP_FOLDER_BOUNCES = os.getenv("IMAP_FOLDER_BOUNCES", "Bounces")

    # Default "from" address for new lists
    IMAP_LIST_FROM = os.getenv("IMAP_LIST_FROM", "noreply@***REMOVED***")

    # SMTP settings (defaults for new lists)
    SMTP_HOST = os.getenv("SMTP_HOST", "***REMOVED***")
    SMTP_PORT = os.getenv("SMTP_PORT", "587")
    SMTP_USER = os.getenv("SMTP_USER", "test-list@***REMOVED***")
    SMTP_PASS = os.getenv("SMTP_PASS", "testtest123")
    SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() in ("true", "1", "yes")

    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # seconds

    # Removed: IMAP_LIST_USER (single-list user), as lists are now dynamic
