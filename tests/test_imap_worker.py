"""
Tests for IMAP worker bounce detection and scaffolding for future message handling.
"""

import pytest
from flask import Flask
from imap_tools import MailboxLoginError, MailMessage

from castmail2list import mailer
from castmail2list.imap_worker import IncomingMessage, create_required_folders
from castmail2list.models import MailingList, Message, Subscriber
from castmail2list.models import db as _db

from .conftest import MailboxStub

# Test files use local helper classes and imports inside functions; allow those
# pylint: disable=import-outside-toplevel,too-few-public-methods,protected-access,missing-class-docstring,missing-function-docstring


def _call_detect_bounce(incoming: IncomingMessage) -> str:
    """
    Helper to access private bounce detection for focused testing.

    Using a helper isolates the protected access to one place so tests remain clean.
    """
    return incoming._detect_bounce()


def test_incoming_message_detect_bounce(bounce_samples, incoming_message_factory):
    """Validate bounce detection using real sample .eml files."""
    for filename, (mail_msg, expected) in bounce_samples.items():
        incoming = incoming_message_factory(mail_msg)
        assert _call_detect_bounce(incoming) == expected, f"Failed for {filename}"


def test_incoming_message_no_bounce(incoming_message_factory):
    """Minimal non-bounce message should return empty string."""
    raw = b"Subject: Hello\nTo: list@example.com\nFrom: sender@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "non-bounce"  # type: ignore[attr-defined]
    incoming = incoming_message_factory(msg)
    assert _call_detect_bounce(incoming) == ""


def test_sender_authentication_and_to_cleanup(mailing_list: MailingList, incoming_message_factory):
    """Sender authentication via +suffix should pass and To address be cleaned."""
    # Configure mailing list to expect a sender auth password
    mailing_list.sender_auth = ["secret123"]

    # Test message with no password
    raw_noauth = b"Subject: Auth Test\nTo: list@example.com\nFrom: auth@example.com\n\nBody"
    msg_noauth = MailMessage.from_bytes(raw_noauth)
    msg_noauth.uid = "auth-0"
    incoming_noauth: IncomingMessage = incoming_message_factory(msg_noauth)

    # Test message with incorrect password
    raw_badauth = b"Subject: Auth Test\nTo: list+false@example.com\nFrom: auth@example.com\n\nBody"
    msg_badauth = MailMessage.from_bytes(raw_badauth)
    msg_badauth.uid = "auth-1"
    incoming_badauth: IncomingMessage = incoming_message_factory(msg_badauth)

    # Test message with correct password suffix
    raw_ok = b"Subject: Auth Test\nTo: list+secret123@example.com\nFrom: auth@example.com\n\nBody"
    msg_ok = MailMessage.from_bytes(raw_ok)
    msg_ok.uid = "auth-2"
    incoming_ok: IncomingMessage = incoming_message_factory(msg_ok)

    # No authentication should return empty string
    passed = incoming_noauth._validate_email_sender_authentication()
    assert passed == ""

    # Bad authentication should return empty string
    passed = incoming_badauth._validate_email_sender_authentication()
    assert passed == ""

    # OK authentication should return the matching To address
    passed = incoming_ok._validate_email_sender_authentication()
    assert passed == "list+secret123@example.com"

    # after removing the suffix the stored To should be without +secret123
    incoming_ok._remove_password_in_to_address(old_to=passed, new_to="list@example.com")
    assert any("+secret123" not in t for t in incoming_ok.msg.to)


