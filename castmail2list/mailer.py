"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
import tempfile
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from flask import Flask
from imap_tools import MailBox
from imap_tools.message import MailAttachment, MailMessage

from castmail2list.models import List, Subscriber


class Mail:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Class for an email sent to multiple recipients via SMTP"""

    def __init__(  # pylint: disable=too-many-positional-arguments, too-many-arguments
        self,
        app: Flask,
        message_id: str,
        list_from_address: str,
    ):
        self.smtp_server: str = app.config["SMTP_HOST"]
        self.smtp_port: str | int = app.config["SMTP_PORT"]
        self.smtp_user: str = app.config["SMTP_USER"]
        self.smtp_password: str = app.config["SMTP_PASS"]
        self.smtp_starttls: bool = app.config["SMTP_STARTTLS"]
        self.envelope_from: str = list_from_address
        self.message_id: str = message_id

    def send_email(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        list_address: str,
        header_from: str,
        subject: str,
        recipient: str,
        to_header: tuple[str, ...],
        cc_header: tuple[str, ...],
        date_header: str,
        text_message: str = "",
        html_message: str = "",
        attachments: list[MailAttachment] | None = None,
    ) -> bytes:
        """
        Sends an email using a Jinja2 template. Returns sent message as bytes
        """
        # --- Choose correct container type ---
        msg: MIMEMultipart | MIMEText
        # If there are attachments, we need a "mixed" container
        if attachments:
            msg = MIMEMultipart("mixed")
        # If there are both text and HTML parts, we need an "alternative" container
        elif text_message and html_message:
            msg = MIMEMultipart("alternative")
        # If there are only text or only HTML parts, we can use a simple MIMEText
        else:
            # Just a plain text or html-only email — no multipart needed
            msg = MIMEText(html_message or text_message, "html" if html_message else "plain")

        # Deal with recipient as possible To of original message
        if recipient in to_header:
            # TODO: Decide what to do if recipient is also in To header
            pass

        # --- Write common headers ---
        msg["From"] = header_from
        msg["To"] = ", ".join(to_header) if to_header else recipient
        if cc_header:
            msg["Cc"] = ", ".join(cc_header)
        msg["Subject"] = subject
        msg["Message-ID"] = self.message_id
        msg["Date"] = date_header or formatdate(localtime=True)
        msg["List-Id"] = f"<{list_address.replace('@', '.')}>"
        msg["X-Mailer"] = "CastMail2List"
        msg["Precedence"] = "list"

        # --- Add body parts ---
        if isinstance(msg, MIMEMultipart):
            if text_message and html_message:
                # Combine text+html properly as an alternative part
                alt = MIMEMultipart("alternative")
                alt.attach(MIMEText(text_message, "plain"))
                alt.attach(MIMEText(html_message, "html"))
                msg.attach(alt)
            elif text_message:
                msg.attach(MIMEText(text_message, "plain"))
            elif html_message:
                msg.attach(MIMEText(html_message, "html"))

            # Add attachments if any
            if attachments:
                for attachment in attachments:
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
                local_hostname=list_address.split("@")[-1],
            ) as server:
                if self.smtp_starttls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    from_addr=self.envelope_from, to_addrs=recipient, msg=msg.as_string()
                )
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to send email: {e}")

        return msg.as_bytes()


def send_msg_to_subscribers(
    app: Flask, msg: MailMessage, ml: List, subscribers: list[Subscriber], mailbox: MailBox
) -> None:
    """Send message to all subscribers"""
    # Prepare message class
    new_msgid = make_msgid(idstring="castmail2list", domain=ml.address.split("@")[-1])
    mail = Mail(app=app, message_id=new_msgid, list_from_address=ml.from_addr)

    # Sanity checks
    if not msg.text and not msg.html:
        logging.warning("No HTML or Plaintext content in message %s", msg.uid)

    # Depending on list mode, prepare headers
    if ml.mode == "broadcast":
        from_header = ml.from_addr or ml.address
    elif ml.mode == "group":
        if not msg.from_values:
            logging.error("No valid From header in message %s, cannot send", msg.uid)
            return
        from_header = (
            f"{msg.from_values.name or msg.from_values.email} via {ml.name} <{ml.address}>"
        )
    else:
        logging.error("Unknown list mode %s for list %s", ml.mode, ml.name)
        return

    if ml.address in msg.to or ml.address in msg.cc:
        # Remove list address from To and CC headers to avoid confusion
        # TODO: Depending on list settings as broadcast or real mailing list, this needs to be
        # handled differently
        msg.to = tuple(addr for addr in msg.to if addr != ml.address)
        msg.cc = tuple(addr for addr in msg.cc if addr != ml.address)

    for subscriber in subscribers:
        try:
            sent_msg = mail.send_email(
                list_address=ml.address,
                header_from=from_header,
                to_header=msg.to,
                cc_header=msg.cc,
                date_header=msg.date_str,
                subject=msg.subject,
                text_message=msg.text or "",
                html_message=msg.html or "",
                recipient=subscriber.email,
                attachments=msg.attachments,
            )
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
            logging.error("Failed to send message to %s: %s", subscriber.email, e)
