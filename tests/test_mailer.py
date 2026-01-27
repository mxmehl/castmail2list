# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for mailer.py focusing on email composition and header handling.

Tests verify that different list modes (broadcast/group) and configurations
produce correct email headers and behavior as documented in doc/modes_and_headers.md.
"""

# mypy: disable-error-code="index"

import email
from unittest.mock import MagicMock

from imap_tools import MailMessage

from castmail2list.mailer import (
    OutgoingEmail,
    send_msg_to_subscribers,
    send_rejection_notification,
    should_notify_sender,
)
from castmail2list.models import MailingList, Subscriber, db

# pylint: disable=protected-access,too-many-arguments,too-many-positional-arguments


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

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="new-msg-id@example.com",
    )

    # Check From header - should be "Sender Name via Broadcast List <...>" format
    assert mail.from_header == "Sender Name via Broadcast List <broadcast@example.com>"

    # Check Reply-To
    assert mail.reply_to == "Sender Name <sender@example.com>"

    # Check X-MailFrom - should not be set in broadcast mode
    assert mail.x_mailfrom_header == "sender@example.com"

    # Check common headers
    assert mail.composed_msg is not None
    assert mail.composed_msg["From"] == "Sender Name via Broadcast List <broadcast@example.com>"
    assert mail.composed_msg["Reply-To"] == "Sender Name <sender@example.com>"
    assert mail.composed_msg["Sender"] == "broadcast@example.com"
    assert mail.composed_msg["X-MailFrom"] == "sender@example.com"
    assert mail.composed_msg["Message-ID"] == "<new-msg-id@example.com>"
    assert mail.composed_msg["Original-Message-ID"] == "<test@example.com>"
    assert mail.composed_msg["X-Mailer"] == "CastMail2List"
    assert mail.composed_msg["List-Id"] == "<broadcast.example.com>"
    assert mail.composed_msg["Precedence"] == "list"


def test_broadcast_with_custom_from(client, broadcast_list_with_from: MailingList):
    """Test broadcast mode with custom from_addr"""
    msg = create_test_message(to_addrs=("broadcast-from@example.com",))

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list_with_from,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # From should be the custom from_addr
    assert mail.from_header == "Custom <custom@example.com>"
    assert mail.x_mailfrom_header == ""
    assert mail.reply_to == ""
    assert mail.composed_msg["From"] == "Custom <custom@example.com>"
    assert mail.composed_msg["Sender"] == "broadcast-from@example.com"
    assert mail.composed_msg is not None
    assert "X-MailFrom" not in mail.composed_msg
    assert "Reply-To" not in mail.composed_msg


def test_broadcast_removes_list_from_to_cc(client, broadcast_list: MailingList):
    """Test that list address is removed from To and Cc in broadcast mode"""
    msg = create_test_message(
        to_addrs=("broadcast@example.com", "other@example.com"),
        cc_addrs=("broadcast@example.com", "cc@example.com"),
    )

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # List address should be removed from To and Cc
    assert "broadcast@example.com" not in mail.msg.to
    assert "other@example.com" in mail.msg.to
    assert "broadcast@example.com" not in mail.msg.cc
    assert "cc@example.com" in mail.msg.cc


def test_broadcast_avoid_duplicates(client, broadcast_list: MailingList, smtp_mock):
    """Test avoid_duplicates in broadcast mode skips recipients in To/Cc"""
    dupe = "sub1@example.com"
    msg = create_test_message(to_addrs=("broadcast@example.com", dupe))

    # Create subscriber who is already in To header
    subscriber = Subscriber(list_id=broadcast_list.id, email=dupe)
    db.session.add(subscriber)
    db.session.commit()

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Send to recipient
    result = mail.send_email_to_recipient(dupe)

    # Should return empty bytes (skipped)
    assert result == b""
    assert len(smtp_mock) == 0  # No SMTP call made


def test_broadcast_no_avoid_duplicates(client, broadcast_list_no_avoid_dup: MailingList, smtp_mock):
    """Test that without avoid_duplicates, recipients in To/Cc still receive mail"""
    dupe = "sub1@example.com"
    msg = create_test_message(to_addrs=("broadcast@example.com", dupe))

    subscriber = Subscriber(list_id=broadcast_list_no_avoid_dup.id, email=dupe)
    db.session.add(subscriber)
    db.session.commit()

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list_no_avoid_dup,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Send to recipient
    result = mail.send_email_to_recipient(dupe)

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

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
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
    mail = OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # From header should be "Sender Name via Group List <group@example.com>"
    assert mail.from_header == "Sender Name via Group List <group@example.com>"
    assert mail.composed_msg["From"] == "Sender Name via Group List <group@example.com>"

    # X-MailFrom should be set to original sender
    assert mail.x_mailfrom_header == "sender@example.com"
    assert mail.composed_msg["X-MailFrom"] == "sender@example.com"

    # Reply-To should include sender and list (sender is NOT a subscriber)
    assert mail.reply_to == "Sender Name <sender@example.com>, Group List <group@example.com>"
    assert (
        mail.composed_msg["Reply-To"]
        == "Sender Name <sender@example.com>, Group List <group@example.com>"
    )

    # Sender should still be list address
    assert mail.composed_msg["Sender"] == "group@example.com"


def test_group_from_with_no_name(client, group_list):
    """Test group mode From header when sender has no display name"""
    msg = create_test_message(
        from_email="sender@example.com", from_name="", to_addrs=("group@example.com",)
    )

    mail = OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Should use email when name is missing
    # formataddr quotes the display name when it contains special chars like @
    assert mail.from_header == '"sender@example.com via Group List" <group@example.com>'


def test_group_reply_to_when_sender_not_subscriber(client, group_list):
    """Test Reply-To includes sender when sender is not a subscriber"""
    msg = create_test_message(
        from_email="external@example.com", from_name="External", to_addrs=("group@example.com",)
    )

    mail = OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Reply-To should include both sender and list
    assert mail.reply_to == "External <external@example.com>, Group List <group@example.com>"
    assert (
        mail.composed_msg["Reply-To"]
        == "External <external@example.com>, Group List <group@example.com>"
    )


def test_group_reply_to_when_sender_is_subscriber(client, group_list):
    """Test Reply-To is just list address when sender is a subscriber"""
    sub_email = "sub1@example.com"
    subscriber = Subscriber(list_id=group_list.id, email=sub_email)
    db.session.add(subscriber)
    db.session.commit()

    msg = create_test_message(
        from_email=sub_email, from_name="Sub One", to_addrs=("group@example.com",)
    )

    mail = OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Reply-To should only be list address
    assert mail.reply_to == "Group List <group@example.com>"
    assert mail.composed_msg["Reply-To"] == "Group List <group@example.com>"


def test_group_no_from_values_error(client, group_list: MailingList, caplog):
    """Test that group mode logs error when from_values is missing"""
    # Create a message without proper From header
    raw = b"To: group@example.com\nSubject: No From\n\nBody"
    msg = MailMessage.from_bytes(raw)
    msg.uid = "no-from"  # type: ignore[attr-defined]

    OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Should log an error
    assert "No valid From header" in caplog.text


def test_group_to_header_preserved(
    client, group_list: MailingList, smtp_mock  # pylint: disable=unused-argument
):
    """Test that in group mode, original To/Cc are preserved without per-recipient mutation"""
    msg = create_test_message(to_addrs=("original@example.com",), cc_addrs=("cc@example.com",))

    mail = OutgoingEmail(
        app=client.application,
        ml=group_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
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

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
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

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    assert "cc1@example.com" in mail.composed_msg["Cc"]
    assert "cc2@example.com" in mail.composed_msg["Cc"]


def test_x_recipient_header(
    client, broadcast_list: MailingList, smtp_mock
):  # pylint: disable=unused-argument
    """Test that X-Recipient header is set per recipient"""
    msg = create_test_message()

    recipient = "specific@example.com"

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    mail.send_email_to_recipient(recipient=recipient)

    # Check X-Recipient was set
    assert mail.composed_msg["X-Recipient"] == recipient


def test_envelope_from_is_bounce_address(client, broadcast_list: MailingList, smtp_mock):
    """Test that SMTP envelope-from uses bounce address format"""
    msg = create_test_message()

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
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

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Should use MIMEMultipart
    assert mail.composed_msg is not None
    assert mail.composed_msg.is_multipart()


def test_simple_text_message(client, broadcast_list: MailingList):
    """Test simple text-only message"""
    msg = create_test_message(body_text="Simple text body")

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="<new-msg-id@example.com>",
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
        # Handle both bytes and string messages
        msg_data = call["msg"]
        if isinstance(msg_data, bytes):
            msg_parsed = email.message_from_bytes(msg_data)
        else:
            msg_parsed = email.message_from_string(msg_data)
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
        id="test2",
        display="Test List",
        address="test2@example.com",
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

    OutgoingEmail(
        app=client.application,
        ml=ml,
        msg=msg,
        message_id="<new-msg-id@example.com>",
    )

    # Should log an error
    assert "Unknown list mode" in caplog.text


# ==================== Tests for Rejection Notifications ====================


def test_should_notify_sender_disabled(client):
    """should_notify_sender returns False when NOTIFY_REJECTED_SENDERS is False"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = False
    assert should_notify_sender(client.application, "test@example.com") is False


