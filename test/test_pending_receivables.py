import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services import pending_receivables as pr


def xlsx(rows, sheet="Receivables"):
    wb = Workbook(); ws = wb.active; ws.title = sheet
    for r in rows: ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


# ---- row validation -------------------------------------------------------------------------------------------
def test_blank_rows_skipped_and_good_row_cleaned():
    rows, errs = pr.clean_rows([{}, {"flat_number": " a-101 ", "amount": "₹ 30,000.5", "overdue_days": "20", "remarks": " Feb  dues "}])
    assert errs == []
    assert rows == [{"flat_number": "a-101", "amount": "30000.50", "overdue_days": 20, "remarks": "Feb dues"}]


def test_known_flat_spelling_wins():
    rows, _ = pr.clean_rows([{"flat_number": "a - 101", "amount": 5}], known_flats=["A-101"])
    assert rows[0]["flat_number"] == "A-101"


@pytest.mark.parametrize("row,frag", [
    ({"flat_number": "", "amount": "10"}, "flat number is required"),
    ({"flat_number": "A-1", "amount": ""}, "amount is required"),
    ({"flat_number": "A-1", "amount": "abc"}, "amount must be a number"),
    ({"flat_number": "A-1", "amount": "0"}, "greater than 0"),
    ({"flat_number": "A-1", "amount": "-5"}, "greater than 0"),
    ({"flat_number": "A-1", "amount": "1.234"}, "2 decimal"),
    ({"flat_number": "A-1", "amount": "nan"}, "amount is required"),
    ({"flat_number": "A-1", "amount": "inf"}, "amount must be a number"),
    ({"flat_number": "A-1", "amount": "10", "overdue_days": "-3"}, "days overdue"),
    ({"flat_number": "A-1", "amount": "10", "overdue_days": "2.5"}, "whole number"),
    ({"flat_number": "x" * 40, "amount": "10"}, "longer than"),
])
def test_row_errors(row, frag):
    rows, errs = pr.clean_rows([row])
    assert rows == [] and len(errs) == 1 and errs[0].startswith("Row 1:") and frag in errs[0]


def test_duplicate_flat_reported_case_and_spacing_insensitive():
    rows, errs = pr.clean_rows([{"flat_number": "A-101", "amount": 1}, {"flat_number": "a - 101", "amount": 2}])
    assert len(rows) == 1 and "already on row 1" in errs[0] and errs[0].startswith("Row 2:")


def test_numeric_excel_flat_numbers():
    rows, _ = pr.clean_rows([{"flat_number": 101.0, "amount": 5}, {"flat_number": 7, "amount": 5}])
    assert [r["flat_number"] for r in rows] == ["101", "7"]


# ---- merge ----------------------------------------------------------------------------------------------------
def test_merge_add_upserts_instead_of_doubling():
    a = [{"flat_number": "A-1", "amount": "10.00", "overdue_days": None, "remarks": ""}]
    inc = [{"flat_number": "a-1", "amount": "99.00", "overdue_days": 3, "remarks": ""},
           {"flat_number": "B-2", "amount": "5.00", "overdue_days": None, "remarks": ""}]
    rows, added, updated = pr.merge(a, inc, "add")
    assert (added, updated) == (1, 1) and len(rows) == 2 and rows[0]["amount"] == "99.00"
    again, added2, updated2 = pr.merge(rows, inc, "add")          # uploading the same file twice
    assert (added2, updated2) == (0, 2) and pr.total(again) == Decimal("104.00")


def test_merge_replace():
    rows, added, updated = pr.merge([{"flat_number": "Z", "amount": "1"}], [{"flat_number": "A", "amount": "2.00"}], "replace")
    assert rows == [{"flat_number": "A", "amount": "2.00"}] and (added, updated) == (1, 0)


