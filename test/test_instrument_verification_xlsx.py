"""verified.xlsx bulk verification (Central + UP) and the shared tick-box path: atomic, audit row well-formed, safe matching.

Regression tests for: the XLSX audit INSERT having 8 columns but 7 values; xlsx rows committed one by one (so 'Nothing was
verified' was untrue); the UP tick path skipping is_master / regime / already-verified checks; audit resource_id (VARCHAR(64))
overflowing on a long id list; substring title matching; the same instrument processed twice; notification numbers over the
old VARCHAR(100)."""
import base64
import io
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.services import document_signing as ds
from app.services import instrument_verification as iv

ROOT = Path(__file__).resolve().parent.parent
HEADERS = ["#", "Regime", "Instrument Type", "Title", "Enactment Year", "Issuing Authority", "Notification / Gazette No.",
           "In Force / Commencement", "Applies When", "Official URL (Complete)", "Verification Notes"]


# ── fakes ────────────────────────────────────────────────────────────────────────────────────────────────────────

class FakeDB:
    """Transactional fake: writes made through _conn() are applied only if the block exits without an error."""

    def __init__(self, rows, master=True, fail_on_id=None):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.master, self.fail_on_id = master, fail_on_id
        self.committed_verifications, self.audits, self.statements = [], [], []

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        if "is_master_admin" in sql:
            return {"is_master_admin": self.master, "society_id": None}
        if "FROM legal_instrument_catalog" in sql and "ANY(%s)" in sql:
            return [dict(r) for i, r in self.rows.items() if i in params[0]]
        if "FROM legal_instrument_catalog" in sql and "regime_code = %s" in sql and "verification <>" not in sql:
            return [dict(r) for r in self.rows.values() if r["regime_code"] == params[0]]
        if "verification <> 'verified'" in sql:
            return [dict(r, applies_when="always", instrument_type="Central Act", issuing_authority="Government of India")
                    for r in self.rows.values()
                    if r["regime_code"] == params[0] and r["verification"] != "verified"]
        raise AssertionError("unexpected query: " + sql)

    @contextmanager
    def _conn(self):
        pending_v, pending_a = [], []
        db = self

        class Cur:
            def execute(s, sql, params=None):
                db.statements.append(sql)
                if "fn_verify_instrument" in sql:
                    if db.fail_on_id is not None and params[0] == db.fail_on_id:
                        raise RuntimeError("ERROR: value too long for type character varying(100)")
                    pending_v.append(params)
                elif "INSERT INTO audit_events" in sql:
                    check_insert_arity(sql, params)
                    pending_a.append(params)

        class C:
            def cursor(s):
                return Cur()

        yield C()                      # an exception inside the block skips the lines below: a rollback
        self.committed_verifications += pending_v
        self.audits += pending_a


def check_insert_arity(sql, params):
    """The bug that shipped: column count must equal value count, and every %s must have a param."""
    cols = re.search(r"INSERT INTO \w+ \((.*?)\)\s*VALUES", sql, re.S).group(1).split(",")
    vals_src = re.search(r"VALUES \((.*)\)\s*$", sql, re.S).group(1)
    depth, vals, cur = 0, [], ""
    for ch in vals_src:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            vals.append(cur)
            cur = ""
        else:
            cur += ch
    vals.append(cur)
    assert len(cols) == len(vals), f"{len(cols)} columns but {len(vals)} values"
    assert sql.count("%s") == len(params)


def inst(i, title, year=None, regime="CENTRAL", ver="unverified"):
    return {"id": i, "title": title, "enactment_year": year, "regime_code": regime, "verification": ver}


def xlsx(sheet, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(HEADERS)
    for n, (title, year, notif, url) in enumerate(rows, 1):
        ws.append([n, "", "", title, year, "", notif, "", "", url, ""])
    buf = io.BytesIO()
    wb.save(buf)
    return "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode()


OK_URL = "https://www.indiacode.nic.in/x.pdf"


# ── atomic upload ────────────────────────────────────────────────────────────────────────────────────────────────

def test_upload_verifies_matched_rows_and_writes_a_well_formed_audit_row():
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872), inst(2, "Indian Stamp Act, 1899", 1899)])
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "Act 9 of 1872", OK_URL),
                                    ("Indian Stamp Act, 1899", 1899, "Act 2 of 1899", OK_URL)])
    res = iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "verified.xlsx", "ADV/2026/14", "2026-11-01", db=db)
    assert res["verified"] == 2 and res["unmatched"] == []
    assert [p[0] for p in db.committed_verifications] == [1, 2] and db.committed_verifications[0][2] == "master"
    (user, action, resource_id, payload), = db.audits
    assert action == "INSTRUMENTS_VERIFIED_XLSX" and resource_id == "CENTRAL" and len(resource_id) <= 64
    assert json.loads(payload)["ids"] == [1, 2]


