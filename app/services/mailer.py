# app/services/mailer.py
"""
Minimal SMTP sender.

Uses the SMTP_* settings already defined in app/config.py. When SMTP_HOST is
not configured, send_email() returns False and the caller decides what to do
(the password-reset flow logs the token so an operator can relay it).

STARTTLS: the connection is upgraded with STARTTLS when the server offers it.
If it does not, the email is still sent but a WARNING is logged asking the
operator to make STARTTLS available.
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
                # The message is still sent (some internal relays have no TLS),
                # but an operator must know it travelled in clear text.
                log.warning(
                    "SMTP server %s:%s does not offer STARTTLS, so this email "
                    "(including password-reset tokens and any SMTP login) is sent "
                    "UNENCRYPTED. Please make STARTTLS available on the mail "
                    "server, or point SMTP_HOST at one that supports it.",
                    Config.SMTP_HOST, Config.SMTP_PORT)
            if Config.SMTP_USER:
                smtp.login(Config.SMTP_USER, Config.SMTP_PASS)
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("send_email failed (to=%s)", to_addr)
        return False
