"""
Tests for IMAP worker bounce detection and scaffolding for future message handling.
"""

import pytest
from imap_tools import MailMessage

from castmail2list.imap_worker import IncomingMessage
from castmail2list.models import MailingList

from .conftest import MailboxStub

# pylint: disable=protected-access


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
