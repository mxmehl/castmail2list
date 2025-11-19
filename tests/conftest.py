"""Fixtures for testing the Flask application."""

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from castmail2list.app import create_app
from castmail2list.models import MailingList, Subscriber, User, db


def add_subscriber(**kwargs) -> Subscriber:
    """Helper function to add a subscriber to the database for testing."""
    subscriber = Subscriber(**kwargs)
    db.session.add(subscriber)
    db.session.commit()
    return subscriber


@pytest.fixture(name="app")
def fixture_app():
    """Create and configure a new app instance for each test"""
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture(name="client")
def fixture_client():
    """Create a test client with an authenticated user and initial data"""
    app = create_app(
        config_overrides={
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        },
        one_off_call=True,
    )
    ctx = app.app_context()
    ctx.push()
    try:
        # fully reset engine to ensure clean in-memory DB
        try:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        except Exception:  # pylint: disable=broad-except
            pass
        db.create_all()

        # Add some initial data
        user = User(username="testuser", password=generate_password_hash("password"), role="user")
        db.session.add(user)
        ml = MailingList(
            name="Test List",
            address="list@example.com",
            mode="broadcast",
            imap_host="ml.local",
            imap_port=993,
            imap_user="user",
            imap_pass="pass",
        )
        db.session.add(ml)
        db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)

        yield client
    finally:
        db.session.remove()
        try:
            db.drop_all()
            db.engine.dispose()
        except Exception:  # pylint: disable=broad-except
            pass
        ctx.pop()


@pytest.fixture(name="client_unauthed")
def fixture_client_unauthed():
    """Create a test client without an authenticated user"""
    app = create_app(
        config_overrides={
            "TESTING": True,
            "SECRET_KEY": "test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        },
        one_off_call=True,
    )
    ctx = app.app_context()
    ctx.push()
    try:
        db.session.remove()
        try:
            db.drop_all()
            db.engine.dispose()
        except Exception:  # pylint: disable=broad-except
            pass
        db.create_all()
        client = app.test_client()
        yield client
    finally:
        db.session.remove()
        try:
            db.drop_all()
            db.engine.dispose()
        except Exception:  # pylint: disable=broad-except
            pass
        ctx.pop()