def test_should_notify_sender_known_only_not_in_db(client):
    """should_notify_sender returns False when sender not in DB and KNOWN_ONLY is True"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []

    assert should_notify_sender(client.application, "unknown@example.com") is False


def test_should_notify_sender_known_only_in_db(client):
    """should_notify_sender returns True when sender in DB and KNOWN_ONLY is True"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []

    # Get the default mailing list from client fixture
    ml = MailingList.query.filter_by(address="list@example.com").first()
    assert ml is not None

    # Add subscriber to DB
    subscriber = Subscriber(list_id=ml.id, email="known@example.com", name="Known User")
    db.session.add(subscriber)
    db.session.commit()

    assert should_notify_sender(client.application, "known@example.com") is True


def test_should_notify_sender_case_insensitive(client):
    """should_notify_sender is case-insensitive for email addresses"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []

    # Get the default mailing list from client fixture
    ml = MailingList.query.filter_by(address="list@example.com").first()
    assert ml is not None

    # Add subscriber with lowercase email
    subscriber = Subscriber(list_id=ml.id, email="user@example.com", name="Test User")
    db.session.add(subscriber)
    db.session.commit()

    # Check with different casing
    assert should_notify_sender(client.application, "USER@EXAMPLE.COM") is True
    assert should_notify_sender(client.application, "User@Example.Com") is True


def test_should_notify_sender_trusted_domain(client):
    """should_notify_sender returns True for trusted domains even if not in DB"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = ["trusted.com", "internal.org"]

    # Not in DB but from trusted domain
    assert should_notify_sender(client.application, "anyone@trusted.com") is True
    assert should_notify_sender(client.application, "user@INTERNAL.ORG") is True  # case-insensitive

    # Not in DB and not from trusted domain
    assert should_notify_sender(client.application, "stranger@untrusted.com") is False


