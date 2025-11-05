"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
import tempfile
import traceback
from copy import deepcopy
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from flask import Flask
from imap_tools import MailBox
from imap_tools.message import MailMessage

from .models import List, Subscriber
from .utils import create_bounce_address


class Mail:  # pylint: disable=too-many-instance-attributes
    """Class for an email sent to multiple recipients via SMTP"""

    def __init__(
        self,
        app: Flask,
        ml: List,
        msg: MailMessage,
        message_id: str,
    ) -> None:
        # SMTP settings from app config
        self.smtp_server: str = app.config["SMTP_HOST"]
        self.smtp_port: str | int = app.config["SMTP_PORT"]
        self.smtp_user: str = app.config["SMTP_USER"]
        self.smtp_password: str = app.config["SMTP_PASS"]
        self.smtp_starttls: bool = app.config["SMTP_STARTTLS"]
        # Arguments as class attributes
        self.message_id: str = message_id
        self.ml: List = ml
        self.msg: MailMessage = msg
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

    def prepare_common_headers(self) -> None:
        """Prepare common email headers, except To which is per-recipient"""
        if not self.composed_msg:
            raise ValueError("Message container type not chosen yet")

        # --- Prepare From and Reply-To headers based on list mode ---
        if self.ml.mode == "broadcast":
            # From: Use the list's From address if set, otherwise the list address itself
            self.from_header = self.ml.from_addr or self.ml.address
            # Reply-To: No Reply-To, sender is the expected recipient of replies
            self.reply_to = ""
        elif self.ml.mode == "group":
            # From: Use "Sender Name via List Name <list@address>" format if possible
            if not self.msg.from_values:
                logging.error("No valid From header in message %s, cannot send", self.msg.uid)
                return
            self.from_header = (
                f"{self.msg.from_values.name or self.msg.from_values.email} "
                f"via {self.ml.name} <{self.ml.address}>"
            )
            # Reply-To: Set to list address to avoid replies going to all subscribers
            self.reply_to = self.ml.address
            # TODO: If sender is not member of list, consider adding them as Reply-To. Or perhaps
            # List and sender?
            # Add X-MailFrom with original sender address
            self.x_mailfrom_header = self.msg.from_values.email
        else:
            logging.error("Unknown list mode %s for list %s", self.ml.mode, self.ml.name)
            return

        if self.ml.address in self.msg.to or self.ml.address in self.msg.cc:
            # Remove list address from To and CC headers to avoid confusion
            # TODO: Depending on list settings as broadcast or real mailing list, this needs to be
            # handled differently
            self.msg.to = tuple(addr for addr in self.msg.to if addr != self.ml.address)
            self.msg.cc = tuple(addr for addr in self.msg.cc if addr != self.ml.address)

        self.composed_msg["From"] = self.from_header
        if self.msg.cc:
            self.composed_msg["Cc"] = ", ".join(self.msg.cc)
        self.composed_msg["Subject"] = self.msg.subject
        self.composed_msg["Message-ID"] = self.message_id
        self.composed_msg["Date"] = self.msg.date_str or formatdate(localtime=True)
        self.composed_msg["Sender"] = self.ml.address
        self.composed_msg["List-Id"] = f"<{self.ml.address.replace('@', '.')}>"
        self.composed_msg["X-Mailer"] = "CastMail2List"
        if self.x_mailfrom_header:
            self.composed_msg["X-MailFrom"] = self.x_mailfrom_header
        self.composed_msg["Precedence"] = "list"
        self.composed_msg["Original-Message-ID"] = self.original_mid
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
    ) -> bytes:
        """
        Sends the mostly prepared list message to a recipient. Returns sent message as bytes.
        """
        if self.composed_msg is None:
            logging.error("Message container not prepared, cannot send email to %s", recipient)
            return b""

        # --- Add per-recipient headers ---
        # Deal with recipient as possible To of original message
        if recipient in self.msg.to:
            # TODO: Decide what to do if recipient is also in To header of original message
            pass
        # Add recipient to To header if not already present
        if recipient not in self.msg.to:
            self.msg.to += (recipient,)
        # Set To header: preserve original To addresses if any (minus the list address in some
        # configurations), and recipient in any case
        self.composed_msg["To"] = ", ".join(self.msg.to) if self.msg.to else recipient

        logging.debug("Email content: \n%s", self.composed_msg.as_string())

        # --- Send email ---
        try:
            # Send the email
            with smtplib.SMTP(
                self.smtp_server,
                int(self.smtp_port),
                local_hostname=self.ml.address.split("@")[-1],
            ) as server:
                if self.smtp_starttls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    from_addr=create_bounce_address(
                        ml_address=self.ml.address, recipient=recipient
                    ),
                    to_addrs=recipient,
                    msg=self.composed_msg.as_string(),
                )
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to send email: %s\nTraceback: %s", e, traceback.format_exc())

        return self.composed_msg.as_bytes()


