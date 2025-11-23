"""
Tests for IMAP worker bounce detection and scaffolding for future message handling.
"""

import pytest
from imap_tools import MailMessage

from castmail2list.imap_worker import IncomingMessage

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


# ---------------- Placeholder / scaffolding tests for future extensions ----------------


@pytest.mark.skip(reason="To be implemented: allowed sender logic")
def test_process_incoming_allowed_sender_placeholder():
    """Placeholder: will assert behavior when sender not in allowed list (broadcast)."""


@pytest.mark.skip(reason="To be implemented: duplicate detection logic")
def test_process_incoming_duplicate_placeholder():
    """Placeholder: will assert duplicate message handling and IMAP move target."""
