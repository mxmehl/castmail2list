# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for IMAP worker bounce detection and scaffolding for future message handling.
"""

from flask import Flask
from imap_tools import MailboxLoginError, MailMessage

import castmail2list.imap_worker as imap_worker_mod
from castmail2list import mailer
from castmail2list.imap_worker import IncomingEmail, create_required_folders
from castmail2list.models import EmailIn, Logs, MailingList, Subscriber, db
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
    assert passed is False

    # Bad authentication should return empty string
    passed = incoming_badauth._validate_email_sender_authentication()
    assert passed is False
    # OK authentication should return the matching To address
    passed = incoming_ok._validate_email_sender_authentication()
    assert passed is True


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

    # Verify DB has only one Message with our Message-ID
    stored_msgs = EmailIn.query.filter_by(message_id="dup-test-1@example.com").all()
    assert len(stored_msgs) == 1

    # Verify DB has a log entry for the duplicate attempt
    duplicate_logs: list[Logs] = Logs.query.filter_by(
        event="email_in", list_id=incoming2.ml.id
    ).all()
    assert len(duplicate_logs) == 1
    assert duplicate_logs[0].message.startswith("Duplicate message detected")
    assert duplicate_logs[0].details.get("original-message-id") == "dup-test-1@example.com"

    # Verify that the duplicate message is still stored in DB, but with a different Message-ID
    duplicate_stored: list[EmailIn] = EmailIn.query.filter_by(
        subject="Dup", status="duplicate"
    ).all()
    assert len(duplicate_stored) == 1
    assert duplicate_stored[0].message_id.startswith("duplicate-")


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


def test_broadcast_allowed_senders_case_insensitive(
    mailing_list: MailingList, incoming_message_factory
):
    """Broadcast mode allowed_senders should work case-insensitively."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["admin@example.com"]

    # Sender with different casing should be allowed
    raw = b"Subject: Case Test\nTo: list@example.com\nFrom: ADMIN@Example.COM\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "case-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_broadcast_sender_auth_as_alternative(mailing_list: MailingList, incoming_message_factory):
    """Broadcast mode should allow sender_auth as alternative to allowed_senders."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["admin@example.com"]
    mailing_list.sender_auth = ["secret123"]

    # Sender not in allowed_senders but with valid password should be allowed
    raw = b"Subject: Auth Alt\nTo: list+secret123@example.com\nFrom: user@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "auth-alt-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True

    # Verify that password is not leaked to recipients
    assert all("+secret123" not in to for to in incoming.msg.to)
    assert all("+secret123" not in to.email for to in incoming.msg.to_values)


def test_broadcast_only_sender_auth(
    mailing_list: MailingList, incoming_message_factory, mailbox_stub: MailboxStub
):
    """Broadcast mode with only sender_auth should allow password holders."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = []
    mailing_list.sender_auth = ["password1", "password2"]

    # Valid password should be allowed
    raw1 = b"Subject: Auth Only\nTo: list+password1@example.com\nFrom: anyone@example.com\n\nBody"
    msg1 = MailMessage.from_bytes(raw1)
    msg1.uid = "auth-only-1"
    incoming1: IncomingEmail = incoming_message_factory(msg1)
    assert incoming1.process_incoming_msg() is True

    # No password should be rejected
    raw2 = b"Subject: No Auth\nTo: list@example.com\nFrom: anyone@example.com\n\nBody"
    msg2 = MailMessage.from_bytes(raw2)
    msg2.uid = "auth-only-2"
    incoming2: IncomingEmail = incoming_message_factory(msg2)
    assert incoming2.process_incoming_msg() is False
    assert mailbox_stub._moves.get("auth-only-2") == incoming2.app.config["IMAP_FOLDER_DENIED"]


def test_broadcast_no_restrictions(mailing_list: MailingList, incoming_message_factory):
    """Broadcast mode with neither allowed_senders nor sender_auth should allow anyone."""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = []
    mailing_list.sender_auth = []

    # Anyone should be allowed
    raw = b"Subject: Open\nTo: list@example.com\nFrom: anyone@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "open-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


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


def test_group_mode_subscriber_case_insensitive(
    mailing_list: MailingList, incoming_message_factory
):
    """Group mode subscriber check should work case-insensitively."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    sub = Subscriber(list_id=mailing_list.id, email="alice@example.com")
    db.session.add(sub)
    db.session.commit()

    # Subscriber with different casing should be allowed
    raw = b"Subject: Case Test\nTo: list@example.com\nFrom: ALICE@Example.COM\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-case-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_group_mode_allowed_senders_bypass(mailing_list: MailingList, incoming_message_factory):
    """Group mode allowed_senders should bypass subscriber check."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    mailing_list.allowed_senders = ["moderator@example.com"]
    sub = Subscriber(list_id=mailing_list.id, email="alice@example.com")
    db.session.add(sub)
    db.session.commit()

    # Moderator not in subscribers but in allowed_senders should be allowed
    raw = b"Subject: Mod Post\nTo: list@example.com\nFrom: moderator@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-mod-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_group_mode_sender_auth_bypass(mailing_list: MailingList, incoming_message_factory):
    """Group mode sender_auth should bypass subscriber check."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    mailing_list.sender_auth = ["guest123"]
    sub = Subscriber(list_id=mailing_list.id, email="alice@example.com")
    db.session.add(sub)
    db.session.commit()

    # Non-subscriber with valid password should be allowed
    raw = b"Subject: Guest\nTo: list+guest123@example.com\nFrom: guest@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-guest-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_group_mode_sender_auth_bypass_case_in_password(
    mailing_list: MailingList, incoming_message_factory
):
    """Group mode sender_auth should be case-sensitive in password."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    mailing_list.sender_auth = ["guest123"]
    sub = Subscriber(list_id=mailing_list.id, email="alice@example.com")
    db.session.add(sub)
    db.session.commit()

    # Non-subscriber with valid password should be allowed
    raw = b"Subject: Guest\nTo: list+GUEST123@example.com\nFrom: guest@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-guest-2"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is False


