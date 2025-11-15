import smtplib
from email.message import EmailMessage


def send_mail(smtp_cfg, to_addr, msg_subject, msg_body, from_addr):
    msg = EmailMessage()
    msg["Subject"] = msg_subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(msg_body)

    with smtplib.SMTP_SSL(smtp_cfg.SMTP_HOST) as smtp:
        smtp.login(smtp_cfg.SMTP_USER, smtp_cfg.SMTP_PASS)
        smtp.send_message(msg)
