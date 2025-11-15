"""Configuration for CastMail2List"""

import os


class Config:  # pylint: disable=too-few-public-methods
    """Flask configuration from environment variables with defaults"""

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///castmail2list.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

    IMAP_HOST = os.getenv("IMAP_HOST", "***REMOVED***")
    IMAP_USER = os.getenv("IMAP_USER", "test-list@***REMOVED***")
    IMAP_PASS = os.getenv("IMAP_PASS", "testtest123")
    IMAP_FOLDER_INBOX = "INBOX"
    IMAP_FOLDER_PROCESSED = "Processed"
    IMAP_FOLDER_BOUNCES = "Bounces"

    SMTP_HOST = os.getenv("SMTP_HOST", "***REMOVED***")
    SMTP_USER = os.getenv("SMTP_USER", "test-list@***REMOVED***")
    SMTP_PASS = os.getenv("SMTP_PASS", "testtest123")

    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # seconds