def test_a_bad_row_stops_the_whole_upload_and_nothing_is_committed():
    """Before: rows 1..n-1 were already verified when 'Nothing was verified' was raised."""
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872), inst(2, "Indian Stamp Act, 1899", 1899)])
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "Act 9 of 1872", OK_URL),
                                    ("Indian Stamp Act, 1899", 1899, "Act 2 of 1899", "ftp://nope")])
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert "Nothing was verified" in str(e.value) and "Row 3" in str(e.value)
    assert db.committed_verifications == [] and db.audits == []


def test_a_database_error_midway_rolls_everything_back():
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872), inst(2, "Indian Stamp Act, 1899", 1899)], fail_on_id=2)
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "N1", OK_URL), ("Indian Stamp Act, 1899", 1899, "N2", OK_URL)])
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert "value too long" in str(e.value) and db.committed_verifications == [] and db.audits == []


def test_blank_rows_are_skipped_so_a_half_filled_template_works():
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872), inst(2, "Indian Stamp Act, 1899", 1899)])
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "Act 9 of 1872", OK_URL), ("Indian Stamp Act, 1899", 1899, "", "")])
    res = iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert res["verified"] == 1 and res["skipped_incomplete"] == ["Indian Stamp Act, 1899"]


def test_already_verified_rows_are_left_alone():
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872, ver="verified")])
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "N", OK_URL)])
    res = iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert res["verified"] == 0 and res["skipped_verified"] == ["Indian Contract Act, 1872"] and db.audits == []


def test_the_same_instrument_twice_is_refused_not_double_processed():
    """A second pass with different data would flip the row back to 'unverified' through trg_instrument_unverify."""
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872)])
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "N1", OK_URL), ("Indian Contract Act, 1872", 1872, "N2", OK_URL)])
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert "same instrument as row 2" in str(e.value) and db.committed_verifications == []


def test_over_long_notification_number_is_reported_before_any_write():
    db = FakeDB([inst(1, "Code on Wages, 2019", 2019)])
    c = xlsx("Central Acts Rules", [("Code on Wages, 2019", 2019, "x" * 300, OK_URL)])
    with pytest.raises(ds.SigningRefused) as e:
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=db)
    assert "300 characters" in str(e.value) and db.committed_verifications == []


def test_master_only_wrong_sheet_future_date_and_missing_opinion():
    c = xlsx("Central Acts Rules", [("Indian Contract Act, 1872", 1872, "N", OK_URL)])
    rows = [inst(1, "Indian Contract Act, 1872", 1872)]
    with pytest.raises(ds.SigningRefused):
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2026-11-01", db=FakeDB(rows, master=False))
    with pytest.raises(ds.SigningRefused) as e:                      # a Central file into the UP panel
        iv.verify_from_uploaded_xlsx(9, "UP_AOA_2010", c, "v.xlsx", "ADV/1", "2026-11-01", db=FakeDB(rows))
    assert "UP Acts Rules" in str(e.value)
    with pytest.raises(ds.SigningRefused):
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "ADV/1", "2999-01-01", db=FakeDB(rows))
    with pytest.raises(ds.SigningRefused):
        iv.verify_from_uploaded_xlsx(9, "CENTRAL", c, "v.xlsx", "  ", "2026-11-01", db=FakeDB(rows))


# ── matching ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_matching_is_exact_first_and_does_not_guess_on_short_titles():
    rows = [inst(1, "Rules"), inst(2, "Real Estate (Regulation and Development) Act, 2016 (RERA)", 2016)]
    assert iv._match_instrument(rows, "Real Estate (Regulation and Development) Act, 2016 (RERA)", 2016)[0]["id"] == 2
    assert iv._match_instrument(rows, "Real Estate (Regulation and Development) Act, 2016", 2016)[0]["id"] == 2   # contained
    assert iv._match_instrument(rows, "Companies Rules, 2014")[1] == "none"       # 'Rules' is too short to be 'contained in'


def test_ambiguous_title_is_reported_not_guessed():
    rows = [inst(1, "Model Bye-Laws of the Association", 2011), inst(2, "Model Bye-Laws of the Association", 2019)]
    assert iv._match_instrument(rows, "Model Bye-Laws of the Association")[1] == "ambiguous"
    assert iv._match_instrument(rows, "Model Bye-Laws of the Association", 2019)[0]["id"] == 2     # the year settles it


