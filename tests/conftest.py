"""Pytest fixtures for testing the CastMail2List Flask application.

Provides application/client fixtures plus IMAP worker related helpers.
"""

from contextlib import suppress
from pathlib import Path

import pytest
from flask import Flask
from imap_tools import MailMessage
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from castmail2list.app import create_app
from castmail2list.imap_worker import IncomingEmail
from castmail2list.models import MailingList, Subscriber, User, db


def add_subscriber(**kwargs) -> Subscriber:
    """Helper function to add a subscriber to the database for testing."""
    subscriber = Subscriber(**kwargs)
    db.session.add(subscriber)
    db.session.commit()
    return subscriber


@pytest.fixture(name="app")
def fixture_app():
    """Create and configure a new Flask app instance for tests."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture(name="client")
def fixture_client():
    """Create a test client with an authenticated user and initial data.

    Sets up an in-memory SQLite database and seeds a user and a mailing list.
    """
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
        # Reset engine to ensure clean in-memory DB; ignore SQLAlchemy-related errors safely
        with suppress(SQLAlchemyError):
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
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
        with suppress(SQLAlchemyError):
            db.drop_all()
            db.engine.dispose()
        ctx.pop()


@pytest.fixture(name="client_unauthed")
def fixture_client_unauthed():
    """Create a test client without an authenticated user.

    Uses an in-memory SQLite database and returns a Flask test client.
    """
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
        with suppress(SQLAlchemyError):
            db.drop_all()
            db.engine.dispose()
        db.create_all()
        client = app.test_client()
        yield client
    finally:
        db.session.remove()
        with suppress(SQLAlchemyError):
            db.drop_all()
            db.engine.dispose()
        ctx.pop()


# ---------------------- Fixtures For IMAP Worker Tests ----------------------


class MailboxStub:  # pylint: disable=too-few-public-methods
    """
    Minimal stub of imap_tools.MailBox for testing logic without network.

    Only the methods/attributes accessed by IncomingMessage are implemented.
    Extend as needed for future tests (e.g., folder creation, message fetching).
    """

    def __init__(self):
        self._flags: dict[str, tuple[list[str], bool]] = {}
        self._moves: dict[str, str] = {}

        class Folder:  # pylint: disable=too-few-public-methods
            """Stub folder handler for MailboxStub"""

            def exists(self, _name):  # always pretend folder exists
                """Pretend an IMAP folder exists."""
                return True

            def create(self, _folder):  # no-op
                """No-op folder creation for tests."""
                return None

        self.folder = Folder()

    def flag(self, uid_list: str, flag_set: list[str], value: bool):  # mimic MailBox.flag signature
        """Record flags set on a message UID (test-only)."""
        self._flags[uid_list] = (flag_set, value)

    def move(self, uid_list: str, destination_folder: str):  # mimic MailBox.move signature
        """Record a move operation (UID -> target folder) for assertions."""
        self._moves[uid_list] = destination_folder


@pytest.fixture(name="mailbox_stub")
def fixture_mailbox_stub() -> MailboxStub:
    """Provide a stub mailbox instance."""
    return MailboxStub()


@pytest.fixture(name="bounce_samples")
def fixture_bounce_samples() -> dict[str, tuple[MailMessage, str, list[str]]]:
    """
    Load real bounce .eml samples into MailMessage objects.

    Returns:
        dict: mapping filename -> (MailMessage, expected_recipient, [expected_bounced_ids])
    """
    samples_dir = Path(__file__).parent / "bounces"
    expected_map: dict[str, tuple[str, list]] = {
        "mailbox-full.eml": (
            "recipient-mailbox-is-full@docomo.ne.jp",
            [
                "200903042128.n24LSDot026083@mx.example.jp",
                "18726744-DE21-43A8-92B6-91B47AE35DC7@example.jp",
            ],
        ),
        "exceeds-size.eml": (
            "this-message-is-too-big-for-the-host@k.vodafone.ne.jp",
            [
                "200904280052.n3S0qj83022773@mx6.example.jp",
                "2B17AB23-5EA9-4E5F-B6C0-6A1BC2ECF522@example.jp",
            ],
        ),
    }
    result: dict[str, tuple[MailMessage, str, list[str]]] = {}
    for path in samples_dir.glob("*.eml"):
        with path.open("rb") as fh:
            msg = MailMessage.from_bytes(fh.read())
            # Ensure a uid attribute exists (normally added by imap_tools when fetching)
            msg.uid = path.name  # type: ignore[attr-defined]
            result[path.name] = (msg,) + expected_map.get(path.name, ("", []))
    return result


@pytest.fixture(name="incoming_message_factory")
def fixture_incoming_message_factory(client, mailing_list, mailbox_stub):
    """
    Factory for creating IncomingMessage instances for tests.

    Keeps test code terse and centralizes construction details."""

    def _factory(mail_msg: MailMessage) -> IncomingEmail:
        # Ensure a non-empty DOMAIN to avoid duplicate-from-same-instance matches in tests
        if not client.application.config.get("DOMAIN"):
            client.application.config["DOMAIN"] = "lists.example.com"

        return IncomingEmail(
            app=client.application,
            mailbox=mailbox_stub,
            msg=mail_msg,
            ml=mailing_list,
        )

    return _factory


# ----------------------  Fixtures for MailingList Variants ----------------------


@pytest.fixture(name="mailing_list")
def fixture_mailing_list(client) -> MailingList:  # depends on authenticated client & DB
    """Return the default mailing list created by the client fixture.

    The `client` fixture is not used directly here but is required to ensure the
    application context and database are available. We explicitly delete the
    reference to silence linter warnings about unused arguments.
    """
    del client
    ml = MailingList.query.filter_by(address="list@example.com").first()
    if ml is None:
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
    return ml


@pytest.fixture(name="broadcast_list")
def fixture_broadcast_list(client) -> MailingList:
    """Create a broadcast mode mailing list"""
    del client  # ensure app context is available
    ml = MailingList(
        name="Broadcast List",
        address="broadcast@example.com",
        mode="broadcast",
        avoid_duplicates=True,
        imap_host="mail.example.com",
        imap_port=993,
        imap_user="user",
        imap_pass="pass",
    )
    db.session.add(ml)
    db.session.commit()
    return ml


@pytest.fixture(name="broadcast_list_with_from")
def fixture_broadcast_list_with_from(client) -> MailingList:
    """Create a broadcast mode mailing list with custom from_addr"""
    del client
    ml = MailingList(
        name="Broadcast From List",
        address="broadcast-from@example.com",
        from_addr="custom@example.com",
        mode="broadcast",
        avoid_duplicates=True,
        imap_host="mail.example.com",
        imap_port=993,
        imap_user="user",
        imap_pass="pass",
    )
    db.session.add(ml)
    db.session.commit()
    return ml


@pytest.fixture(name="broadcast_list_no_avoid_dup")
def fixture_broadcast_list_no_avoid_dup(client) -> MailingList:
    """Create a broadcast mode mailing list without avoid_duplicates"""
    del client
    ml = MailingList(
        name="Broadcast No Dup",
        address="broadcast-nodup@example.com",
        mode="broadcast",
        avoid_duplicates=False,
        imap_host="mail.example.com",
        imap_port=993,
        imap_user="user",
        imap_pass="pass",
    )
    db.session.add(ml)
    db.session.commit()
    return ml


@pytest.fixture(name="group_list")
def fixture_group_list(client) -> MailingList:
    """Create a group mode mailing list"""
    del client
    ml = MailingList(
        name="Group List",
        address="group@example.com",
        mode="group",
        avoid_duplicates=True,
        imap_host="mail.example.com",
        imap_port=993,
        imap_user="user",
        imap_pass="pass",
    )
    db.session.add(ml)
    db.session.commit()
    return ml
