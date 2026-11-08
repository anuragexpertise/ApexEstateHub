"""Builder's Declaration of undivided interest: workbook parsing, plan checks and the completion check (hermetic)."""
import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services import undivided_declaration as ud


def book(rows, headers=ud.HEADERS, sheet="Declaration", pct_format=None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(list(headers))
    for r in rows:
        ws.append(r)
    if pct_format:
        for r in range(2, ws.max_row + 1):
            ws.cell(r, 3).number_format = pct_format
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_good_workbook_parses_with_six_decimal_shares():
    rows, errs = ud.parse_workbook(book([["A-101", 1200, 60.5], ["A-102", 1100.4, 39.5]]))
    assert errs == []
    assert [r["flat"] for r in rows] == ["A-101", "A-102"]
    assert rows[1]["area"] == 1100 and rows[1]["area_rounded"] is True
    assert sum(r["pct"] for r in rows) == Decimal("100.000000")


def test_numeric_flat_numbers_and_blank_rows():
    rows, errs = ud.parse_workbook(book([[101.0, 900, 50], [None, None, None], ["102", 900, 50]]))
    assert errs == [] and [r["flat"] for r in rows] == ["101", "102"]


def test_percent_formatted_cells_are_read_as_percentages():
    rows, errs = ud.parse_workbook(book([["A", 100, 0.6], ["B", 100, 0.4]], pct_format="0.00%"))
    assert errs == [] and [r["pct"] for r in rows] == [Decimal("60.000000"), Decimal("40.000000")]


@pytest.mark.parametrize("rows,frag", [
    ([["A", 100, 50], ["a", 100, 50]], "repeats row 2"),
    ([["A", 100, None]], "Undivided-Interest is blank"),
    ([["A", None, 100]], "Area must be greater than zero"),
    ([["A", 100, "abc"]], "not a number"),
    ([["A", 100, 0]], "above 0"),
    ([["A", 100, 100.1]], "at most 100"),
    ([["A", 100, 33.1234567]], "more than 6 decimal places"),
    ([["", 100, 100]], "Flat No is blank"),
])
def test_bad_rows_are_named_with_their_row(rows, frag):
    _rows, errs = ud.parse_workbook(book(rows))
    assert any(frag in e for e in errs), errs


def test_missing_heading_and_wrong_file_types():
    _r, errs = ud.parse_workbook(book([["A", 1, 100]], headers=("Flat No", "Area", "Share of land")))
    assert "Missing: Undivided-Interest" in errs[0]
    assert ud.parse_workbook(b"not a workbook")[1]
    assert ud.parse_workbook(b"")[1]


def test_heading_aliases_and_first_sheet_fallback():
    rows, errs = ud.parse_workbook(book([["A", 10, 100]], headers=("Flat Number", "Area (sq ft)", "Undivided Interest (%)"), sheet="Sheet1"))
    assert errs == [] and rows[0]["pct"] == Decimal("100.000000")


def _fake_db(monkeypatch, existing, passed=0, slots=100):
    def rows(sql, params=None):
        return existing
    def row(sql, params=None):
        return {"n": passed}
    monkeypatch.setattr(ud, "_rows", rows)
    monkeypatch.setattr(ud, "_row", row)
    import app.services.plan_limits as pl
    monkeypatch.setattr(pl, "remaining_apartment_slots", lambda sid: (slots, "Test", slots))


def _rowset(*pairs):
    return [{"row": i + 2, "flat": f, "area": 1000, "area_rounded": False, "pct": Decimal(str(p)).quantize(ud.SIX_DP)}
            for i, (f, p) in enumerate(pairs)]


def test_plan_requires_total_100(monkeypatch):
    _fake_db(monkeypatch, [])
    _p, errs = ud.plan(1, _rowset(("A", 60), ("B", 30)))
    assert any("90" in e and "short of 100%" in e for e in errs)
    _p, errs = ud.plan(1, _rowset(("A", 0.6), ("B", 0.4)))
    assert any("fractions of 1" in e for e in errs)
    _p, errs = ud.plan(1, _rowset(("A", 60), ("B", 40)))
    assert errs == []


def test_plan_splits_update_and_create_and_demands_every_enrolled_flat(monkeypatch):
    _fake_db(monkeypatch, [{"id": 7, "flat_number": "A-101", "active": True}, {"id": 8, "flat_number": "A-102", "active": True}])
    p, errs = ud.plan(1, _rowset(("a 101", 50), ("B-1", 50)))
    assert [r["id"] for r in p["update"]] == [7] and [r["flat"] for r in p["create"]] == ["B-1"]
    assert any("missing from the file: A-102" in e for e in errs)


def test_plan_refuses_inactive_flat_plan_cap_and_passed_resolutions(monkeypatch):
    _fake_db(monkeypatch, [{"id": 7, "flat_number": "A", "active": False}], passed=1, slots=0)
    _p, errs = ud.plan(1, _rowset(("A", 50), ("B", 50)))
    text = " ".join(errs)
    assert "inactive" in text and "only 0 slot" in text and "already been passed" in text


def test_blockers_need_evidence_unless_a_reason_and_always_need_a_balanced_total(monkeypatch):
    balanced = {"apartments_total": 4, "apartments_missing": 0, "total_declared_pct": Decimal("100"), "balanced": True}
    monkeypatch.setattr(ud, "_row", lambda sql, params=None: balanced)
    monkeypatch.setattr(ud, "latest_evidence", lambda sid: None)
    assert len(ud.blockers(1)) == 1
    assert len(ud.blockers(1, "short")) == 1
    assert ud.blockers(1, "Old society, no builder Declaration exists") == []
    unbalanced = {"apartments_total": 4, "apartments_missing": 1, "total_declared_pct": Decimal("75"), "balanced": False}
    monkeypatch.setattr(ud, "_row", lambda sql, params=None: unbalanced)
    monkeypatch.setattr(ud, "latest_evidence", lambda sid: {"sha256": "x"})
    out = ud.blockers(1, "any reason that is long enough")
    assert len(out) == 1 and "75%" in out[0] and "1 flat(s) missing" in out[0]