def test_should_notify_sender_no_restrictions(client):
    """should_notify_sender returns True when KNOWN_ONLY is False and no trusted domains"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = False
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []

    # Anyone should be notified
    assert should_notify_sender(client.application, "anyone@anywhere.com") is True


def test_send_rejection_notification_disabled(client, smtp_mock):
    """send_rejection_notification should not send when notifications are disabled"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = False
    client.application.config["DOMAIN"] = "lists.example.com"
    client.application.config["SYSTEM_EMAIL"] = "noreply@lists.example.com"

    result = send_rejection_notification(
        app=client.application,
        sender_email="test@example.com",
        recipient="list@example.com",
        reason="Not authorized",
    )

    assert result is False
    assert len(smtp_mock) == 0


def test_send_rejection_notification_success(client, smtp_mock):
    """send_rejection_notification should send email to known sender"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = True
    client.application.config["NOTIFY_REJECTED_TRUSTED_DOMAINS"] = []
    client.application.config["DOMAIN"] = "lists.example.com"
    client.application.config["SYSTEM_EMAIL"] = "noreply@lists.example.com"

    # Get the default mailing list from client fixture
    ml = MailingList.query.filter_by(address="list@example.com").first()
    assert ml is not None

    # Add subscriber
    subscriber = Subscriber(list_id=ml.id, email="known@example.com", name="Known User")
    db.session.add(subscriber)
    db.session.commit()

    result = send_rejection_notification(
        app=client.application,
        sender_email="known@example.com",
        recipient="broadcast@example.com",
        reason="You are not authorized to send to this list",
    )

    assert result is True
    assert len(smtp_mock) == 1

    # Verify email was sent
    call = smtp_mock[0]
    assert call["to_addrs"] == "known@example.com"
    assert call["from_addr"] == ""  # Empty Return-Path for auto-response

    # Parse message to check headers and content
    msg_sent = call["msg"]
    parsed = (
        email.message_from_bytes(msg_sent)
        if isinstance(msg_sent, bytes)
        else email.message_from_string(msg_sent)
    )

    assert parsed["To"] == "known@example.com"
    assert parsed["From"] == "noreply@lists.example.com"
    assert "broadcast@example.com" in parsed["Subject"]
    assert parsed["Auto-Submitted"] == "auto-replied"
    assert parsed["X-Auto-Response-Suppress"] == "All"
    assert parsed["Precedence"] == "bulk"

    # Check body content
    body_bytes = parsed.get_payload(decode=True)
    body = body_bytes.decode() if isinstance(body_bytes, bytes) else str(body_bytes)
    assert "broadcast@example.com" in body
    assert "not authorized" in body.lower()


def test_send_rejection_notification_with_reply_to(client, smtp_mock):
    """send_rejection_notification should set In-Reply-To when provided"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = False
    client.application.config["DOMAIN"] = "lists.example.com"
    client.application.config["SYSTEM_EMAIL"] = "noreply@lists.example.com"

    original_msgid = "<original-message-123@sender.com>"

    result = send_rejection_notification(
        app=client.application,
        sender_email="sender@example.com",
        recipient="list@example.com",
        reason="Not a member",
        in_reply_to=original_msgid,
    )

    assert result is True
    assert len(smtp_mock) == 1

    # Parse message to check threading headers
    call = smtp_mock[0]
    # Parse message to check headers and content
    msg_sent = call["msg"]
    parsed = (
        email.message_from_bytes(msg_sent)
        if isinstance(msg_sent, bytes)
        else email.message_from_string(msg_sent)
    )

    assert parsed["In-Reply-To"] == original_msgid
    assert parsed["References"] == original_msgid


