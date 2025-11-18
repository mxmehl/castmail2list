"""Configuration for CastMail2List"""

import os


class Config:  # pylint: disable=too-few-public-methods
    """Flask configuration from environment variables with defaults"""

    # App settings
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///castmail2list.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

    # General settings
    LANGUAGE = "en"  # Supported languages: "en", "de"
    DOMAIN = os.getenv("DOMAIN", "***REMOVED***")

    # IMAP settings and defaults (used as defaults for new lists)
    IMAP_DEFAULT_HOST = os.getenv("IMAP_DEFAULT_HOST", "***REMOVED***")
    IMAP_DEFAULT_DOMAIN = os.getenv("IMAP_DEFAULT_DOMAIN", "***REMOVED***")
    IMAP_DEFAULT_PORT = os.getenv("IMAP_DEFAULT_PORT", "993")
    IMAP_DEFAULT_PASS = os.getenv("IMAP_DEFAULT_PASS", "testtest123")

    # IMAP folder names
    IMAP_FOLDER_INBOX = os.getenv("IMAP_FOLDER_INBOX", "INBOX")
    IMAP_FOLDER_PROCESSED = os.getenv("IMAP_FOLDER_PROCESSED", "Processed")
    IMAP_FOLDER_SENT = os.getenv("IMAP_FOLDER_SENT", "Sent")
    IMAP_FOLDER_BOUNCES = os.getenv("IMAP_FOLDER_BOUNCES", "Bounces")
    IMAP_FOLDER_DENIED = os.getenv("IMAP_FOLDER_DENIED", "Denied")
    IMAP_FOLDER_DUPLICATE = os.getenv("IMAP_FOLDER_DUPLICATE", "Duplicate")

    # SMTP settings (defaults for new lists)
    SMTP_HOST = os.getenv("SMTP_HOST", "***REMOVED***")
    SMTP_PORT = os.getenv("SMTP_PORT", "587")
    SMTP_USER = os.getenv("SMTP_USER", "test-list@***REMOVED***")
    SMTP_PASS = os.getenv("SMTP_PASS", "testtest123")
    SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() in ("true", "1", "yes")

    POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
