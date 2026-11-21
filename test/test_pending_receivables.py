import datetime
import io
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

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


# ---- B2 regression: str vs bytes -------------------------------------------------
def test_parse_upload_accepts_str_data_url():
    """B2: a dcc.Upload data-URL string (str) must decode to bytes, not raise
    'a bytes-like object is required, not \'str\''."""
    data = xlsx([["flat_number", "amount", "overdue_days", "remarks"],
                 ["A-101", 30000, 5, "Mar dues"]])
    import base64
    data_url = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + base64.b64encode(data).decode()
    rows, errs, info = pr.parse_upload(data_url, "r.xlsx")
    assert errs == [] and info["rows_read"] == 1
    assert rows[0] == {"flat_number": "A-101", "amount": "30000.00", "overdue_days": 5, "remarks": "Mar dues"}


def test_parse_upload_accepts_raw_bytes():
    """B2: raw bytes still work (the pre-str path)."""
    data = xlsx([["flat_number", "amount", "overdue_days", "remarks"],
                 ["A-102", "1,250.50", None, None]])
    rows, errs, _ = pr.parse_upload(data, "r.xlsx")
    assert errs == [] and rows[0]["amount"] == "1250.50"


def test_parse_upload_non_xlsx_user_visible_error():
    """B2: a non-xlsx file returns a user-visible UploadError, not a stack trace."""
    with pytest.raises(pr.UploadError) as e:
        pr.parse_upload(b"not a zip file at all", "r.xlsx")
    assert "valid .xlsx" in str(e.value)




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
    back, errs, _ = pr.parse_upload(pr.build_template(fy="2026", rows=rows, known_flats=["07", "08"]), "t.xlsx")
    assert errs == [] and back == [{"flat_number": "07", "amount": "100.50", "overdue_days": 4, "remarks": "x"}]


def test_arrears_template_new_sheet_and_columns():
    from openpyxl import load_workbook
    import io
    buf = io.BytesIO(pr.build_template(known_flats=["07", "08"], fy="2026", as_on="2026-09-30"))
    wb = load_workbook(buf)
    assert wb.sheetnames[0] == "2026"
    ws = wb["2026"]
    assert [c.value for c in ws[1]] == ["flat_no", "amount", "due_days", "remarks", "as_on_date"]
    # as_on_date prefilled on every row; flat column text-formatted
    assert ws["E2"].value == "2026-09-30" and ws["E3"].value == "2026-09-30"
    assert ws["A2"].number_format == "@"


def test_parse_upload_reads_fy_sheet_and_validates_as_on_date():
    from openpyxl import Workbook
    import io
    wb = Workbook()
    ws = wb.active
    ws.title = "2026"
    ws.append(["flat_no", "amount", "due_days", "remarks", "as_on_date"])
    ws.append(["07", "100.00", "", "", "2026-09-30"])
    ws.append(["08", "200.00", "", "", "2026-09-30"])
    buf = io.BytesIO()
    wb.save(buf)
    back, errs, _ = pr.parse_upload(buf.getvalue(), "t.xlsx", known_flats=["07", "08"], fy="2026", as_on="2026-09-30")
    assert errs == []
    assert {r["flat_number"] for r in back} == {"07", "08"}

    # wrong as_on_date is flagged on that row
    wb2 = Workbook()
    ws2 = wb2.active
    ws2.title = "2026"
    ws2.append(["flat_no", "amount", "due_days", "remarks", "as_on_date"])
    ws2.append(["07", "100.00", "", "", "2025-01-01"])
    buf2 = io.BytesIO()
    wb2.save(buf2)
    back2, errs2, _ = pr.parse_upload(buf2.getvalue(), "t.xlsx", known_flats=["07", "08"], fy="2026", as_on="2026-09-30")
    assert any("as_on_date must be 2026-09-30" in e for e in errs2)


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


# ---- Apt-Arrears template + strict importer (NMF tasks B and C) -----------------------------------------------
_HDR = ["flat_no", "amount", "due_days", "remarks", "as_on_date"]
_YEAR = {"known_flats": ["101"], "fy": 2026, "as_on": "2026-04-01"}


