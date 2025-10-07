import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///castmail2list.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")

    IMAP_HOST = os.getenv("IMAP_HOST", "***REMOVED***")
    IMAP_USER = os.getenv("IMAP_USER", "test-list@***REMOVED***")
    IMAP_PASS = os.getenv("IMAP_PASS", "testtest123")
    IMAP_FOLDER = "INBOX"

    SMTP_HOST = os.getenv("SMTP_HOST", "***REMOVED***")
    SMTP_USER = os.getenv("SMTP_USER", "test-list@***REMOVED***")
    SMTP_PASS = os.getenv("SMTP_PASS", "testtest123")
