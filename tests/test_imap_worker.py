"""
Tests for IMAP worker bounce detection and scaffolding for future message handling.
"""

from flask import Flask
from imap_tools import MailboxLoginError, MailMessage

import castmail2list.imap_worker as imap_worker_mod
from castmail2list import mailer
from castmail2list.imap_worker import IncomingEmail, create_required_folders
from castmail2list.models import EmailIn, MailingList, Subscriber, db
from castmail2list.utils import create_bounce_address

from .conftest import MailboxStub

# pylint: disable=protected-access,too-few-public-methods


def _call_detect_bounce(incoming: IncomingEmail) -> tuple[str, list[str]]:
    """
    Helper to access private bounce detection for focused testing.

    Using a helper isolates the protected access to one place so tests remain clean.
    """
    return incoming._detect_bounce()


def test_incoming_message_detect_bounce(
    bounce_samples: dict[str, tuple[MailMessage, str, list[str]]], incoming_message_factory
):
    """Validate bounce detection using real sample .eml files."""
    for filename, (mail_msg, expected_rec, expected_ids) in bounce_samples.items():
        incoming: IncomingEmail = incoming_message_factory(mail_msg)
        bounce_rec, bounce_ids = incoming._detect_bounce()
        assert bounce_rec == expected_rec, f"Failed for {filename}"
        assert bounce_ids == expected_ids, f"Failed for {filename}"


