"""
Tests for mailer.py focusing on email composition and header handling.

Tests verify that different list modes (broadcast/group) and configurations
produce correct email headers and behavior as documented in doc/modes_and_headers.md.
"""

# mypy: disable-error-code="index"

import email
from unittest.mock import MagicMock

import pytest
from imap_tools import MailMessage
from pytest import MonkeyPatch

from castmail2list.mailer import Mail, send_msg_to_subscribers
from castmail2list.models import MailingList, Subscriber, db

# pylint: disable=protected-access,too-many-arguments,too-many-positional-arguments


@pytest.fixture(name="smtp_mock")
def fixture_smtp_mock(monkeypatch: MonkeyPatch):
    """
    Mock smtplib.SMTP to avoid actual network calls.

    Returns a mock object that records all sendmail calls for inspection.
    """
    smtp_calls = []

    class MockSMTP:
        """Mock SMTP server for testing"""

        def __init__(self, host, port, local_hostname=None):
            self.host = host
            self.port = port
            self.local_hostname = local_hostname

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            """Mock starttls"""

        def login(self, user, password):
            """Mock login"""

        def sendmail(self, from_addr, to_addrs, msg):
            """Record sendmail call"""
            smtp_calls.append(
                {"from_addr": from_addr, "to_addrs": to_addrs, "msg": msg, "msg_parsed": msg}
            )

    monkeypatch.setattr("castmail2list.mailer.smtplib.SMTP", MockSMTP)
    return smtp_calls


def create_test_message(
    subject: str = "Test Subject",
    from_email: str = "sender@example.com",
    from_name: str = "Sender Name",
    to_addrs: tuple[str, ...] = ("broadcast@example.com",),
    cc_addrs: tuple[str, ...] = (),
    body_text: str = "Test plain text body",
    body_html: str = "",  # pylint: disable=unused-argument
    message_id: str = "<test@example.com>",
) -> MailMessage:
    """Helper to create test MailMessage objects"""
    # Build raw email
    raw_parts = [
        f"From: {from_name} <{from_email}>" if from_name else f"From: {from_email}",
        f"To: {', '.join(to_addrs)}",
    ]
    if cc_addrs:
        raw_parts.append(f"Cc: {', '.join(cc_addrs)}")
    raw_parts.extend(
        [
            f"Subject: {subject}",
            f"Message-ID: {message_id}",
            "Date: Mon, 01 Jan 2024 12:00:00 +0000",
            "",
            body_text,
        ]
    )
    raw = "\n".join(raw_parts).encode()

    msg = MailMessage.from_bytes(raw)
    msg.uid = "test-uid"  # type: ignore[attr-defined]
    return msg


# ==================== Tests for Broadcast Mode ====================


def test_broadcast_basic_headers(client, broadcast_list: MailingList):
    """Test basic header composition in broadcast mode"""
    msg = create_test_message()
    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com", name="Sub One")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Check From header - should be list address (no from_addr set)
    assert mail.from_header == "broadcast@example.com"

    # Check Reply-To - should be empty in broadcast mode
    assert mail.reply_to == ""

    # Check X-MailFrom - should not be set in broadcast mode
    assert mail.x_mailfrom_header == ""

    # Check common headers
    assert mail.composed_msg is not None
    assert mail.composed_msg["From"] == "broadcast@example.com"
    assert mail.composed_msg["Sender"] == "broadcast@example.com"
    assert mail.composed_msg["Message-ID"] == "<new-msg-id@example.com>"
    assert mail.composed_msg["Original-Message-ID"] == "<test@example.com>"
    assert mail.composed_msg["X-Mailer"] == "CastMail2List"
    assert mail.composed_msg["List-Id"] == "<broadcast.example.com>"
    assert mail.composed_msg["Precedence"] == "list"
    assert "Reply-To" not in mail.composed_msg


