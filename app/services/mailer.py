# app/services/mailer.py
"""
Minimal SMTP sender.

Uses the SMTP_* settings already defined in app/config.py. When SMTP_HOST is
not configured, send_email() returns False and the caller decides what to do
(the password-reset flow logs the token so an operator can relay it, and tells
the user truthfully that no email was sent).
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import Config

log = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(Config.SMTP_HOST)


def send_email(to_addr: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True only if the SMTP server accepted it."""
    if not smtp_configured() or not to_addr:
        return False
    msg = EmailMessage()
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls()
                smtp.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass
            if Config.SMTP_USER:
                smtp.login(Config.SMTP_USER, Config.SMTP_PASS)
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("send_email failed (to=%s)", to_addr)
        return False