def test_detect_bounce_via_to_header(incoming_message_factory):
    """_detect_bounce should find bounced recipient from special To header."""
    recipient = "john.doe@gmail.com"
    list_addr = "list@example.com"
    raw = (
        b"Subject: Bounce Test\nTo: "
        + create_bounce_address(list_addr, recipient).encode()
        + b"\nFrom: sender@example.com\nMessage-ID: mid-test2\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "detect-to-1"
    incoming: IncomingEmail = incoming_message_factory(msg)

    bounced_rec, bounced_mid = incoming._detect_bounce()
    assert isinstance(bounced_rec, str)
    # parse_bounce_address returns the bounced local part in our samples
    assert bounced_rec == "john.doe@gmail.com"
    # ... and the Message-ID is extracted correctly
    assert isinstance(bounced_mid, list)
    assert len(bounced_mid) == 1
    assert "mid-test2" in bounced_mid


def test_detect_bounce_via_flufl_scan(monkeypatch, incoming_message_factory):
    """_detect_bounce should use flufl.bounce.scan_message when present."""
    # Prepare a simple message without special To header
    raw = (
        b"Subject: Scan Test\nTo: list@example.com\n"
        b"From: sender@example.com\nMessage-ID: test-3\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "detect-flufl-1"
    incoming: IncomingEmail = incoming_message_factory(msg)

    # Monkeypatch the scan_message function used inside the imap_worker module
    def _fake_scan(_msg):
        return {b"flufl-recipient@example.com"}

    monkeypatch.setattr(imap_worker_mod, "scan_message", _fake_scan)

    bounced_rec, bounced_mid = incoming._detect_bounce()
    assert isinstance(bounced_rec, str)
    assert "flufl-recipient@example.com" in bounced_rec
    assert isinstance(bounced_mid, list)
    assert len(bounced_mid) == 1
    assert "test-3" in bounced_mid


def test_incoming_message_no_bounce(incoming_message_factory):
    """Minimal non-bounce message should return empty string."""
    raw = (
        b"Subject: Hello\nTo: list@example.com\n"
        b"From: sender@example.com\nMessage-ID: test-5\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "non-bounce"
    incoming: IncomingEmail = incoming_message_factory(msg)
    bounced_rec, bounced_mid = incoming._detect_bounce()
    assert bounced_rec == ""
    assert bounced_mid == []


def test_sender_authentication_and_to_cleanup(mailing_list: MailingList, incoming_message_factory):
    """Sender authentication via +suffix should pass and To address be cleaned."""
    # Configure mailing list to expect a sender auth password
    mailing_list.sender_auth = ["secret123"]

    # Test message with no password
    raw_noauth = b"Subject: Auth Test\nTo: list@example.com\nFrom: auth@example.com\n\nBody"
    msg_noauth = MailMessage.from_bytes(raw_noauth)
    msg_noauth.uid = "auth-0"
    incoming_noauth: IncomingEmail = incoming_message_factory(msg_noauth)

    # Test message with incorrect password
    raw_badauth = b"Subject: Auth Test\nTo: list+false@example.com\nFrom: auth@example.com\n\nBody"
    msg_badauth = MailMessage.from_bytes(raw_badauth)
    msg_badauth.uid = "auth-1"
    incoming_badauth: IncomingEmail = incoming_message_factory(msg_badauth)

    # Test message with correct password suffix
    raw_ok = b"Subject: Auth Test\nTo: list+secret123@example.com\nFrom: auth@example.com\n\nBody"
    msg_ok = MailMessage.from_bytes(raw_ok)
    msg_ok.uid = "auth-2"
    incoming_ok: IncomingEmail = incoming_message_factory(msg_ok)

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
    incoming: IncomingEmail = incoming_message_factory(MailMessage.from_bytes(b"Subject: x\n\n\n"))
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
    incoming1: IncomingEmail = incoming_message_factory(msg)
    res1 = incoming1.process_incoming_msg()
    assert res1 is True

    # Second processing of the same message should be detected as duplicate
    msg2 = MailMessage.from_bytes(raw)
    msg2.uid = "dup-2"  # type: ignore[attr-defined]
    incoming2: IncomingEmail = incoming_message_factory(msg2)
    res2 = incoming2.process_incoming_msg()
    assert res2 is False

    # Verify mailbox_stub recorded move to duplicate folder for the second UID
    assert mailbox_stub._moves.get("dup-2") == incoming2.app.config["IMAP_FOLDER_DUPLICATE"]


def test_broadcast_sender_not_allowed(
    mailing_list: MailingList, incoming_message_factory, mailbox_stub: MailboxStub
):
    """Broadcast mode should reject senders not in `allowed_senders` and move to denied."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["allowed@example.com"]

    raw = b"Subject: Bad Sender\nTo: list@example.com\nFrom: badguy@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "bad-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
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
    db.session.add(sub)
    db.session.commit()

    # Message from non-subscriber should be denied
    raw1 = b"Subject: Group Test\nTo: list@example.com\nFrom: intruder@example.com\n\nBody"
    msg1 = MailMessage.from_bytes(raw1)
    msg1.uid = "grp-1"
    incoming1: IncomingEmail = incoming_message_factory(msg1)
    res1 = incoming1.process_incoming_msg()
    assert res1 is False
    assert mailbox_stub._moves.get("grp-1") == incoming1.app.config["IMAP_FOLDER_DENIED"]

    # Message from subscriber should be allowed (no duplicate in DB, so processed)
    raw2 = b"Subject: Group Test\nTo: list@example.com\nFrom: member@example.com\n\nBody"
    msg2 = MailMessage.from_bytes(raw2)
    msg2.uid = "grp-2"
    incoming2: IncomingEmail = incoming_message_factory(msg2)
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
    incoming: IncomingEmail = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is True

    # Verify DB has a Message with our Message-ID
    stored_msg = EmailIn.query.filter_by(message_id="store-1@example.com").first()
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

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True

    # Ensure there's at least one subscriber to send to
    db.session.add(Subscriber(list_id=incoming.ml.id, email="recipient@example.com"))
    db.session.commit()

    # Patch Mail.send_email_to_recipient to avoid SMTP
    def _fake_send(_self, _recipient):
        return b"OK"

    monkeypatch.setattr(mailer.OutgoingEmail, "send_email_to_recipient", _fake_send, raising=True)

    sent_successful, _ = mailer.send_msg_to_subscribers(
        app=incoming.app, msg=msg, ml=incoming.ml, mailbox=mailbox_stub
    )

    assert isinstance(sent_successful, list)


def test_send_msg_not_called_for_bounce(bounce_samples, incoming_message_factory, monkeypatch):
    """Ensure `send_msg_to_subscribers` is NOT called for bounce messages."""
    # Pick one bounce sample
    _, (bounce_msg, _, _) = next(iter(bounce_samples.items()))

    called = {}

    def _spy(_app, _msg, _ml, _mailbox):
        """Spy replacement for `send_msg_to_subscribers` used to observe calls."""
        called["called"] = True
        return [], []

    monkeypatch.setattr(mailer, "send_msg_to_subscribers", _spy)

    incoming: IncomingEmail = incoming_message_factory(bounce_msg)
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
            """Return False to simulate missing folder."""
            return False

        def create(self, folder=None):
            """Create the folder (test stub)."""
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
    started = {}

    class FakeThread:
        """Thread-like fake used to verify thread start is invoked."""

        def __init__(self, target=None, args=None, daemon=None):
            """Initialize fake thread (no-op)."""
            # accept parameters and ignore them to satisfy signature
            del target, args, daemon
            started["created"] = True

        def start(self):
            """Simulate starting the thread by recording state."""
            started["started"] = True

    monkeypatch.setattr(imap_worker_mod, "threading", type("T", (), {"Thread": FakeThread}))

    app = Flask(__name__)
    app.config["TESTING"] = False
    imap_worker_mod.initialize_imap_polling(app)
    assert started.get("created") is True
    assert started.get("started") is True


def test_check_all_lists_handles_imap_errors(monkeypatch, client):
    """check_all_lists_for_messages should handle MailboxLoginError and other exceptions."""

    # Fake MailBox that raises MailboxLoginError when login() is called
    class FakeMailBoxLoginFail:
        """Fake MailBox that raises `MailboxLoginError` on login."""

        def __init__(self, *args, **kwargs):
            """Initialize fake mailbox that will raise on login."""
            del args, kwargs

        def login(self, username=None, password=None):
            """Raise a mailbox login error when login is attempted."""
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
                """Fake MailBox whose fetch raises a runtime error"""

                def __init__(self):
                    class Folder:
                        """Simulate folder handler for MailBox"""

                        def set(self, _):
                            """Simulate folder.set call."""
                            del _

                    self.folder = Folder()

                def fetch(self):
                    """Simulate fetch raising an error."""
                    raise RuntimeError("fetch error")

            return MB()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeMailBoxFetchFail:
        """Fake MailBox whose fetch raises a runtime error inside the context manager."""

        def __init__(self, *args, **kwargs):
            """Init fake mailbox fetch fail (no-op)."""
            del args, kwargs

        def login(self, username=None, password=None):
            """Return a context manager which will raise from fetch()."""
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

    incoming: IncomingEmail = incoming_message_factory(msg)
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
    incoming: IncomingEmail = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is False
    assert mailbox_stub._moves.get("self-1") == incoming.app.config["IMAP_FOLDER_DENIED"]
    stored_msg = EmailIn.query.filter_by(
        status="duplicate-from-same-instance", list_id=incoming.ml.id
    ).first()
    # status stored should reflect duplicate-from-same-instance
    assert stored_msg is not None
    assert stored_msg.status == "duplicate-from-same-instance"


def test_bounce_messages_are_stored_in_bounces(incoming_message_factory, mailbox_stub):
    """A bounce message should result in stored status 'bounce-msg' and moved to bounces folder."""
    # Use a simple To that parse_bounce_address recognizes (pattern +bounces--)
    raw = (
        b"Subject: Bounce\nTo: list+bounces--recipient@example.com\n"
        b"From: sender@example.com\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "bounce-store-1"
    incoming: IncomingEmail = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is False

    # Verify DB record exists and status is 'bounce-msg'
    stored_msg = EmailIn.query.filter_by(status="bounce-msg", list_id=incoming.ml.id).first()
    assert stored_msg is not None
    assert stored_msg.status == "bounce-msg"
    assert mailbox_stub._moves.get("bounce-store-1") == incoming.app.config["IMAP_FOLDER_BOUNCES"]


def test_store_msg_generates_message_id_when_missing(incoming_message_factory):
    """When Message-ID header is missing, a generated id should be stored in DB."""
    raw = b"Subject: No ID\nTo: list@example.com\nFrom: sender@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "noid-1"
    incoming: IncomingEmail = incoming_message_factory(msg)

    res = incoming.process_incoming_msg()
    assert res is True

    all_msgs = EmailIn.query.filter_by(list_id=incoming.ml.id).all()
    stored_msg = all_msgs[-1] if all_msgs else None
    assert stored_msg is not None
    assert stored_msg.message_id != ""