# ---- upload ---------------------------------------------------------------------------------------------------
def test_upload_blank_optional_cells_do_not_become_nan():
    """Regression: pandas dtype=str turned blank cells into 'nan' (days error / remarks 'nan')."""
    data = xlsx([["flat_number", "amount", "overdue_days", "remarks"],
                 ["A-101", 30000, None, None], ["A-102", "1,250.50", 15, "Mar"]])
    rows, errs, info = pr.parse_upload(data, "r.xlsx")
    assert errs == [] and info["rows_read"] == 2
    assert rows[0] == {"flat_number": "A-101", "amount": "30000.00", "overdue_days": None, "remarks": ""}
    assert rows[1]["amount"] == "1250.50" and rows[1]["overdue_days"] == 15


def test_upload_reports_spreadsheet_row_numbers_and_aliases_and_title_line():
    data = xlsx([["Opening dues 2026"], ["Flat No.", "Outstanding", "Days overdue"],
                 ["A-1", 10, 1], [None, 5, None], ["A-3", "x", None]])
    rows, errs, info = pr.parse_upload(data, "r.xlsx")
    assert info["header_row"] == 2 and len(rows) == 1
    assert errs[0].startswith("Row 4:") and "flat number is required" in errs[0]
    assert errs[1].startswith("Row 5:") and "amount must be a number" in errs[1]


def test_upload_falls_back_to_first_sheet_and_csv_semicolons():
    rows, errs, _ = pr.parse_upload(xlsx([["flat", "amount"], ["A-1", 5]], sheet="Sheet1"), "r.xlsx")
    assert rows[0]["flat_number"] == "A-1" and not errs
    rows, errs, _ = pr.parse_upload("flat_number;amount;remarks\nB-1;7,5;hello\n".encode(), "r.csv")
    assert errs and "amount" in errs[0]                           # '7,5' is not 2-decimal-safe: reported, not guessed
    rows, errs, _ = pr.parse_upload("flat_number,amount,remarks\nB-1,75,hello\n".encode("utf-8-sig"), "r.csv")
    assert rows == [{"flat_number": "B-1", "amount": "75.00", "overdue_days": None, "remarks": "hello"}] and not errs


@pytest.mark.parametrize("data,name,frag", [
    (b"", "x.xlsx", "empty"),
    (b"not a zip", "x.xlsx", "not a valid .xlsx"),
    (xlsx([["a", "b"], [1, 2]]), "x.xlsx", "header row"),
    (b"x" * (2 * 1024 * 1024 + 1), "x.xlsx", "2 MB"),
])
def test_unusable_files(data, name, frag):
    with pytest.raises(pr.UploadError) as e:
        pr.parse_upload(data, name)
    assert frag in str(e.value)


def test_template_round_trip_keeps_leading_zero_flats():
    rows = [{"flat_number": "07", "amount": "100.50", "overdue_days": 4, "remarks": "x"}]
    back, errs, _ = pr.parse_upload(pr.build_template(rows, known_flats=["07", "08"]), "t.xlsx")
    assert errs == [] and back == [{"flat_number": "07", "amount": "100.50", "overdue_days": 4, "remarks": "x"}]


# ---- tie-out / validator --------------------------------------------------------------------------------------
def test_tie_out_and_validation_errors():
    rows = [{"flat_number": "A", "amount": "30000.00"}]
    bf = [{"side": "Dr", "tab": "SDr", "bf_amount": "30000"}, {"side": "Dr", "tab": "Bank", "bf_amount": "9"}]
    assert pr.tie_out(rows, pr.sdr_total(bf)) == (Decimal("30000.00"), Decimal("30000"), Decimal("0.00"))
    assert pr.validation_errors(rows, pr.sdr_total(bf)) == []
    assert "do not tie" in pr.validation_errors(rows, Decimal("1"))[0]
    assert pr.validation_errors([], Decimal("5")) == []            # nothing entered is allowed
    bad = pr.validation_errors([{"flat_number": "A", "amount": "1"}, {"flat_number": "a", "amount": "1"}], Decimal("2"))
    assert len(bad) == 1 and "already on row 1" in bad[0]
