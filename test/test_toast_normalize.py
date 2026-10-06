"""Toasts always show a readable message (blank-toast fix)."""
import pytest

from app.utils.ux_toasts import normalize_toast, toast_duration_ms


@pytest.mark.parametrize("data,expected_type", [
    ({"type": "success", "message": ""}, "success"),
    ({"type": "error", "message": None}, "error"),
    ({"type": "error"}, "error"),
    ({"type": "warning", "message": "   "}, "warning"),
    ({"type": "error", "message": "None"}, "error"),
    ({"type": "error", "message": "False"}, "error"),
    ({"message": ""}, "info"),
    ({"type": "weird", "message": ""}, "info"),
])
def test_empty_message_gets_a_default(data, expected_type):
    out = normalize_toast(data)
    assert out["type"] == expected_type
    assert out["message"].strip()


def test_nothing_to_show():
    assert normalize_toast(None) is None
    assert normalize_toast({}) is None
    assert normalize_toast("") is None


def test_plain_string_and_wrapper_and_alt_keys():
    assert normalize_toast("Saved")["message"] == "Saved"
    assert normalize_toast({"_toast": {"type": "success", "message": "Receipt saved"}})["message"] == "Receipt saved"
    assert normalize_toast({"type": "error", "msg": "Flat not found"})["message"] == "Flat not found"
    assert normalize_toast({"type": "info", "message": ["a", "b"]})["message"] == "a b"


def test_technical_text_is_made_friendly():
    raw = 'duplicate key value violates unique constraint "x"\nDETAIL: Key (email)=(a@b) already exists.'
    assert normalize_toast({"type": "error", "message": raw})["message"] == "This record already exists."
    out = normalize_toast({"type": "error", "message": 'psycopg2.errors.UndefinedColumn: column "q" does not exist'})
    assert "psycopg2" not in out["message"] and "column" not in out["message"]
    out = normalize_toast({"type": "error", "message": "Cannot save\nCONTEXT: PL/pgSQL function x line 3"})
    assert out["message"] == "Cannot save"


def test_long_message_is_trimmed_and_given_more_time():
    out = normalize_toast({"type": "info", "message": "word " * 200})
    assert len(out["message"]) <= 241 and out["message"].endswith("\u2026")
    assert toast_duration_ms("x" * 200, "error") > toast_duration_ms("ok", "success")
    assert toast_duration_ms("x" * 5000, "error") <= 10000


def test_good_messages_untouched_and_extra_keys_kept():
    out = normalize_toast({"type": "success", "message": "Setup completed successfully!",
                           "action": {"kind": "view_receipts", "receipt_ids": [1]}})
    assert out["message"] == "Setup completed successfully!" and out["action"]["receipt_ids"] == [1]