# ── tick-box path, both regimes ──────────────────────────────────────────────────────────────────────────────────

def _items(*ids):
    return [{"id": i, "notification_no": f"N-{i}", "source_url": f"https://example.gov.in/{i}"} for i in ids]


def test_up_tick_path_goes_through_the_same_checks():
    db = FakeDB([inst(1, "UP Act", 2010, "UP_AOA_2010"), inst(2, "Central Act", 2016, "CENTRAL"), inst(3, "UP Done", 2011, "UP_AOA_2010", "verified")])
    with pytest.raises(ds.SigningRefused):                                   # not master
        iv.verify_many_as_master(9, _items(1), "ADV/1", db=FakeDB([inst(1, "UP Act", 2010, "UP_AOA_2010")], master=False), regime_code="UP_AOA_2010")
    with pytest.raises(ds.SigningRefused) as e:                              # a tampered id from another regime, and a verified one
        iv.verify_many_as_master(9, _items(1, 2, 3), "ADV/1", db=db, regime_code="UP_AOA_2010")
    assert "not a UP instrument" in str(e.value) and "already verified" in str(e.value) and db.committed_verifications == []
    assert iv.verify_many_as_master(9, _items(1), "ADV/1", "2026-11-01", db=db, regime_code="UP_AOA_2010") == 1
    assert db.audits[0][2] == "UP_AOA_2010"


def test_audit_resource_id_never_overflows_varchar_64_with_many_ids():
    rows = [inst(i, f"Instrument number {i}", 2000, "UP_AOA_2010") for i in range(1000, 1060)]
    db = FakeDB(rows)
    assert iv.verify_many_as_master(9, _items(*range(1000, 1060)), "ADV/1", "2026-11-01", db=db, regime_code="UP_AOA_2010") == 60
    assert len(db.audits[0][2]) <= 64 and len(json.loads(db.audits[0][3])["ids"]) == 60


def test_the_same_id_twice_and_an_unknown_regime_are_refused():
    db = FakeDB([inst(1, "A long enough title", 2000)])
    with pytest.raises(ds.SigningRefused):
        iv.verify_many_as_master(9, _items(1, 1), "ADV/1", db=db)
    with pytest.raises(ds.SigningRefused):
        iv.verify_many_as_master(9, _items(1), "ADV/1", db=db, regime_code="GUJ_APT_1972")


# ── template ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_template_lists_only_unverified_instruments_of_the_regime():
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872), inst(2, "Done Act", 2000, ver="verified"), inst(3, "UP Act", 2010, "UP_AOA_2010")])
    rows = iv.template_rows("CENTRAL", db=db)
    assert [r[3] for r in rows] == ["Indian Contract Act, 1872"] and rows[0][1] == "CENTRAL" and rows[0][6] == rows[0][9] == ""


# ── the real file shipped in the repo, against the real seed catalogue ───────────────────────────────────────────

@pytest.mark.skipif(not (ROOT / "verified.xlsx").exists(), reason="verified.xlsx not in the repo")
@pytest.mark.parametrize("regime,sheet", [("CENTRAL", "Central Acts Rules"), ("UP_AOA_2010", "UP Acts Rules")])
def test_repo_verified_xlsx_verifies_against_the_seed_catalogue(regime, sheet):
    from database.legal_reference import INSTRUMENTS
    seeded = [inst(n, r["title"], r["enactment_year"], r["regime_code"]) for n, r in enumerate(INSTRUMENTS, 1)]
    db = FakeDB(seeded)
    raw = (ROOT / "verified.xlsx").read_bytes()
    contents = "data:application/vnd.openxmlformats;base64," + base64.b64encode(raw).decode()
    ws = load_workbook(io.BytesIO(raw), data_only=True)[sheet]
    fillable = sum(1 for r in ws.iter_rows(min_row=2, values_only=True) if r[3] and r[6] and r[9] and str(r[9]).startswith("http"))
    res = iv.verify_from_uploaded_xlsx(9, regime, contents, "verified.xlsx", "ADV/2026/14", "2026-11-01", db=db)
    assert res["verified"] + len(res["unmatched"]) == fillable
    # Known gap in the data, reported to the master rather than guessed at: verified.xlsx carries an e-signature rules row that is
    # not in the seeded Central catalogue (database/legal_reference.py). Add it there if it should be tracked.
    assert res["unmatched"] == (["Electronic Signature (Authentication Technique & Procedure) Rules, 2016"] if regime == "CENTRAL" else [])
    assert res["verified"] >= 6
    # the 105-117 character gazette citations (over the old VARCHAR(100)) are accepted
    assert all(len(str(p[3])) <= 255 for p in db.committed_verifications)
    assert any(len(str(p[3])) > 100 for p in db.committed_verifications) or regime == "UP_AOA_2010"


