"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
import tempfile
import traceback
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from flask import Flask
from imap_tools import MailBox
from imap_tools.message import MailMessage

from castmail2list.models import List, Subscriber


class Mail:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Class for an email sent to multiple recipients via SMTP"""

    def __init__(  # pylint: disable=too-many-positional-arguments, too-many-arguments
        self,
        app: Flask,
        ml: List,
        msg: MailMessage,
        message_id: str,
    ) -> None:
        self.smtp_server: str = app.config["SMTP_HOST"]
        self.smtp_port: str | int = app.config["SMTP_PORT"]
        self.smtp_user: str = app.config["SMTP_USER"]
        self.smtp_password: str = app.config["SMTP_PASS"]
        self.smtp_starttls: bool = app.config["SMTP_STARTTLS"]
        self.message_id: str = message_id
        self.ml: List = ml
        self.msg: MailMessage = msg
        self.from_header: str = ""
        self.reply_to: str = ""
        self.original_mid: str = next(iter(self.msg.headers.get("message-id", ())), "")


    def construct_envelope_from(self, recipient: str) -> str:
        """
        Construct the individualized Envelope From address for bounce handling.

        For the list address `list1@list.example.com` and the recipient `jane.doe@gmail.com`,
        the return will be `list1+bounces--jane.doe=gmail.com@list.example.com`

        Args:
            recipient (str): The recipient email address
        Returns:
            str: The constructed Envelope From address
        """
        local_part, domain_part = self.ml.address.split("@", 1)
        sanitized_recipient = recipient.replace("@", "=").replace("+", "-")
        return f"{local_part}+bounces--{sanitized_recipient}@{domain_part}"

    def send_email(  # pylint: disable=too-many-branches,too-many-statements
        self,
        recipient: str,
    ) -> bytes:
        """
        Sends an email using a Jinja2 template. Returns sent message as bytes
        """
        # --- Choose correct container type ---
        msg: MIMEMultipart | MIMEText
        # If there are attachments, we need a "mixed" container
        if self.msg.attachments:
            msg = MIMEMultipart("mixed")
        # If there are both text and HTML parts, we need an "alternative" container
        elif self.msg.text and self.msg.html:
            msg = MIMEMultipart("alternative")
        # If there are only text or only HTML parts, we can use a simple MIMEText
        else:
            # Just a plain text or html-only email — no multipart needed
            msg = MIMEText(self.msg.html or self.msg.text, "html" if self.msg.html else "plain")

        # Deal with recipient as possible To of original message
        if recipient in self.msg.to:
            # TODO: Decide what to do if recipient is also in To header
            pass

        # --- Write common headers ---
        msg["From"] = self.from_header
        msg["To"] = ", ".join(self.msg.to) if self.msg.to else recipient
        if self.msg.cc:
            msg["Cc"] = ", ".join(self.msg.cc)
        msg["Subject"] = self.msg.subject
        msg["Message-ID"] = self.message_id
        msg["Date"] = self.msg.date_str or formatdate(localtime=True)
        msg["List-Id"] = f"<{self.ml.address.replace('@', '.')}>"
        msg["X-Mailer"] = "CastMail2List"
        msg["Precedence"] = "list"
        msg["Original-Message-ID"] = self.original_mid
        msg["In-Reply-To"] = (
            self.msg.headers.get("in-reply-to", ())[0]
            if self.msg.headers.get("in-reply-to", ())
            else self.original_mid
        )
        msg["References"] = " ".join(self.msg.headers.get("references", ()) + (self.original_mid,))
        if self.reply_to:
            msg["Reply-To"] = self.reply_to

        # --- Add body parts ---
        if isinstance(msg, MIMEMultipart):
            if self.msg.text and self.msg.html:
                # Combine text+html properly as an alternative part
                alt = MIMEMultipart("alternative")
                alt.attach(MIMEText(self.msg.text, "plain"))
                alt.attach(MIMEText(self.msg.html, "html"))
                msg.attach(alt)
            elif self.msg.text:
                msg.attach(MIMEText(self.msg.text, "plain"))
            elif self.msg.html:
                msg.attach(MIMEText(self.msg.html, "html"))

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
                    msg.attach(part)

        logging.debug("Email content: \n%s", msg.as_string())

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
                    from_addr=self.construct_envelope_from(recipient),
                    to_addrs=recipient,
                    msg=msg.as_string(),
                )
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to send email: %s\nTraceback: %s", e, traceback.format_exc())

        return msg.as_bytes()


def send_msg_to_subscribers(app: Flask, msg: MailMessage, ml: List, mailbox: MailBox) -> None:
    """Send message to all subscribers of a list"""
    # Find all subscribers of the list
    subscribers: list[Subscriber] = Subscriber.query.filter_by(list_id=ml.id).all()
    logging.debug(
        "Found %d subscribers for the list <%s>: %s",
        len(subscribers),
        ml.address,
        ", ".join([subscribers.email for subscribers in subscribers]),
    )

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

    # Depending on list mode, prepare headers
    if ml.mode == "broadcast":
        # From: Use the list's From address if set, otherwise the list address itself
        mail.from_header = ml.from_addr or ml.address
        # Reply-To: No Reply-To, sender is the expected recipient of replies
        mail.reply_to = ""
    elif ml.mode == "group":
        # From: Use "Sender Name via List Name <list@address>" format if possible
        if not msg.from_values:
            logging.error("No valid From header in message %s, cannot send", msg.uid)
            return
        mail.from_header = (
            f"{msg.from_values.name or msg.from_values.email} via {ml.name} <{ml.address}>"
        )
        # Reply-To: Set to list address to avoid replies going to all subscribers
        mail.reply_to = ml.address
    else:
        logging.error("Unknown list mode %s for list %s", ml.mode, ml.name)
        return

    if ml.address in msg.to or ml.address in msg.cc:
        # Remove list address from To and CC headers to avoid confusion
        # TODO: Depending on list settings as broadcast or real mailing list, this needs to be
        # handled differently
        mail.msg.to = tuple(addr for addr in msg.to if addr != ml.address)
        mail.msg.cc = tuple(addr for addr in msg.cc if addr != ml.address)

    for subscriber in subscribers:
        try:
            sent_msg = mail.send_email(recipient=subscriber.email)
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
