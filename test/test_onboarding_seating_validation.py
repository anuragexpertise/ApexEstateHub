"""Regression tests for "Treasurer could not be seated: an unexpected error stopped it" at the Founding committee stage.

Offline: no database needed. Each case below used to get past validation, reach Postgres or Pillow, fail there, and show
the admin only "see the server log", so the committee stayed stuck with the President and Secretary seated.
"""
import io

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from app.services import onboarding_service as ob  # noqa: E402


def _image(fmt: str, mode: str = "RGB", size=(400, 150)) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, (20, 30, 40) if mode == "RGB" else 0).save(buf, fmt)
    return buf.getvalue()


def _rows(**treasurer):
    def row(office, n, flat):
        return {"office": office, "name": f"{office} P", "email": f"{n}@x.example", "mobile": "9876543210",
                "flat_number": flat, "flat_area_sqft": "1200", "resolution_ref": "GBM 1"}
    t = row("Treasurer", "t", "A-103")
    t.update(treasurer)
    return [row("President", "p", "A-101"), row("Secretary", "s", "A-102"), t,
            {"office": "Grievance Officer", "name": "G", "email": "g@x.example", "mobile": "9876543213"}]


# ── column widths ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_length_problems_names_each_field_that_will_not_fit():
    msgs = ob._length_problems("Treasurer", "X" * 25, "N" * 101, "+" + "9" * 15)
    text = " ".join(msgs)
    assert len(msgs) == 3
    assert "flat number is 25" in text and "name is 101" in text and "mobile number is 16" in text


def test_length_problems_accepts_values_at_the_limit():
    assert ob._length_problems("Treasurer", "X" * 20, "N" * 100, "9" * 15) == []
    assert ob._length_problems("Treasurer", "A-103", "Ravi Kumar", None) == []


@pytest.mark.parametrize("field,value,fragment", [
    ("flat_number", "Tower-B-Penthouse-1203-E", "flat number is 24"),
    ("name", "N" * 101, "name is 101"),
    ("mobile", "+919876543210123", "mobile number is 16"),
])
def test_election_rows_with_an_oversized_treasurer_value_are_refused_before_anything_is_written(field, value, fragment):
    _data, errors = ob.validate_election_rows(_rows(**{field: value}))
    assert any("Treasurer" in e and fragment in e for e in errors), errors


def test_valid_election_rows_still_pass():
    _data, errors = ob.validate_election_rows(_rows())
    assert errors == []


# ── signature images ───────────────────────────────────────────────────────────────────────────────────────────────
def test_a_real_jpeg_signature_is_accepted():
    """The JPEG signature is three bytes; it used to be compared with a four-byte slice, so every JPEG was refused."""
    ob._check_signature_file("sign.jpg", _image("JPEG"))
    ob._check_signature_file("sign.jpeg", _image("JPEG"))


@pytest.mark.parametrize("fmt,name", [("PNG", "sign.png"), ("WEBP", "sign.webp")])
def test_real_png_and_webp_signatures_are_accepted(fmt, name):
    ob._check_signature_file(name, _image(fmt))


@pytest.mark.parametrize("data", [
    _image("PNG", "RGBA")[:60],                              # right header, cut off
    b"\x89PNG\r\n\x1a\n" + b"not really an image" * 10,      # right header, garbage after it
    b"\xff\xd8\xff" + b"garbage" * 20,                       # a JPEG header over garbage
])
def test_a_damaged_signature_is_refused_with_a_plain_message_not_an_unexpected_error(data):
    with pytest.raises(ob.OnboardingError, match="damaged or incomplete"):
        ob._check_signature_file("sign.png", data)


def test_a_non_image_is_still_refused():
    with pytest.raises(ob.OnboardingError, match="does not look like a real image"):
        ob._check_signature_file("sign.png", b"plain text, not an image")


# ── the message the admin sees when something unforeseen still happens ─────────────────────────────────────────────
class _PgError(Exception):
    def __init__(self, pgcode):
        super().__init__("database detail that must not reach the screen")
        self.pgcode = pgcode


def test_unexpected_errors_get_a_useful_message_without_echoing_database_text():
    too_long = ob._describe_unexpected(_PgError("22001"))
    assert "too long" in too_long and "database detail" not in too_long
    assert "already recorded" in ob._describe_unexpected(_PgError("23505"))
    generic = ob._describe_unexpected(RuntimeError("boom"))
    assert "RuntimeError" in generic and "server log" in generic and "boom" not in generic