# ── the workflow end to end: download template -> fill in -> upload ──────────────────────────────────────────────

@pytest.mark.parametrize("regime,sheet", [("CENTRAL", "Central Acts Rules"), ("UP_AOA_2010", "UP Acts Rules")])
def test_downloaded_template_round_trips_through_upload(regime, sheet):
    from app.dash_apps.callbacks.master_rules_callbacks import _build_template_bytes
    from database.legal_reference import INSTRUMENTS
    seeded = [inst(n, r["title"], r["enactment_year"], r["regime_code"]) for n, r in enumerate(INSTRUMENTS, 1)]
    db = FakeDB(seeded)
    template = _build_template_bytes(sheet, iv.template_rows(regime, db=db))
    wb = load_workbook(io.BytesIO(template))
    ws = wb[sheet]
    assert [c.value for c in ws[1]] == HEADERS and ws.max_row == 1 + sum(1 for r in seeded if r["regime_code"] == regime)
    for row in ws.iter_rows(min_row=2):                    # the master fills in only these two columns
        row[6].value, row[9].value = f"Notification {row[0].value}/2026", f"https://www.indiacode.nic.in/{row[0].value}.pdf"
    buf = io.BytesIO()
    wb.save(buf)
    contents = "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode()
    res = iv.verify_from_uploaded_xlsx(9, regime, contents, "verified.xlsx", "ADV/2026/14", "2026-11-01", db=db)
    assert res["unmatched"] == [] and res["verified"] == ws.max_row - 1


def test_an_untouched_template_verifies_nothing():
    """The old template carried a pre-filled example row that an unedited upload would have verified."""
    from app.dash_apps.callbacks.master_rules_callbacks import _build_template_bytes
    db = FakeDB([inst(1, "Indian Contract Act, 1872", 1872)])
    raw = _build_template_bytes("Central Acts Rules", iv.template_rows("CENTRAL", db=db))
    contents = "data:application/octet-stream;base64," + base64.b64encode(raw).decode()
    res = iv.verify_from_uploaded_xlsx(9, "CENTRAL", contents, "verified.xlsx", "ADV/1", "2026-11-01", db=db)
    assert res["verified"] == 0 and db.committed_verifications == [] and db.audits == []


def test_callbacks_register_and_every_component_id_they_use_exists_in_the_pages():
    """Registers the module on a real Dash app (this raised ImportError before: PreventUpdate is not in `dash` in 2.14.2), then
    checks each fixed-id Input/Output/State of the civ-* callbacks is present in the rendered Central and UP pages."""
    import dash
    from app.dash_apps.callbacks import master_rules_callbacks as m
    from app.dash_apps.pages import portal_pages as pp
    from database.db_manager import db as real_db
    from database.legal_reference import INSTRUMENTS

    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    m.register_master_rules_callbacks(app)

    def fake_exec(sql, params=None, fetch_one=False, fetch_all=False):
        out = []
        for n, r in enumerate(INSTRUMENTS, 1):
            if r["regime_code"] == ("UP_AOA_2010" if "'UP_AOA_2010'" in sql else "CENTRAL"):
                out.append(dict(r, id=n, verification="unverified", source_url=None, notification_no=None, verifier_role=None,
                                last_verified_on=None))
        return out

    real_db._execute = fake_exec
    try:
        ids = set()

        def walk(c):
            cid = getattr(c, "id", None)
            if isinstance(cid, str):
                ids.add(cid)
            kids = getattr(c, "children", None)
            for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
                if hasattr(k, "to_plotly_json"):
                    walk(k)

        for page in (pp._rwa_compliance_india_page("#c96a19", "master"), pp._rwa_compliance_up_page("#c96a19", "master")):
            walk(page)
    finally:
        del real_db._execute                                    # restore the class method
    need = {"civ-opinion", "civ-date", "civ-all", "civ-verify", "civ-msg", "civ-xlsx-upload", "civ-xlsx-verify", "civ-xlsx-name",
            "civ-xlsx-download-template", "civ-xlsx-template-download",
            "civ-opinion-up", "civ-date-up", "civ-all-up", "civ-verify-up", "civ-msg-up", "civ-xlsx-upload-up", "civ-xlsx-verify-up",
            "civ-xlsx-name-up", "civ-xlsx-download-template-up", "civ-xlsx-template-download-up"}
    assert need <= ids, sorted(need - ids)
    assert not [i for i in ids if i.startswith("civ-xlsx-opinion") or i.startswith("civ-xlsx-date") or i.endswith("xlsx-msg")]
