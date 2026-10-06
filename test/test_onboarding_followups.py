"""
Regression tests for the follow-up decisions on the onboarding re-audit:

  R1  the seeded 'SBI' account is the primary bank account from day one
  R2  a missing STARTTLS is warned about (loudly), not silently ignored
  R3  the forgot-password form gives ONE message for every outcome
  R5  the Quick Start no longer claims every date defaults to 1 April

Pure logic / text checks only: no database needed.
"""
import logging
import smtplib
from pathlib import Path

import pytest

from app.services import auth_service, mailer

ROOT = Path(__file__).resolve().parent.parent


# ── R1 ────────────────────────────────────────────────────────────────────────
def _setup_fn_sql() -> str:
    sql = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")
    start = sql.index("CREATE OR REPLACE FUNCTION fn_complete_society_setup")
    nxt = sql.find("CREATE OR REPLACE FUNCTION", start + 10)
    return sql[start: nxt if nxt != -1 else len(sql)]


def test_r1_setup_function_defaults_primary_bank_to_sbi():
    body = _setup_fn_sql()
    assert "primary_bank_account_id = COALESCE(primary_bank_account_id" in body
    assert "tab_name = 'SBI'" in body
    # an already-chosen primary must win over the default
    assert body.index("primary_bank_account_id = COALESCE(primary_bank_account_id,") < body.index("WHERE id = p_society_id")


def test_r1_wizard_text_matches_behaviour():
    src = (ROOT / "app" / "dash_apps" / "pages" / "setup_wizard.py").read_text(encoding="utf-8")
    assert "NOT set by default" not in src
    assert "SBI A/c - Society" in src


def test_r1_quickstart_says_sbi_is_primary():
    doc = (ROOT / "docs" / "ADMIN_QUICKSTART.md").read_text(encoding="utf-8")
    assert "SBI A/c - Society" in doc
    assert "It is *not* set for you" not in doc


# ── R2 ────────────────────────────────────────────────────────────────────────
class _FakeSMTP:
    supports_starttls = True
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        if not self.supports_starttls:
            raise smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server.")

    def login(self, user, password):
        pass

    def send_message(self, msg):
        type(self).sent.append(msg)


@pytest.fixture
def smtp_env(monkeypatch):
    class Fake(_FakeSMTP):
        sent = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", Fake)
    monkeypatch.setattr(mailer.Config, "SMTP_HOST", "mail.example.org")
    monkeypatch.setattr(mailer.Config, "SMTP_PORT", 587)
    monkeypatch.setattr(mailer.Config, "SMTP_FROM", "noreply@example.org")
    monkeypatch.setattr(mailer.Config, "SMTP_USER", "")
    return Fake


def test_r2_warns_when_starttls_is_not_offered(smtp_env, caplog):
    smtp_env.supports_starttls = False
    caplog.set_level(logging.WARNING, logger="app.services.mailer")
    assert mailer.send_email("a@b.com", "subj", "body") is True       # still sent
    assert len(smtp_env.sent) == 1
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("STARTTLS" in m and "UNENCRYPTED" in m for m in warned), warned
    assert any("mail.example.org" in m for m in warned)


def test_r2_no_warning_when_starttls_is_available(smtp_env, caplog):
    smtp_env.supports_starttls = True
    caplog.set_level(logging.WARNING, logger="app.services.mailer")
    assert mailer.send_email("a@b.com", "subj", "body") is True
    assert not [r for r in caplog.records if "STARTTLS" in r.getMessage()]


def test_r2_warning_never_contains_the_message_body(smtp_env, caplog):
    smtp_env.supports_starttls = False
    caplog.set_level(logging.WARNING, logger="app.services.mailer")
    mailer.send_email("a@b.com", "subj", "Reset token: SECRET-TOKEN-123")
    assert "SECRET-TOKEN-123" not in caplog.text


# ── R3 ────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, known_emails):
        self.known = {e.lower() for e in known_emails}

    def _execute(self, query, params=None, fetch_one=False, **kw):
        if query.lstrip().upper().startswith("SELECT"):
            email = (params or {}).get("email", "").lower()
            return {"id": 7} if email in self.known else None
        return None


def test_r3_message_text():
    assert auth_service.RESET_REQUEST_MESSAGE == "Reset mail sent if account available in database."


@pytest.mark.parametrize("email,mail_ok", [
    ("nobody@example.com", True),       # no such account
    ("admin@society.org", True),        # account exists, mail delivered
    ("admin@society.org", False),       # account exists, mail NOT delivered (no SMTP)
])
def test_r3_same_message_for_every_outcome(monkeypatch, email, mail_ok):
    monkeypatch.setattr(auth_service, "db", _StubDB(["admin@society.org"]))
    monkeypatch.setattr("app.services.mailer.send_email", lambda *a, **k: mail_ok)
    ok, msg, _token = auth_service.request_password_reset(email, None)
    assert ok is True
    assert msg == auth_service.RESET_REQUEST_MESSAGE


def test_r3_unknown_account_gets_no_token(monkeypatch):
    monkeypatch.setattr(auth_service, "db", _StubDB([]))
    _ok, _msg, token = auth_service.request_password_reset("nobody@example.com", None)
    assert token is None


# ── R5 ────────────────────────────────────────────────────────────────────────
def test_r5_quickstart_does_not_overclaim_default_dates():
    doc = (ROOT / "docs" / "ADMIN_QUICKSTART.md").read_text(encoding="utf-8")
    assert "Dates default to the start of the current financial year" not in doc
    assert "Accounting Start Date" in doc and "created your society" in doc
