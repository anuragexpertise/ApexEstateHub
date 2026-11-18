"""DATABASE_URL connections must still run the session in IST, or CURRENT_DATE lags today_ist() between 00:00 and 05:30 IST."""
import pytest

from database.db_manager import DatabaseManager


@pytest.fixture
def dsn(monkeypatch):
    def make(url, **env):
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.delenv("PG_SKIP_STARTUP_OPTIONS", raising=False)
        monkeypatch.delenv("TZ", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return DatabaseManager._dsn(object.__new__(DatabaseManager))
    return make


def test_database_url_gets_ist_option(dsn):
    out = dsn("postgres://u:p@pg-x.aivencloud.com:12345/db?sslmode=require")
    assert out.startswith("postgresql://") and "&options=-c%20timezone%3DAsia/Kolkata" in out.replace("%2F", "/")


def test_url_without_query_uses_question_mark(dsn):
    assert "?options=" in dsn("postgresql://u:p@h/db")


def test_pooler_host_is_left_alone(dsn):
    assert "options=" not in dsn("postgresql://u:p@ep-x-pooler.example.com/db?sslmode=require")


def test_existing_options_and_skip_flag_respected(dsn):
    assert dsn("postgresql://u:p@h/db?options=-c%20x%3D1").count("options=") == 1
    assert "options=" not in dsn("postgresql://u:p@h/db", PG_SKIP_STARTUP_OPTIONS="1")


def test_old_calcutta_alias_is_normalised(dsn):
    assert "Asia/Kolkata" in dsn("postgresql://u:p@h/db", TZ="Asia/Calcutta").replace("%2F", "/")