def test_duplicate_detection_moves_to_duplicate(
    incoming_message_factory, mailbox_stub: MailboxStub
):
    """Processing the same Message-ID twice should move the second copy to duplicate folder."""
    # Ensure the app DOMAIN is non-empty so the "duplicate-from-same-instance" check
    # does not trigger (an empty DOMAIN is contained in any header string).
    incoming: IncomingMessage = incoming_message_factory(
        MailMessage.from_bytes(b"Subject: x\n\n\n")
    )
    incoming_app = incoming.app
    incoming_app.config["DOMAIN"] = "lists.example.com"

    # Create a simple message with a deterministic Message-ID header
    raw = (
        b"Message-ID: <dup-test-1@example.com>\nSubject: Dup\n"
        b"To: list@example.com\nFrom: dup@example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "dup-1"
    # First processing should store it as new (returns True)
    incoming1: IncomingMessage = incoming_message_factory(msg)
    res1 = incoming1.process_incoming_msg()
    assert res1 is True

    # Second processing of the same message should be detected as duplicate
    msg2 = MailMessage.from_bytes(raw)
    msg2.uid = "dup-2"  # type: ignore[attr-defined]
    incoming2: IncomingMessage = incoming_message_factory(msg2)
    res2 = incoming2.process_incoming_msg()
    assert res2 is False

    # Verify mailbox_stub recorded move to duplicate folder for the second UID
    assert mailbox_stub._moves.get("dup-2") == incoming2.app.config["IMAP_FOLDER_DUPLICATE"]


# ---------------- Placeholder / scaffolding tests for future extensions ----------------


@pytest.mark.skip(reason="To be implemented: allowed sender logic")
def test_process_incoming_allowed_sender_placeholder():
    """Placeholder: will assert behavior when sender not in allowed list (broadcast)."""


@pytest.mark.skip(reason="To be implemented: duplicate detection logic")
def test_process_incoming_duplicate_placeholder():
    """Placeholder: will assert duplicate message handling and IMAP move target."""


def test_broadcast_sender_not_allowed(
    mailing_list: MailingList, incoming_message_factory, mailbox_stub: MailboxStub
):
    """Broadcast mode should reject senders not in `allowed_senders` and move to denied."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["allowed@example.com"]

    raw = b"Subject: Bad Sender\nTo: list@example.com\nFrom: badguy@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "bad-1"

    incoming: IncomingMessage = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is False
    assert mailbox_stub._moves.get("bad-1") == incoming.app.config["IMAP_FOLDER_DENIED"]


def test_group_mode_subscriber_restrictions(
    mailing_list: MailingList, incoming_message_factory, mailbox_stub: MailboxStub
):
    """
    Group mode should only allow messages from subscribers when `only_subscribers_send` is set.
    """
    # Set up a group list with one subscriber
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    sub = Subscriber(list_id=mailing_list.id, email="member@example.com")
    _db.session.add(sub)
    _db.session.commit()

    # Message from non-subscriber should be denied
    raw1 = b"Subject: Group Test\nTo: list@example.com\nFrom: intruder@example.com\n\nBody"
    msg1 = MailMessage.from_bytes(raw1)
    msg1.uid = "grp-1"
    incoming1: IncomingMessage = incoming_message_factory(msg1)
    res1 = incoming1.process_incoming_msg()
    assert res1 is False
    assert mailbox_stub._moves.get("grp-1") == incoming1.app.config["IMAP_FOLDER_DENIED"]

    # Message from subscriber should be allowed (no duplicate in DB, so processed)
    raw2 = b"Subject: Group Test\nTo: list@example.com\nFrom: member@example.com\n\nBody"
    msg2 = MailMessage.from_bytes(raw2)
    msg2.uid = "grp-2"
    incoming2: IncomingMessage = incoming_message_factory(msg2)
    res2 = incoming2.process_incoming_msg()
    assert res2 is True
    assert mailbox_stub._moves.get("grp-2") == incoming2.app.config["IMAP_FOLDER_PROCESSED"]


def test_processed_message_stored_and_moved(incoming_message_factory, mailbox_stub: MailboxStub):
    """A valid message should be stored in DB with status 'ok' and moved to processed folder."""
    raw = (
        b"Subject: Store Test\nMessage-ID: <store-1@example.com>"
        b"\nTo: list@example.com\nFrom: sender@example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "store-1"  # type: ignore[attr-defined]
    incoming: IncomingMessage = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is True

    # Verify DB has a Message with our Message-ID
    stored_msg = Message.query.filter_by(message_id="store-1@example.com").first()
    assert stored_msg is not None
    assert stored_msg.status == "ok"
    assert mailbox_stub._moves.get("store-1") == incoming.app.config["IMAP_FOLDER_PROCESSED"]


def test_send_msg_to_subscribers_called_for_ok_message(
    monkeypatch, incoming_message_factory, mailbox_stub
):
    """Ensure `send_msg_to_subscribers` is invoked for messages that pass checks."""
    # Arrange: create a simple message that should be OK
    raw = (
        b"Subject: Send Test\nMessage-ID: <send-1@example.com>"
        b"\nTo: list@example.com\nFrom: sender@example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "send-1"

    incoming: IncomingMessage = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True

    # Ensure there's at least one subscriber to send to
    _db.session.add(Subscriber(list_id=incoming.ml.id, email="recipient@example.com"))
    _db.session.commit()

    # Patch Mail.send_email_to_recipient to avoid SMTP
    def _fake_send(_self, _recipient):
        return b"OK"

    monkeypatch.setattr(mailer.Mail, "send_email_to_recipient", _fake_send, raising=True)

    sent_successful, _ = mailer.send_msg_to_subscribers(
        app=incoming.app, msg=msg, ml=incoming.ml, mailbox=mailbox_stub
    )

    assert isinstance(sent_successful, list)


def test_send_msg_not_called_for_bounce(bounce_samples, incoming_message_factory, monkeypatch):
    """Ensure `send_msg_to_subscribers` is NOT called for bounce messages."""
    # Pick one bounce sample
    _, (bounce_msg, _) = next(iter(bounce_samples.items()))

    called = {}

    def _spy(_app, _msg, _ml, _mailbox):
        """Spy replacement for `send_msg_to_subscribers` used to observe calls."""
        called["called"] = True
        return [], []

    monkeypatch.setattr(mailer, "send_msg_to_subscribers", _spy)

    incoming: IncomingMessage = incoming_message_factory(bounce_msg)
    res = incoming.process_incoming_msg()
    assert res is False
    assert called.get("called") is None


def test_create_required_folders_calls_create(client):
    """create_required_folders should call MailBox.folder.create when folder missing."""

    class FakeFolder:
        """Fake folder object used to verify create() is called."""

        def __init__(self):
            self.created = False

        def exists(self, _name):
            return False

        def create(self, folder=None):
            # accept and ignore the folder parameter to satisfy signature
            del folder
            self.created = True

    class FakeMailbox:
        """Fake MailBox exposing a `folder` attribute like imap_tools.MailBox."""

        def __init__(self):
            self.folder = FakeFolder()

    mb = FakeMailbox()
    create_required_folders(client.application, mb)  # type: ignore[arg-type]
    assert mb.folder.created is True


def test_initialize_imap_polling_starts_thread(monkeypatch):
    """initialize_imap_polling should start a background thread when TESTING is False."""
    import castmail2list.imap_worker as imap_worker_mod

    started = {}

    class FakeThread:
        """Thread-like fake used to verify thread start is invoked."""

        def __init__(self, target=None, args=None, daemon=None):
            # accept parameters and ignore them to satisfy signature
            del target, args, daemon
            started["created"] = True

        def start(self):
            started["started"] = True

    monkeypatch.setattr(imap_worker_mod, "threading", type("T", (), {"Thread": FakeThread}))

    app = Flask(__name__)
    app.config["TESTING"] = False
    imap_worker_mod.initialize_imap_polling(app)
    assert started.get("created") is True
    assert started.get("started") is True


def test_check_all_lists_handles_imap_errors(mailing_list, monkeypatch, client):
    """check_all_lists_for_messages should handle MailboxLoginError and other exceptions."""
    del mailing_list
    import castmail2list.imap_worker as imap_worker_mod

    # Fake MailBox that raises MailboxLoginError when login() is called
    class FakeMailBoxLoginFail:
        """Fake MailBox that raises `MailboxLoginError` on login."""

        def __init__(self, *args, **kwargs):
            pass

        def login(self, username=None, password=None):
            # accept and ignore username/password to satisfy signature
            del username, password
            # construct a realistic MailboxLoginError payload so __str__ does not fail
            # command_result is expected to be a tuple like (status, data)
            raise MailboxLoginError((None, b"error"), "OK")

    monkeypatch.setattr(imap_worker_mod, "MailBox", FakeMailBoxLoginFail)

    # Should not raise
    imap_worker_mod.check_all_lists_for_messages(client.application)

    # Now fake a MailBox whose fetch() raises a generic exception inside the context manager
    class FakeCM:
        """Context manager used to simulate a mailbox fetch raising an error."""

        def __enter__(self):
            class MB:
                def __init__(self):
                    class Folder:
                        def set(self, _):
                            pass

                    self.folder = Folder()

                def fetch(self):
                    raise RuntimeError("fetch error")

            return MB()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeMailBoxFetchFail:
        """Fake MailBox whose fetch raises a runtime error inside the context manager."""

        def __init__(self, *args, **kwargs):
            pass

        def login(self, username=None, password=None):
            del username, password
            return FakeCM()

    monkeypatch.setattr(imap_worker_mod, "MailBox", FakeMailBoxFetchFail)

    # Should not raise despite fetch() raising
    imap_worker_mod.check_all_lists_for_messages(client.application)


def test_validate_sender_auth_when_from_missing(
    mailing_list: MailingList, incoming_message_factory
):
    """When the message has no From header, sender authentication still works."""
    # mailing_list fixture provided but not used directly here
    mailing_list.mode = "broadcast"
    mailing_list.sender_auth = ["pw"]

    raw = b"Subject: Auth Test\nTo: list+pw@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "auth-no-from"

    incoming: IncomingMessage = incoming_message_factory(msg)
    passed = incoming._validate_email_sender_authentication()
    # Current behaviour: authentication is checked by +suffix only,
    # independent of From header presence
    assert passed == "list+pw@example.com"


def test_validate_duplicate_from_same_instance(incoming_message_factory, mailbox_stub: MailboxStub):
    """
    Messages containing the app DOMAIN in X-CastMail2List-Domain are treated as messages from same
    instance sending to itself. This results in denial and storage with
    'duplicate-from-same-instance' status, as we do not want to provoke a mail loop.
    """
    app: Flask = incoming_message_factory(MailMessage.from_bytes(b"Subject: x\n\n")).app
    app.config["DOMAIN"] = "lists.example.com"

    raw = (
        b"Subject: Self\nMessage-ID: <self-1@example.com>\nTo: list@example.com\n"
        b"From: me@example.com\nX-CastMail2List-Domain: lists.example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "self-1"
    incoming: IncomingMessage = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is False
    assert mailbox_stub._moves.get("self-1") == incoming.app.config["IMAP_FOLDER_DENIED"]
    stored_msg = Message.query.filter_by(
        status="duplicate-from-same-instance", list_id=incoming.ml.id
    ).first()
    # status stored should reflect duplicate-from-same-instance
    assert stored_msg is not None
    assert stored_msg.status == "duplicate-from-same-instance"


def test_bounce_messages_are_stored_in_bounces(
    mailing_list, incoming_message_factory, mailbox_stub
):
    """A bounce message should result in stored status 'bounce-msg' and moved to bounces folder."""
    # Use a simple To that parse_bounce_address recognizes (pattern +bounces--)
    del mailing_list
    raw = (
        b"Subject: Bounce\nTo: list+bounces--recipient@example.com\n"
        b"From: sender@example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "bounce-store-1"
    incoming: IncomingMessage = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is False

    # Verify DB record exists and status is 'bounce-msg'
    stored_msg = Message.query.filter_by(status="bounce-msg", list_id=incoming.ml.id).first()
    assert stored_msg is not None
    assert stored_msg.status == "bounce-msg"
    assert mailbox_stub._moves.get("bounce-store-1") == incoming.app.config["IMAP_FOLDER_BOUNCES"]


def test_store_msg_generates_message_id_when_missing(incoming_message_factory, mailbox_stub):
    """When Message-ID header is missing, a generated id should be stored in DB."""
    # mailbox_stub fixture isn't used directly in this test
    del mailbox_stub
    raw = b"Subject: No ID\nTo: list@example.com\nFrom: sender@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "noid-1"
    incoming: IncomingMessage = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is True

    all_msgs = Message.query.filter_by(list_id=incoming.ml.id).all()
    stored_msg = all_msgs[-1] if all_msgs else None
    assert stored_msg is not None
    assert stored_msg.message_id != ""