def get_list_subscribers(ml: List) -> list[Subscriber]:
    """Get all (deduplicated) subscribers of a mailing list, including those from overlapping lists"""
    # Find all subscribers of the list
    subscribers: list[Subscriber] = Subscriber.query.filter_by(list_id=ml.id).all()
    logging.debug(
        "Found %d initial subscribers for the list <%s>: %s",
        len(subscribers),
        ml.address,
        ", ".join([subscribers.email for subscribers in subscribers]),
    )

    # Find out if any of the subscribers' email addresses is a configured mailing list address
    subscriber_emails: list[str] = [sub.email for sub in subscribers]
    all_lists: list[List] = List.query.all()
    ml_addresses: list[str] = [l.address for l in all_lists]
    overlapping_addresses = set(subscriber_emails) & set(ml_addresses)
    if overlapping_addresses:
        logging.debug(
            "Some subscribers are also mailing lists: %s",
            ", ".join(overlapping_addresses),
        )

    # Get all subscribers of each of those lists to avoid sending duplicate emails
    additional_subscribers: list[Subscriber] = []
    for overlap_address in overlapping_addresses:
        overlapping_list = List.query.filter_by(address=overlap_address).first()
        if overlapping_list:
            overlapping_subs = Subscriber.query.filter_by(list_id=overlapping_list.id).all()
            additional_subscribers.extend(overlapping_subs)

    # Combine and deduplicate subscribers
    all_subscribers_dict = {sub.email: sub for sub in subscribers + additional_subscribers}
    subscribers = list(all_subscribers_dict.values())

    # Finally, remove the identified mailing list addresses themselves
    subscribers = [sub for sub in subscribers if sub.email not in ml_addresses]

    logging.debug(
        "Found %d unique, non-list subscribers for the list <%s>: %s",
        len(subscribers),
        ml.address,
        ", ".join([sub.email for sub in subscribers]),
    )
    return subscribers


def send_msg_to_subscribers(app: Flask, msg: MailMessage, ml: List, mailbox: MailBox) -> None:
    """Send message to all subscribers of a list"""
    subscribers: list[Subscriber] = get_list_subscribers(ml)
    return

    # Prepare message class
    new_msgid = make_msgid(idstring="castmail2list", domain=ml.address.split("@")[-1])
    mail = Mail(app=app, ml=ml, msg=msg, message_id=new_msgid)

    # --- Sanity checks ---
    # Make sure there is content to send
    if not msg.text and not msg.html:
        logging.warning("No HTML or Plaintext content in message %s", msg.uid)
    # In broadcast mode, ensure the original sender of the message is in the allowed senders list
    if ml.mode == "broadcast" and ml.allowed_senders:
        allowed_senders: list[str] = [
            email.strip() for email in ml.allowed_senders.split(",") if email.strip()
        ]
        if not msg.from_values or msg.from_values.email not in allowed_senders:
            logging.error(
                "Sender %s not in allowed senders for list %s, skipping message %s",
                msg.from_values.email if msg.from_values else "unknown",
                ml.name,
                msg.uid,
            )
            return
    # In group mode, ensure the original sender is one of the subscribers
    if ml.mode == "group" and subscribers and ml.only_subscribers_send:
        subscriber_emails = [sub.email for sub in subscribers]
        if not msg.from_values or msg.from_values.email not in subscriber_emails:
            logging.error(
                "Sender %s not a subscriber of list %s, skipping message %s",
                msg.from_values.email if msg.from_values else "unknown",
                ml.name,
                msg.uid,
            )
            return

    for subscriber in subscribers:
        try:
            # Copy mail class to avoid cross-contamination between recipients
            recipient_mail = deepcopy(mail)
            sent_msg = recipient_mail.send_email_to_recipient(recipient=subscriber.email)
            with tempfile.NamedTemporaryFile(mode="w+", delete=True) as tmpfile:
                tmpfile.write(msg.obj.as_string())
                tmpfile.flush()
                logging.debug(
                    "Saving sent message to temp file %s to be stored in Sent folder", tmpfile.name
                )
                mailbox.append(
                    message=sent_msg, folder=app.config["IMAP_FOLDER_SENT"], flag_set=["\\Seen"]
                )
        except Exception as e:  # pylint: disable=broad-except
            logging.error(
                "Failed to send message to %s: %s\nTraceback: %s",
                subscriber.email,
                e,
                traceback.format_exc(),
            )
