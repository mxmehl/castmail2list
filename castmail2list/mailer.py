"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
import tempfile
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from flask import Flask, render_template
from flask_babel import _
from imap_tools import MailBox
from imap_tools.message import MailMessage

from .models import EmailOut, MailingList, Subscriber, db
from .utils import (
    create_bounce_address,
    create_log_entry,
    generate_via_from_header,
    get_list_recipients_recursive,
    get_message_id_from_incoming,
    reply_to_from_email_and_name,
)


def send_email_via_smtp(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_starttls: bool,
    message: bytes,
    from_addr: str,
    to_addrs: str,
    local_hostname: str | None = None,
) -> None:
    """
    Send an email via SMTP with the given configuration.

    Args:
        smtp_host (str): SMTP server hostname
        smtp_port (int): SMTP server port
        smtp_user (str): SMTP username for authentication
        smtp_password (str): SMTP password for authentication
        smtp_starttls (bool): Whether to use STARTTLS
        message (str): Email message to send
        from_addr (str): Sender address (for sendmail method)
        to_addrs (str): Recipient address(es) (for sendmail method)
        local_hostname (str | None): Optional local hostname for SMTP connection

    Raises:
        Exception: If sending fails
    """
    with smtplib.SMTP(smtp_host, smtp_port, local_hostname=local_hostname) as server:
        if smtp_starttls:
            server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.sendmail(from_addr=from_addr, to_addrs=to_addrs, msg=message)