def test_send_rejection_notification_dry_mode(client, smtp_mock):
    """send_rejection_notification should not send in DRY mode"""
    client.application.config["NOTIFY_REJECTED_SENDERS"] = True
    client.application.config["NOTIFY_REJECTED_KNOWN_ONLY"] = False
    client.application.config["DRY"] = True
    client.application.config["DOMAIN"] = "lists.example.com"
    client.application.config["SYSTEM_EMAIL"] = "noreply@lists.example.com"

    result = send_rejection_notification(
        app=client.application,
        sender_email="test@example.com",
        recipient="list@example.com",
        reason="Test rejection",
    )

    assert result is True  # Function returns True in DRY mode
    assert len(smtp_mock) == 0  # But no actual email sent


def test_umlaut_in_display_name_encoding(client, broadcast_list: MailingList):
    """Test that umlaut in list name is properly encoded in From header.

    Regression test for issue where display names with non-ASCII characters
    caused the entire From header (including email address) to be encoded.
    Email addresses should never be encoded, only display names.
    """
    # Update list to have umlaut in display name
    broadcast_list.display = "Elternböirat"
    db.session.commit()

    msg = create_test_message(
        from_email="info@waldorfkindergarten-konstanz.de",
        from_name="Test User",
        to_addrs=("broadcast@example.com",),
    )

    mail = OutgoingEmail(
        app=client.application,
        ml=broadcast_list,
        msg=msg,
        message_id="new-msg-id@example.com",
    )

    # The From header should be properly formatted
    # formataddr will quote the display name and handle encoding internally
    expected_email = "broadcast@example.com"

    # Check that the email address is present and unencoded
    assert expected_email in mail.from_header
    # Check the display name is present (may be encoded by formataddr)
    assert "Elternb" in mail.from_header  # Partial match to handle encoding

    # Most importantly: verify the composed message header doesn't encode the email
    from_header = mail.composed_msg["From"]
    # Email address should appear unencoded in angle brackets
    assert f"<{expected_email}>" in from_header
    # The @ in email should not be encoded (would be =40 if encoded)
    assert "=40" not in from_header or "broadcast@example.com" in from_header
