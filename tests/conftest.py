"""Fixtures for testing the Flask application."""

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from castmail2list.app import create_app
from castmail2list.models import User, db


@pytest.fixture(name="app")
def fixture_app():
    """Create and configure a new app instance for each test"""
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture(name="client")
def fixture_client():
    """
    Create a test client for the Flask application with an initialized in-memory database and a test
    user. Does not start background IMAP polling.
    """
    app = create_app(
        config_overrides={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
        # start_imap=False,
    )

    ctx = app.app_context()
    ctx.push()
    try:
        db.create_all()
        # create a test user so login_required routes can load a user from session
        user = User(username="testuser", password=generate_password_hash("password"), role="user")
        db.session.add(user)
        db.session.commit()

        client = app.test_client()
        # set the session user id so flask-login sees an authenticated user
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
        yield client
    finally:
        ctx.pop()


@pytest.fixture(name="client_unauthed")
def fixture_client_unauthed():
    """
    Create a test client for the Flask application with an initialized in-memory database and no
    authenticated user. Does not start background IMAP polling.
    """
    app = create_app(
        config_overrides={"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"},
        # start_imap=False,
    )

    ctx = app.app_context()
    ctx.push()
    try:
        db.create_all()

        client = app.test_client()

        yield client
    finally:
        ctx.pop()