def test_broadcast_with_custom_from(client, broadcast_list_with_from: MailingList):
    """Test broadcast mode with custom from_addr"""
    msg = create_test_message(to_addrs=("broadcast-from@example.com",))
    subscribers = [Subscriber(list_id=broadcast_list_with_from.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list_with_from,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # From should be the custom from_addr
    assert mail.from_header == "custom@example.com"
    assert mail.composed_msg["From"] == "custom@example.com"
    assert mail.composed_msg["Sender"] == "broadcast-from@example.com"


def test_broadcast_removes_list_from_to_cc(client, broadcast_list: MailingList):
    """Test that list address is removed from To and Cc in broadcast mode"""
    msg = create_test_message(
        to_addrs=("broadcast@example.com", "other@example.com"),
        cc_addrs=("broadcast@example.com", "cc@example.com"),
    )
    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # List address should be removed from To and Cc
    assert "broadcast@example.com" not in mail.msg.to
    assert "other@example.com" in mail.msg.to
    assert "broadcast@example.com" not in mail.msg.cc
    assert "cc@example.com" in mail.msg.cc


def test_broadcast_avoid_duplicates(client, broadcast_list: MailingList, smtp_mock):
    """Test avoid_duplicates in broadcast mode skips recipients in To/Cc"""
    msg = create_test_message(to_addrs=("broadcast@example.com", "sub1@example.com"))

    # Create subscriber who is already in To header
    subscriber = Subscriber(list_id=broadcast_list.id, email="sub1@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    # Send to recipient
    result = mail.send_email_to_recipient("sub1@example.com")

    # Should return empty bytes (skipped)
    assert result == b""
    assert len(smtp_mock) == 0  # No SMTP call made


def test_broadcast_no_avoid_duplicates(client, broadcast_list_no_avoid_dup: MailingList, smtp_mock):
    """Test that without avoid_duplicates, recipients in To/Cc still receive mail"""
    msg = create_test_message(to_addrs=("broadcast-nodup@example.com", "sub1@example.com"))

    subscriber = Subscriber(list_id=broadcast_list_no_avoid_dup.id, email="sub1@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=broadcast_list_no_avoid_dup,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    # Send to recipient
    result = mail.send_email_to_recipient("sub1@example.com")

    # Should send normally
    assert result != b""
    assert len(smtp_mock) == 1


def test_broadcast_recipient_appended_to_to(
    client, broadcast_list: MailingList, smtp_mock  # pylint: disable=unused-argument
):
    """Test that in broadcast mode, recipient is appended to To header"""
    msg = create_test_message(to_addrs=("broadcast@example.com", "other@example.net"))

    subscriber = Subscriber(list_id=broadcast_list.id, email="newrecipient@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    # Send to recipient
    result = mail.send_email_to_recipient("newrecipient@example.com")

    # Verify recipient was added to msg.to
    assert "newrecipient@example.com" in mail.msg.to
    assert "newrecipient@example.com" in result.decode()

    # Original other recipient should still be present
    assert "other@example.net" in mail.msg.to
    assert "other@example.net" in result.decode()


# ==================== Tests for Group Mode ====================


def test_group_basic_headers(client, group_list: MailingList):
    """Test basic header composition in group mode"""
    msg = create_test_message(
        to_addrs=("group@example.com",),
    )

    # Sender is NOT in subscriber list, so Reply-To will include sender
    subscribers = [Subscriber(list_id=group_list.id, email="sub1@example.com", name="Sub One")]

    mail = Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # From header should be "Sender Name via Group List <group@example.com>"
    assert mail.from_header == "Sender Name via Group List <group@example.com>"
    assert mail.composed_msg["From"] == "Sender Name via Group List <group@example.com>"

    # X-MailFrom should be set to original sender
    assert mail.x_mailfrom_header == "sender@example.com"
    assert mail.composed_msg["X-MailFrom"] == "sender@example.com"

    # Reply-To should include sender and list (sender is NOT a subscriber)
    assert mail.reply_to == "sender@example.com, group@example.com"
    assert mail.composed_msg["Reply-To"] == "sender@example.com, group@example.com"

    # Sender should still be list address
    assert mail.composed_msg["Sender"] == "group@example.com"


def test_group_from_with_no_name(client, group_list):
    """Test group mode From header when sender has no display name"""
    msg = create_test_message(
        from_email="sender@example.com", from_name="", to_addrs=("group@example.com",)
    )

    subscribers = [Subscriber(list_id=group_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Should use email when name is missing
    assert "sender@example.com via Group List <group@example.com>" in mail.from_header


def test_group_reply_to_when_sender_not_subscriber(client, group_list):
    """Test Reply-To includes sender when sender is not a subscriber"""
    msg = create_test_message(
        from_email="external@example.com", from_name="External", to_addrs=("group@example.com",)
    )

    # Subscriber list does NOT include external@example.com
    subscribers = [Subscriber(list_id=group_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Reply-To should include both sender and list
    assert mail.reply_to == "external@example.com, group@example.com"
    assert mail.composed_msg["Reply-To"] == "external@example.com, group@example.com"


def test_group_reply_to_when_sender_is_subscriber(client, group_list):
    """Test Reply-To is just list address when sender is a subscriber"""
    msg = create_test_message(
        from_email="sub1@example.com", from_name="Sub One", to_addrs=("group@example.com",)
    )

    # Subscriber list includes the sender
    subscribers = [Subscriber(list_id=group_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Reply-To should only be list address
    assert mail.reply_to == "group@example.com"
    assert mail.composed_msg["Reply-To"] == "group@example.com"


def test_group_no_from_values_error(client, group_list: MailingList, caplog):
    """Test that group mode logs error when from_values is missing"""
    # Create a message without proper From header
    raw = b"To: group@example.com\nSubject: No From\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "no-from"  # type: ignore[attr-defined]

    subscribers = [Subscriber(list_id=group_list.id, email="sub1@example.com")]

    Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Should log an error
    assert "No valid From header" in caplog.text


def test_group_to_header_preserved(
    client, group_list: MailingList, smtp_mock  # pylint: disable=unused-argument
):
    """Test that in group mode, original To/Cc are preserved without per-recipient mutation"""
    msg = create_test_message(to_addrs=("original@example.com",), cc_addrs=("cc@example.com",))

    subscriber = Subscriber(list_id=group_list.id, email="newrecipient@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    # Before sending
    original_to = mail.msg.to

    # Send to recipient
    mail.send_email_to_recipient("newrecipient@example.com")

    # Verify msg.to was NOT mutated (no recipient append in group mode)
    assert mail.msg.to == original_to
    assert "newrecipient@example.com" not in mail.msg.to


# ==================== Tests for Common Headers ====================


def test_threading_headers(client, broadcast_list: MailingList):
    """Test that threading headers (In-Reply-To, References) are preserved"""
    raw = (
        b"From: sender@example.com\n"
        b"To: broadcast@example.com\n"
        b"Subject: Re: Thread\n"
        b"Message-ID: <reply@example.com>\n"
        b"In-Reply-To: <original@example.com>\n"
        b"References: <first@example.com> <original@example.com>\n"
        b"\n"
        b"Reply body"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "reply"  # type: ignore[attr-defined]

    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Check In-Reply-To
    assert mail.composed_msg["In-Reply-To"] == "<original@example.com>"

    # Check References includes original references plus original message-id
    refs = mail.composed_msg["References"]
    assert "<first@example.com>" in refs
    assert "<original@example.com>" in refs
    assert "<reply@example.com>" in refs


def test_cc_header_preserved(client, broadcast_list: MailingList):
    """Test that Cc header is preserved in outgoing message"""
    msg = create_test_message(cc_addrs=("cc1@example.com", "cc2@example.com"))

    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    assert "cc1@example.com" in mail.composed_msg["Cc"]
    assert "cc2@example.com" in mail.composed_msg["Cc"]


def test_x_recipient_header(
    client, broadcast_list: MailingList, smtp_mock
):  # pylint: disable=unused-argument
    """Test that X-Recipient header is set per recipient"""
    msg = create_test_message()

    subscriber = Subscriber(list_id=broadcast_list.id, email="specific@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    mail.send_email_to_recipient("specific@example.com")

    # Check X-Recipient was set
    assert mail.composed_msg["X-Recipient"] == "specific@example.com"


def test_envelope_from_is_bounce_address(client, broadcast_list: MailingList, smtp_mock):
    """Test that SMTP envelope-from uses bounce address format"""
    msg = create_test_message()

    subscriber = Subscriber(list_id=broadcast_list.id, email="recipient@example.com")
    db.session.add(subscriber)
    db.session.commit()

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=[subscriber],
    )

    mail.send_email_to_recipient("recipient@example.com")

    # Check SMTP call used bounce address as envelope-from
    assert len(smtp_mock) == 1
    envelope_from = smtp_mock[0]["from_addr"]
    # Should be in format: broadcast+<hash>-recipient=example.com@example.com
    assert envelope_from.startswith("broadcast+")
    assert "recipient=example.com" in envelope_from


# ==================== Tests for Message Body and Attachments ====================


def test_multipart_alternative_text_and_html(client, broadcast_list: MailingList):
    """Test that messages with both text and html use multipart/alternative"""
    raw = (
        b"From: sender@example.com\n"
        b"To: broadcast@example.com\n"
        b"Subject: Multipart Test\n"
        b"MIME-Version: 1.0\n"
        b"Content-Type: multipart/alternative; boundary=boundary123\n"
        b"\n"
        b"--boundary123\n"
        b"Content-Type: text/plain\n"
        b"\n"
        b"Plain text version\n"
        b"--boundary123\n"
        b"Content-Type: text/html\n"
        b"\n"
        b"<p>HTML version</p>\n"
        b"--boundary123--\n"
    )
    msg = MailMessage.from_bytes(raw)
    msg.uid = "multipart"  # type: ignore[attr-defined]

    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Should use MIMEMultipart
    assert mail.composed_msg is not None
    assert mail.composed_msg.is_multipart()


def test_simple_text_message(client, broadcast_list: MailingList):
    """Test simple text-only message"""
    msg = create_test_message(body_text="Simple text body")

    subscribers = [Subscriber(list_id=broadcast_list.id, email="sub1@example.com")]

    mail = Mail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Should not be multipart for simple text
    assert mail.composed_msg is not None
    # Could be multipart or simple depending on implementation
    # Just verify it contains the text
    msg_str = mail.composed_msg.as_string()
    assert "Simple text body" in msg_str


# ==================== Tests for send_msg_to_subscribers Integration ====================


def test_send_msg_to_subscribers_success(
    client, broadcast_list: MailingList, mailbox_stub, smtp_mock
):
    """Test full send_msg_to_subscribers workflow"""
    msg = create_test_message()

    # Add subscribers
    sub1 = Subscriber(list_id=broadcast_list.id, email="sub1@example.com")
    sub2 = Subscriber(list_id=broadcast_list.id, email="sub2@example.com")
    db.session.add_all([sub1, sub2])
    db.session.commit()

    # Mock mailbox.append to avoid IMAP operations
    mailbox_stub.append = MagicMock()

    sent_successful, sent_failed = send_msg_to_subscribers(
        app=client.application, msg=msg, ml=broadcast_list, mailbox=mailbox_stub
    )

    # Should have sent to both subscribers
    assert len(sent_successful) == 2
    assert len(sent_failed) == 0
    assert "sub1@example.com" in sent_successful
    assert "sub2@example.com" in sent_successful

    # Should have made 2 SMTP calls
    assert len(smtp_mock) == 2


def test_send_msg_deepcopy_prevents_cross_contamination(
    client, broadcast_list: MailingList, mailbox_stub, smtp_mock
):
    """Test that deepcopy prevents header cross-contamination between recipients"""
    msg = create_test_message()

    # Add two subscribers
    sub1 = Subscriber(list_id=broadcast_list.id, email="sub1@example.com")
    sub2 = Subscriber(list_id=broadcast_list.id, email="sub2@example.com")
    db.session.add_all([sub1, sub2])
    db.session.commit()

    mailbox_stub.append = MagicMock()

    send_msg_to_subscribers(
        app=client.application, msg=msg, ml=broadcast_list, mailbox=mailbox_stub
    )

    # Parse the sent messages to verify X-Recipient is unique
    recipients_found: list[str] = []
    for call in smtp_mock:
        msg_parsed = email.message_from_string(call["msg"])
        recipients_found.append(msg_parsed["X-Recipient"])

    # Each message should have correct X-Recipient
    assert len(recipients_found) == 2
    assert "sub1@example.com" in recipients_found
    assert "sub2@example.com" in recipients_found


def test_send_msg_stores_in_sent_folder(
    client, broadcast_list: MailingList, mailbox_stub, smtp_mock  # pylint: disable=unused-argument
):
    """Test that successfully sent messages are stored in IMAP Sent folder"""
    msg = create_test_message()

    sub1 = Subscriber(list_id=broadcast_list.id, email="sub1@example.com")
    db.session.add(sub1)
    db.session.commit()

    # Mock mailbox.append
    append_calls = []

    def mock_append(message, folder, flag_set):
        append_calls.append({"message": message, "folder": folder, "flag_set": flag_set})

    mailbox_stub.append = mock_append

    send_msg_to_subscribers(
        app=client.application, msg=msg, ml=broadcast_list, mailbox=mailbox_stub
    )

    # Should have appended to Sent folder
    assert len(append_calls) == 1
    assert append_calls[0]["folder"] == client.application.config["IMAP_FOLDER_SENT"]
    assert "\\Seen" in append_calls[0]["flag_set"]


def test_unknown_mode_logs_error(client, caplog, monkeypatch):
    """Test that unknown list mode logs error"""
    # Create a valid list
    ml = MailingList(
        name="Test List",
        address="test@example.com",
        mode="broadcast",
        imap_host="mail.example.com",
        imap_port=993,
        imap_user="user",
        imap_pass="pass",
    )
    db.session.add(ml)
    db.session.commit()

    # Mock the mode property to return invalid value
    monkeypatch.setattr(type(ml), "mode", property(lambda self: "invalid-mode"))

    msg = create_test_message()
    subscribers = [Subscriber(list_id=ml.id, email="sub1@example.com")]

    Mail(
        app=client.application,
        ml=ml,
        msg=msg,
        message_id="<new-msg-id@example.com>",
        subscribers=subscribers,
    )

    # Should log an error
    assert "Unknown list mode" in caplog.text
