"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid


class Mail:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Class for an email with specific template and subject this app will send"""

    def __init__(  # pylint: disable=too-many-positional-arguments, too-many-arguments
        self,
        smtp_server: str,
        smtp_port: str | int,
        smtp_user: str,
        smtp_password: str,
        smtp_starttls: bool,
        smtp_from: str,
    ):
        self.smtp_server: str = smtp_server
        self.smtp_port: str | int = smtp_port
        self.smtp_user: str = smtp_user
        self.smtp_password: str = smtp_password
        self.smtp_starttls: bool = smtp_starttls
        self.smtp_from: str = smtp_from

    def send_email(self, subject: str, message: str, recipient: str) -> None:
        """
        Sends an email using a Jinja2 template.
        """

        # Create the email message
        msg = MIMEMultipart()
        msg["From"] = self.smtp_from
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(idstring="castmail2list", domain="localhost")
        msg["Date"] = formatdate(localtime=True)

        # Attach the email body as HTML
        msg.attach(MIMEText(message, "html"))
        logging.debug("Email content: \n%s", msg.as_string())

        try:
            # Send the email
            with smtplib.SMTP(self.smtp_server, int(self.smtp_port)) as server:
                if self.smtp_starttls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, recipient, msg.as_string())
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to send email: {e}")