def test_group_mode_sender_auth_bypass_case_in_address(
    mailing_list: MailingList, incoming_message_factory
):
    """Group mode sender_auth should be case-insensitive in list address."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    mailing_list.sender_auth = ["guest123"]
    sub = Subscriber(list_id=mailing_list.id, email="alice@example.com")
    db.session.add(sub)
    db.session.commit()

    # Non-subscriber with valid password should be allowed
    raw = b"Subject: Guest\nTo: LiSt+guest123@EXAMPLE.com\nFrom: guest@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-guest-3"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_group_mode_open(mailing_list: MailingList, incoming_message_factory):
    """Group mode with only_subscribers_send=False should allow anyone."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = False

    # Anyone should be allowed
    raw = b"Subject: Open Group\nTo: list@example.com\nFrom: anyone@example.com\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "grp-open-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    res = incoming.process_incoming_msg()
    assert res is True


def test_group_mode_all_authorization_methods(
    mailing_list: MailingList, incoming_message_factory, mailbox_stub: MailboxStub
):
    """Group mode should check allowed_senders, sender_auth, then subscriber in order."""
    mailing_list.mode = "group"
    mailing_list.only_subscribers_send = True
    mailing_list.allowed_senders = ["mod@example.com"]
    mailing_list.sender_auth = ["pass123"]
    sub = Subscriber(list_id=mailing_list.id, email="member@example.com")
    db.session.add(sub)
    db.session.commit()

    # Test 1: allowed_senders bypass
    raw1 = b"Subject: Mod\nTo: list@example.com\nFrom: mod@example.com\n\nBody"
    msg1 = MailMessage.from_bytes(raw1)
    msg1.uid = "grp-all-1"
    assert incoming_message_factory(msg1).process_incoming_msg() is True

    # Test 2: sender_auth bypass
    raw2 = b"Subject: Auth\nTo: list+pass123@example.com\nFrom: guest@example.com\n\nBody"
    msg2 = MailMessage.from_bytes(raw2)
    msg2.uid = "grp-all-2"
    assert incoming_message_factory(msg2).process_incoming_msg() is True

    # Test 3: subscriber
    raw3 = b"Subject: Member\nTo: list@example.com\nFrom: member@example.com\n\nBody"
    msg3 = MailMessage.from_bytes(raw3)
    msg3.uid = "grp-all-3"
    assert incoming_message_factory(msg3).process_incoming_msg() is True

    # Test 4: none of the above
    raw4 = b"Subject: Intruder\nTo: list@example.com\nFrom: intruder@example.com\n\nBody"
    msg4 = MailMessage.from_bytes(raw4)
    msg4.uid = "grp-all-4"
    incoming4 = incoming_message_factory(msg4)
    assert incoming4.process_incoming_msg() is False
    assert mailbox_stub._moves.get("grp-all-4") == incoming4.app.config["IMAP_FOLDER_DENIED"]


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
    assert passed is True


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


# ==================== Tests for Rejection Notifications Integration ====================
# Note: Detailed unit tests for should_notify_sender() and send_rejection_notification()
# are in test_mailer.py. These integration tests only verify end-to-end workflow.


def test_rejection_notification_integration_known_sender(
    mailing_list: MailingList, incoming_message_factory, smtp_mock
):
    """Integration test: rejection notification sent to known sender via full workflow"""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["allowed@example.com"]

    # Add the rejected sender to database (so they're "known")
    subscriber = Subscriber(
        list_id=mailing_list.id, email="rejected@example.com", name="Rejected User"
    )
    db.session.add(subscriber)
    db.session.commit()

    raw = (
        b"Subject: Test\nTo: list@example.com\nFrom: rejected@example.com\n"
        b"Message-ID: <test123>\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "rej-1"

    incoming: IncomingEmail = incoming_message_factory(msg)
    incoming.app.config["NOTIFY_REJECTED_SENDERS"] = True
    incoming.app.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True

    res = incoming.process_incoming_msg()
    assert res is False  # Message rejected

    # Verify SMTP was called (notification sent)
    assert len(smtp_mock) == 1
    assert smtp_mock[0]["to_addrs"] == "rejected@example.com"


def test_rejection_notification_integration_unknown_sender(
    mailing_list: MailingList, incoming_message_factory, smtp_mock
):
    """Integration test: no notification for unknown sender via full workflow"""
    mailing_list.mode = "broadcast"
    mailing_list.allowed_senders = ["allowed@example.com"]

    raw = (
        b"Subject: Test\nTo: list@example.com\nFrom: unknown@example.com\n"
        b"Message-ID: <test789>\n\nBody"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "rej-3"

    incoming: IncomingEmail = incoming_message_factory(msg)
    incoming.app.config["NOTIFY_REJECTED_SENDERS"] = True
    incoming.app.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    incoming.app.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []

    res = incoming.process_incoming_msg()
    assert res is False  # Message rejected

    # Verify NO SMTP send was attempted (notification was not sent)
    assert len(smtp_mock) == 0