def _apt(as_on_cell, sheet="2026", header=None, flat="101"):
    return xlsx([header or _HDR, [flat, 500, 10, "", as_on_cell]], sheet=sheet)


def test_template_has_one_year_sheet_new_headers_and_no_legacy_sheet():
    wb = load_workbook(io.BytesIO(pr.build_template(fy=2026, known_flats=["101"], as_on="2026-04-01")))
    assert wb.sheetnames[0] == "2026" and "Receivables" not in wb.sheetnames
    ws = wb["2026"]
    assert [c.value for c in ws[1]] == _HDR
    assert ws["E2"].value == "2026-04-01"                     # as_on_date prefilled on every flat row
    notes = " ".join(str(r[0].value) for r in wb["Instructions"].iter_rows())
    assert "due_days" in notes and "as_on_date" in notes
    assert "overdue_days" not in notes and "flat_number" not in notes


def test_build_template_requires_a_financial_year():
    with pytest.raises(TypeError):
        pr.build_template()


def test_template_round_trip_with_year_and_as_on_date():
    rows = [{"flat_number": "07", "amount": "100.50", "overdue_days": 4, "remarks": "x"}]
    data = pr.build_template(fy=2026, rows=rows, known_flats=["07"], as_on="2026-04-01")
    back, errs, _ = pr.parse_upload(data, "t.xlsx", known_flats=["07"], fy=2026, as_on="2026-04-01")
    assert errs == [] and back == [{"flat_number": "07", "amount": "100.50", "overdue_days": 4, "remarks": "x"}]


@pytest.mark.parametrize("cell", ["2026-04-01", datetime.date(2026, 4, 1), datetime.datetime(2026, 4, 1)])
def test_as_on_date_accepts_text_date_and_datetime_cells(cell):
    clean, errs, _ = pr.parse_upload(_apt(cell), "t.xlsx", **_YEAR)
    assert errs == [] and len(clean) == 1


@pytest.mark.parametrize("cell", ["2026-05-01", datetime.date(2026, 5, 1), datetime.datetime(2026, 5, 1, 9, 30)])
def test_as_on_date_mismatch_names_the_row(cell):
    _, errs, _ = pr.parse_upload(_apt(cell), "t.xlsx", **_YEAR)
    assert errs == ["Row 2: as_on_date must be 2026-04-01."]


def test_blank_as_on_date_cell_is_allowed():
    _, errs, _ = pr.parse_upload(_apt(None), "t.xlsx", **_YEAR)
    assert errs == []


def test_old_receivables_sheet_is_rejected_with_a_clear_message():
    old = xlsx([["flat_number", "amount", "overdue_days", "remarks"], ["101", 500, 10, ""]], sheet="Receivables")
    with pytest.raises(pr.UploadError, match=r"no sheet named '2026'.*fresh Apt-Arrears template"):
        pr.parse_upload(old, "t.xlsx", **_YEAR)


def test_wrong_year_sheet_is_rejected_and_names_the_expected_sheet():
    with pytest.raises(pr.UploadError, match="no sheet named '2026'"):
        pr.parse_upload(_apt("2026-04-01", sheet="2025"), "t.xlsx", **_YEAR)


@pytest.mark.parametrize("header,frag", [
    (["flat_number", "amount", "due_days", "remarks", "as_on_date"], "old 'flat_number' column"),
    (["flat_no", "amount", "overdue_days", "remarks", "as_on_date"], "old 'overdue_days' column"),
])
def test_old_column_names_are_rejected_even_on_the_right_sheet(header, frag):
    with pytest.raises(pr.UploadError, match=frag):
        pr.parse_upload(_apt("2026-04-01", header=header), "t.xlsx", **_YEAR)


def test_missing_header_message_uses_the_new_column_names():
    with pytest.raises(pr.UploadError) as exc:
        pr.parse_upload(xlsx([["a", "b"], [1, 2]], sheet="2026"), "t.xlsx", **_YEAR)
    msg = str(exc.value)
    assert "flat_no" in msg and "due_days" in msg and "overdue_days" not in msg and "flat_number" not in msg
