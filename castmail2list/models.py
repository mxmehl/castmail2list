"""Database models for CastMail2List"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class List(db.Model):  # pylint: disable=too-few-public-methods
    """A mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    address = db.Column(db.String)
    subscribers = db.relationship("Subscriber", backref="list", lazy=True)


class Subscriber(db.Model):  # pylint: disable=too-few-public-methods
    """A subscriber to a mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("list.id"), nullable=False)
    email = db.Column(db.String, nullable=False)


class Message(db.Model):  # pylint: disable=too-few-public-methods
    """A message sent to a mailing list"""

    id = db.Column(db.Integer, primary_key=True)
    list_id = db.Column(db.Integer, db.ForeignKey("list.id"))
    subject = db.Column(db.String)
    from_addr = db.Column(db.String)
    raw = db.Column(db.Text)  # for now, store full RFC822 text
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