class OutgoingEmail:  # pylint: disable=too-many-instance-attributes
    """Class for an email sent to multiple recipients via SMTP"""

    def __init__(  # pylint: disable=too-many-arguments, too-many-positional-arguments
        self,
        app: Flask,
        ml: MailingList,
        msg: MailMessage,
        message_id: str,
    ) -> None:
        # Relevant settings from app config
        self.app_domain: str = app.config["DOMAIN"]
        self.smtp_server: str = app.config["SMTP_HOST"]
        self.smtp_port: int = int(app.config["SMTP_PORT"])
        self.smtp_user: str = app.config["SMTP_USER"]
        self.smtp_password: str = app.config["SMTP_PASS"]
        self.smtp_starttls: bool = app.config["SMTP_STARTTLS"]
        # Arguments as class attributes
        self.message_id: str = message_id
        self.ml: MailingList = ml
        self.msg: MailMessage = msg
        self.subscribers_emails: list[str] = list(get_list_recipients_recursive(ml.id).keys())
        # Additional attributes we need for sending
        self.composed_msg: MIMEMultipart | MIMEText | None = None
        self.from_header: str = ""
        self.reply_to: str = ""
        self.original_mid: str = next(iter(self.msg.headers.get("message-id", ())), "")
        self.x_mailfrom_header: str = ""

        # Initialize message container type, common headers, and body parts
        self.choose_container_type()
        self.prepare_common_headers()
        self.add_body_parts()

    def __deepcopy__(self, memo):
        """
        Custom deepcopy to avoid detaching SQLAlchemy objects from session.

        Only deep copies msg and composed_msg to prevent cross-contamination between
        recipients. All other attributes are either shallow-copied (immutable) or kept
        as references (SQLAlchemy objects that must stay attached to the session).
        """
        # Create a new instance without calling __init__
        cls = self.__class__
        new_obj = cls.__new__(cls)

        # Define which attributes should NOT be deep copied
        no_deepcopy = {"ml", "subscribers"}  # SQLAlchemy objects - keep as references
        deepcopy_these = {"msg", "composed_msg"}  # Must be independent per recipient

        # Copy all attributes
        for key, value in self.__dict__.items():
            if key in deepcopy_these:
                # Deep copy to avoid cross-contamination
                setattr(new_obj, key, deepcopy(value, memo))
            elif key in no_deepcopy:
                # Keep reference (don't copy SQLAlchemy objects)
                setattr(new_obj, key, value)
            else:
                # Shallow copy (immutable types like str, int are safe)
                setattr(new_obj, key, value)

        return new_obj

    def choose_container_type(self) -> None:
        """Choose the correct container type for the email based on its content"""
        # If there are attachments, use multipart/mixed
        if self.msg.attachments:
            self.composed_msg = MIMEMultipart("mixed")
        # If both text and html parts exist, use multipart/alternative
        elif self.msg.text and self.msg.html:
            self.composed_msg = MIMEMultipart("alternative")
        # Otherwise, use simple MIMEText with either text or html, whichever exists
        else:
            self.composed_msg = MIMEText(
                self.msg.html or self.msg.text, "html" if self.msg.html else "plain"
            )

    def prepare_common_headers(self) -> None:  # pylint: disable=too-many-branches
        """Prepare common email headers, except To which is per-recipient"""
        # --- Sanity checks ---
        if not self.composed_msg:
            raise ValueError("Message container type not chosen yet")
        if not self.msg.from_values:
            logging.error("No valid From header in message %s, cannot send", self.msg.uid)
            return

        # --- Prepare From and Reply-To headers based on list mode ---
        if self.ml.mode == "broadcast":
            # From: Use the list's From address if set, otherwise use the via format
            self.from_header = self.ml.from_addr or generate_via_from_header(
                from_values=self.msg.from_values,
                ml_address=self.ml.address,
                ml_display=self.ml.display,
            )
            # Set Reply-To:
            # * If the list has a custom From address, no Reply-To is needed
            # * If not, set Reply-To to the original sender to allow direct replies. In this case,
            #   it is also set for the X-MailFrom header.
            if self.ml.from_addr:
                self.reply_to = ""
            else:
                self.reply_to = reply_to_from_email_and_name(
                    self.msg.from_values.email, self.msg.from_values.name
                )
                self.x_mailfrom_header = self.msg.from_values.email
            # Remove list address from To and CC headers to avoid confusion
            if self.ml.address in self.msg.to or self.ml.address in self.msg.cc:
                self.msg.to = tuple(addr for addr in self.msg.to if addr != self.ml.address)
                self.msg.cc = tuple(addr for addr in self.msg.cc if addr != self.ml.address)
        elif self.ml.mode == "group":
            # From: Use "Sender Name via List Name <list@address>" format
            self.from_header = generate_via_from_header(
                from_values=self.msg.from_values,
                ml_address=self.ml.address,
                ml_display=self.ml.display,
            )
            # Set Reply-To:
            # * Set to list address to avoid replies going to all subscribers
            # * If sender is not a recipient of the list, add them as Reply-To as well
            self.reply_to = reply_to_from_email_and_name(self.ml.address, self.ml.display)
            if self.msg.from_values.email not in self.subscribers_emails:
                self.reply_to = (
                    reply_to_from_email_and_name(
                        self.msg.from_values.email, self.msg.from_values.name
                    )
                    + ", "
                    + self.reply_to
                )
            # Add X-MailFrom with original sender address
            self.x_mailfrom_header = self.msg.from_values.email
        else:
            logging.error("Unknown list mode %s for list %s", self.ml.mode, self.ml.display)
            return

        # App
        self.composed_msg["X-Mailer"] = "CastMail2List"
        self.composed_msg["X-CastMail2List-Domain"] = self.app_domain
        # List-specific headers
        self.composed_msg["List-Id"] = f"<{self.ml.address.replace('@', '.')}>"
        self.composed_msg["Precedence"] = "list"
        # Sender
        self.composed_msg["From"] = self.from_header
        self.composed_msg["Sender"] = self.ml.address
        if self.x_mailfrom_header:
            self.composed_msg["X-MailFrom"] = self.x_mailfrom_header
        # Recipients
        if self.msg.cc:
            self.composed_msg["Cc"] = ", ".join(self.msg.cc)
        # Message
        self.composed_msg["Subject"] = self.msg.subject
        self.composed_msg["Message-ID"] = f"<{self.message_id}>"
        self.composed_msg["Date"] = self.msg.date_str or formatdate(localtime=True)
        self.composed_msg["Original-Message-ID"] = self.original_mid
        # Threading and references
        self.composed_msg["In-Reply-To"] = (
            self.msg.headers.get("in-reply-to", ())[0]
            if self.msg.headers.get("in-reply-to", ())
            else self.original_mid
        )
        self.composed_msg["References"] = " ".join(
            self.msg.headers.get("references", ()) + (self.original_mid,)
        )
        if self.reply_to:
            self.composed_msg["Reply-To"] = self.reply_to

    def add_body_parts(self) -> None:
        """Add body parts to the email message container"""
        if not self.composed_msg:
            raise ValueError("Message container type not chosen yet")

        if isinstance(self.composed_msg, MIMEMultipart):
            if self.msg.text and self.msg.html:
                # Combine text+html properly as an alternative part
                alt = MIMEMultipart("alternative")
                alt.attach(MIMEText(self.msg.text, "plain"))
                alt.attach(MIMEText(self.msg.html, "html"))
                self.composed_msg.attach(alt)
            elif self.msg.text:
                self.composed_msg.attach(MIMEText(self.msg.text, "plain"))
            elif self.msg.html:
                self.composed_msg.attach(MIMEText(self.msg.html, "html"))

            # Add attachments if any
            if self.msg.attachments:
                for attachment in self.msg.attachments:
                    part = MIMEBase(
                        attachment.content_type.split("/")[0], attachment.content_type.split("/")[1]
                    )
                    part.set_payload(attachment.payload)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'{attachment.content_disposition}; filename="{attachment.filename}"',
                    )
                    self.composed_msg.attach(part)

    def send_email_to_recipient(
        self,
        recipient: str,
        dry: bool = False,
    ) -> bytes:
        """
        Sends the mostly prepared list message to a recipient. Returns sent message as bytes.

        Args:
            recipient (str): Recipient email address
        Returns:
            bytes: Sent message as bytes
        """
        if self.composed_msg is None:
            logging.error("Message container not prepared, cannot send email to %s", recipient)
            return b""

        # --- Add per-recipient headers ---
        # Deal with recipient as possible To/Cc of original message
        if recipient in self.msg.to or recipient in self.msg.cc:
            if self.ml.avoid_duplicates:
                logging.info(
                    "Recipient %s already in To/Cc of original message. Skipping as the list is "
                    "configured to avoid duplicates.",
                    recipient,
                )
                return b""
        # In Broadcast mode: add recipient to To header if not already present
        if self.ml.mode == "broadcast" and recipient not in self.msg.to:
            self.msg.to += (recipient,)
        # Set To header: preserve original To addresses if any (minus the list address in some
        # configurations), and recipient in any case
        self.composed_msg["To"] = ", ".join(self.msg.to) if self.msg.to else recipient
        # Set X-Recipient header to ease debugging
        self.composed_msg["X-Recipient"] = recipient

        logging.debug("Email content: \n%s", self.composed_msg.as_string())

        # --- Send email ---
        if dry:
            logging.info(
                "[DRY MODE] Would send the email to %s. Use --debug to see full email content.",
                recipient,
            )
            return self.composed_msg.as_bytes()
        try:
            # Send the email
            send_email_via_smtp(
                smtp_host=self.smtp_server,
                smtp_port=self.smtp_port,
                smtp_user=self.smtp_user,
                smtp_password=self.smtp_password,
                smtp_starttls=self.smtp_starttls,
                message=self.composed_msg.as_bytes(),
                from_addr=create_bounce_address(ml_address=self.ml.address, recipient=recipient),
                to_addrs=recipient,
                local_hostname=self.ml.address.split("@")[-1],
            )
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to send email: %s\nTraceback: %s", e, traceback.format_exc())
            create_log_entry(
                level="error",
                event="email_out",
                message=f"Failed to send email to {recipient}: {e}",
                details={"recipient": recipient, "message_id": self.message_id},
                list_id=self.ml.id,
            )
            return b""

        return self.composed_msg.as_bytes()


