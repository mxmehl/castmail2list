"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
import tempfile
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
        list_name: str,
        header_from: str,
        subject: str,
        recipient: str,
        to_header: tuple[str, ...],
        cc_header: tuple[str, ...],
        date_header: str,
        text_message: str = "",
        html_message: str = "",
        attachments: None | list[tuple[str, bytes, str]] = None,
    ) -> bytes:
        """
        Sends an email using a Jinja2 template. Returns sent message as bytes
        """
        # Deal with recipient as possible To of original message
        if recipient in to_header:
            # TODO: Decide what to do if recipient is also in To header
            pass

        # Create the email message wth all necessary headers
        msg = MIMEMultipart()
        msg["From"] = header_from
        msg["To"] = ", ".join(to_header) if to_header else recipient
        if cc_header:
            msg["Cc"] = ", ".join(cc_header)
        msg["Subject"] = subject
        msg["Message-ID"] = self.message_id
        msg["Date"] = date_header or formatdate(localtime=True)
        # TODO: Set List-ID only for real mailing lists, not for broadcast mode
        msg["List-Id"] = f"{list_name} <{list_address.replace('@', '.')}>"
        msg["X-Mailer"] = "CastMail2List"

        # Attach the email body in Plain and HTML
        if text_message:
            msg.attach(MIMEText(text_message, "plain"))
        if html_message:
            msg.attach(MIMEText(html_message, "html"))

        logging.debug("Email content: \n%s", msg.as_string())

        try:
            # Send the email
            with smtplib.SMTP(self.smtp_server, int(self.smtp_port)) as server:
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
    new_msgid = make_msgid(idstring="castmail2list", domain="localhost")
    mail = Mail(app=app, message_id=new_msgid, list_from_address=ml.from_addr)

    # Sanity checks
    if not msg.text and not msg.html:
        logging.warning("No HTML or Plaintext content in message %s", msg.uid)

    # Depending on list mode, prepare headers
    if ml.mode == "broadcast":
        from_header = ml.from_addr or ml.address
    elif ml.mode == "list":
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
                list_address=ml.from_addr,
                list_name=ml.name,
                header_from=from_header,
                to_header=msg.to,
                cc_header=msg.cc,
                date_header=msg.date_str,
                subject=msg.subject,
                text_message=msg.text or "",
                html_message=msg.html or "",
                recipient=subscriber.email,
            )
            with tempfile.NamedTemporaryFile(mode="w+", delete=True) as tmpfile:
                tmpfile.write(msg.obj.as_string())
                tmpfile.flush()
                logging.debug(
                    "Saving sent message to temp file %s to be stored in Sent folder", tmpfile.name
                )
                mailbox.append(message=sent_msg, folder=app.config["IMAP_FOLDER_SENT"], flag_set=["\\Seen"])
        except Exception as e:  # pylint: disable=broad-except
            logging.error("Failed to send message to %s: %s", subscriber.email, e)
