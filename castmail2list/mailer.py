"""Mailer utility for sending emails via SMTP"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from imap_tools.utils import EmailAddress


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

    def send_email(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        list_address: str,
        list_name: str,
        from_addr: EmailAddress,
        subject: str,
        recipient: str,
        to_header: tuple[str, ...],
        cc_header: tuple[str, ...],
        date_header: str,
        msg_id: str,
        text_message: str = "",
        html_message: str = "",
        attachments: None | list[tuple[str, bytes, str]] = None,
    ) -> None:
        """
        Sends an email using a Jinja2 template.
        """

        # Deal with recipient as possible To of original message
        if recipient in to_header:
            # TODO: Decide what to do if recipient is also in To header
            pass
        if list_address in to_header or list_address in cc_header:
            # Remove list address from To and CC headers to avoid confusion
            # TODO: Depending on list settings as broadcast or real mailing list, this needs to be
            # handled differently
            to_header = tuple(addr for addr in to_header if addr != list_address)
            cc_header = tuple(addr for addr in cc_header if addr != list_address)

        # Model new From field
        from_header = f"{from_addr.name} via {list_name} <{list_address}>"

        # Create the email message wth all necessary headers
        msg = MIMEMultipart()
        msg["From"] = from_header
        msg["To"] = ", ".join(to_header) if to_header else recipient
        if cc_header:
            msg["Cc"] = ", ".join(cc_header)
        msg["Subject"] = subject
        msg["Message-ID"] = msg_id
        msg["Date"] = date_header or formatdate(localtime=True)
        # TODO: Set List-ID only for real mailing lists, not for broadcast mode
        msg["List-Id"] = f"{list_name} <{list_address.replace('@', '.')}>"
        msg["X-Mailer"] = "CastMail2List"

        # Attach the email body in Plain and HTML
        if html_message:
            msg.attach(MIMEText(html_message, "html"))
        if text_message:
            msg.attach(MIMEText(text_message, "plain"))
        if not html_message and not text_message:
            logging.warning("No HTML or Plaintext content provided for email to %s", recipient)

        logging.debug("Email content: \n%s", msg.as_string())

        try:
            # Send the email
            with smtplib.SMTP(self.smtp_server, int(self.smtp_port)) as server:
                if self.smtp_starttls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(from_addr=self.smtp_from, to_addrs=recipient, msg=msg.as_string())
            logging.info("Email sent to %s", recipient)

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Failed to send email: {e}")