def send_msg_to_subscribers(
    app: Flask, msg: MailMessage, ml: MailingList, mailbox: MailBox
) -> tuple[list[str], list[str]]:
    """
    Send message to all subscribers of a list. Stores sent message in Sent folder via IMAP.

    Args:
        app (Flask): Flask application instance
        msg (MailMessage): The incoming message to forward
        ml (MailingList): Mailing list to send to
        mailbox (MailBox): IMAP mailbox instance for storing sent messages

    Returns:
        tuple[list[str], list[str]]: Tuple of lists of successful and failed recipient email
            addresses
    """
    sent_successful: list[str] = []
    sent_failed: list[str] = []

    subscribers_emails: list[str] = list(get_list_recipients_recursive(ml.id).keys())
    logging.info(
        "Sending message %s to %d subscribers of list <%s>: %s",
        msg.uid,
        len(subscribers_emails),
        ml.address,
        ", ".join(subscribers_emails),
    )

    # Prepare message class
    new_msgid = make_msgid(idstring="castmail2list", domain=ml.address.split("@")[-1]).strip("<>")
    mail = OutgoingEmail(app=app, ml=ml, msg=msg, message_id=new_msgid)

    # Store fundamental information about to-be-sent message in database
    email_out = EmailOut(
        email_in_mid=get_message_id_from_incoming(msg),
        message_id=new_msgid,
        list_id=ml.id,
        recipients=subscribers_emails,
        sent_at=datetime.now(timezone.utc),
    )

    # --- Sanity checks ---
    # Make sure there is content to send
    if not msg.text and not msg.html:
        logging.warning("No HTML or Plaintext content in message %s", msg.uid)

    # --- Send to each subscriber individually ---
    for subscriber in subscribers_emails:
        try:
            # Copy mail class to avoid cross-contamination between recipients
            recipient_mail = deepcopy(mail)
            # Send email to recipient
            sent_msg = recipient_mail.send_email_to_recipient(
                recipient=subscriber, dry=app.config.get("DRY", False)
            )

            # Store sent message in Sent folder via IMAP if we have one
            if sent_msg:
                sent_successful.append(subscriber)
                with tempfile.NamedTemporaryFile(mode="w+", delete=True) as tmpfile:
                    tmpfile.write(msg.obj.as_string())
                    tmpfile.flush()
                    logging.debug(
                        "Saving sent message to temp file %s to be stored in Sent folder",
                        tmpfile.name,
                    )
                    if app.config.get("DRY", False):
                        logging.info(
                            "[DRY MODE] Would store sent message for %s in Sent folder "
                            "and mark as read.",
                            subscriber,
                        )
                    else:
                        mailbox.append(
                            message=sent_msg,
                            folder=app.config["IMAP_FOLDER_SENT"],
                            flag_set=["\\Seen"],
                        )
            else:
                sent_failed.append(subscriber)
                logging.warning(
                    "No sent message returned for subscriber %s, not storing in Sent folder",
                    subscriber,
                )
        except Exception as e:  # pylint: disable=broad-except
            sent_failed.append(subscriber)
            logging.error(
                "Failed to send message to %s: %s\nTraceback: %s",
                subscriber,
                e,
                traceback.format_exc(),
            )

    # Unify sent email lists and log/return results
    logging.info(
        "Finished sending message %s. Successful: %d, Failed: %d",
        msg.uid,
        len(sent_successful),
        len(sent_failed),
    )

    # Update EmailOut database entry, and add to session
    email_out.subject = mail.msg.subject
    email_out.raw = mail.composed_msg.as_string() if mail.composed_msg else ""
    email_out.sent_successful = sent_successful
    email_out.sent_failed = sent_failed
    db.session.add(email_out)
    db.session.commit()

    return sent_successful, sent_failed


