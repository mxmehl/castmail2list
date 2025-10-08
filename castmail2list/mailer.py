"""Mailer utility for sending emails via SMTP"""

import smtplib
from email.message import EmailMessage


def send_mail(smtp_cfg, to_addr: str, msg_subject: str, msg_body: str, from_addr: str):
    """
    Send an email via SMTP

    Args:
        smtp_cfg: SMTP configuration object with SMTP_HOST, SMTP_USER, SMTP_PASS
        to_addr (str): recipient email address
        msg_subject (str): email subject
        msg_body (str): email body (plain text)
        from_addr (str): sender email address

    Returns:
        None

    Raises:
        smtplib.SMTPException: if sending fails
    """
    msg = EmailMessage()
    msg["Subject"] = msg_subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(msg_body)

    with smtplib.SMTP_SSL(smtp_cfg.SMTP_HOST) as smtp:
        smtp.login(smtp_cfg.SMTP_USER, smtp_cfg.SMTP_PASS)
        smtp.send_message(msg)