def should_notify_sender(app: Flask, sender_email: str) -> bool:
    """
    Determine if a sender should be notified about message rejection.

    Args:
        app: Flask application instance
        sender_email: Email address of the sender (case-insensitive)

    Returns:
        bool: True if sender should be notified, False otherwise
    """
    # Check if notifications are enabled
    if not app.config.get("NOTIFY_REJECTED_SENDERS", False):
        return False

    # Normalize email to lowercase for case-insensitive comparison
    sender_email_lower = sender_email.lower()

    # Check if sender domain is in trusted domains list
    trusted_domains: list[str] = app.config.get("NOTIFY_REJECTED_TRUSTED_DOMAINS", [])
    if trusted_domains:
        sender_domain = sender_email_lower.split("@")[-1] if "@" in sender_email_lower else ""
        # Case-insensitive domain comparison
        if any(sender_domain == domain.lower() for domain in trusted_domains):
            logging.debug("Sender %s is in trusted domain, will notify", sender_email)
            return True

    # If restricted to known senders only, check database
    if app.config.get("NOTIFY_REJECTED_KNOWN_ONLY", True):
        subscriber = db.session.query(Subscriber).filter_by(email=sender_email_lower).first()
        if subscriber:
            logging.debug("Sender %s found in database, will notify", sender_email)
            return True
        logging.debug(
            "Sender %s not in database and NOTIFY_REJECTED_KNOWN_ONLY is True, will not notify",
            sender_email,
        )
        return False

    # If not restricted to known senders and not in trusted domains, notify anyway
    logging.debug("Sender %s will be notified (no restrictions active)", sender_email)
    return True


def send_rejection_notification(  # pylint: disable=too-many-arguments
    app: Flask,
    sender_email: str,
    recipient: str,
    reason: str,
    in_reply_to: str | None = None,
) -> bool:
    """
    Send a rejection notification to a sender whose message was not delivered.

    Args:
        app (Flask): Flask application instance
        sender_email (str): Email address to send notification to
        recipient (str): The list/recipient the sender tried to send to
        reason (str): Reason for rejection
        in_reply_to (str | None): Optional Message-ID to reference in the notification

    Returns:
        bool: True if notification was sent successfully, False otherwise
    """
    # Check if we should notify this sender
    if not should_notify_sender(app, sender_email):
        logging.debug("Skipping rejection notification for %s", sender_email)
        return False

    # Log sending attempt
    create_log_entry(
        level="info",
        event="email_out",
        message=f"Sending rejection notification to {sender_email} for message to {recipient}",
        details={"recipient": recipient, "reason": reason},
    )

    try:
        text_body = render_template(
            "email_rejection_notification.txt",
            recipient=recipient,
            reason=reason,
            domain=app.config["DOMAIN"],
        )

        # Create plain text message
        msg = MIMEText(text_body, "plain", "utf-8")
        # App
        msg["X-Mailer"] = "CastMail2List"
        msg["X-CastMail2List-Domain"] = app.config["DOMAIN"]
        # Message
        msg["Subject"] = _("Message to %(recipient)s not delivered", recipient=recipient)
        msg["From"] = app.config["SYSTEM_EMAIL"]
        msg["To"] = sender_email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=app.config["DOMAIN"])
        # Threading and references
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        # Prevent auto-responder loops
        msg["Auto-Submitted"] = "auto-replied"  # RFC 3834
        msg["X-Auto-Response-Suppress"] = "All"  # Prevent auto-responder loops
        msg["Precedence"] = "bulk"

        # Send email via SMTP
        if app.config.get("DRY", False):
            logging.info(
                "[DRY MODE] Would send rejection notification to %s for message to %s",
                sender_email,
                recipient,
            )
            return True

        send_email_via_smtp(
            smtp_host=app.config["SMTP_HOST"],
            smtp_port=app.config["SMTP_PORT"],
            smtp_user=app.config["SMTP_USER"],
            smtp_password=app.config["SMTP_PASS"],
            smtp_starttls=app.config.get("SMTP_STARTTLS", True),
            message=msg.as_bytes(),
            from_addr="",  # Empty Return-Path as it's an auto response
            to_addrs=sender_email,
            local_hostname=app.config["DOMAIN"],
        )

        logging.info(
            "Sent rejection notification to %s for message to %s (reason: %s)",
            sender_email,
            recipient,
            reason,
        )
        return True

    except Exception as e:  # pylint: disable=broad-except
        logging.error(
            "Failed to send rejection notification to %s: %s\nTraceback: %s",
            sender_email,
            e,
            traceback.format_exc(),
        )
        return False
