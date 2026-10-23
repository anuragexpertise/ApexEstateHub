"""
Zero-row behaviour of the TDS and GST engines for a society whose rates were left for the CA.

Hermetic: SQL is checked as text (like test_onboarding_followups.py), Python through stubs and the FakeDB.

  1. GST: a missing rate raises only when GST would actually be levied, and says it is pending CA confirmation.
  2. GST: the rate the setup function writes is in force from the first of the accounting-start month.
  3. TDS: the setup function writes an IT2025 twin for each wizard row, because from 1-Apr-2026 the engine reads
     only IT2025 rows.
  4. TDS: a 'section-not-configured' result is never silent (warning text + compliance flag).
"""
from pathlib import Path

import pytest

from database import seed, tds_compliance

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")


def _fn_sql(name: str) -> str:
    start = SQL.index(f"CREATE OR REPLACE FUNCTION {name}")
    nxt = SQL.find("CREATE OR REPLACE FUNCTION", start + 10)
    return SQL[start: nxt if nxt != -1 else len(SQL)]


# ── 1. GST lookup in billing ──────────────────────────────────────────────────
def test_billing_only_raises_for_missing_gst_rate_when_gst_is_levied():
    body = _fn_sql("fn_auto_generate_receivables")
    lookup = body.index("SELECT cgst_rate_pct, sgst_rate_pct INTO v_cgst_rate, v_sgst_rate")
    gate = body.index("IF v_total_taxable > v_gst_threshold AND v_gate_state = 'above' THEN")
    raise_at = body.index("No active GST rate found")
    # nothing between the lookup and the levy decision may abort billing
    assert "RAISE EXCEPTION" not in body[lookup:gate]
    # the one raise sits inside the levy branch
    assert gate < raise_at < body.index("v_gst_cgst := ROUND(", gate)
    assert body.count("No active GST rate found") == 1


def test_billing_gst_message_says_pending_ca_confirmation():
    assert "pending CA confirmation" in _fn_sql("fn_auto_generate_receivables")
    # every 'no rate' raise in the file (billing and asset disposal) names the CA, so none reads as a system fault
    for chunk in SQL.split("No active GST rate found")[1:]:
        assert "pending CA confirmation" in chunk[:260]


# ── 2. GST effective date ─────────────────────────────────────────────────────
def test_setup_function_stamps_gst_rate_from_the_calc_start_month():
    body = _fn_sql("fn_complete_society_setup")
    ins = body.index("INSERT INTO gst_rates")
    block = body[ins: ins + 500]
    assert "date_trunc('month'" in block and "p_calc_start" in block
    assert "CURRENT_DATE);" not in block          # no longer 'in force from today'


def test_tab_inserts_first_gst_rate_from_the_calc_start_month(monkeypatch):
    from app.services import tax_rate_service as trs
    calls = []

    class _DB:
        def _execute(self, sql, params=None, **kw):
            calls.append((sql, params))
            return None

    monkeypatch.setattr(trs, "db", _DB())
    monkeypatch.setattr(trs, "_require", lambda sid: None)
    monkeypatch.setattr(trs, "mark_pending", lambda sid: None)
    monkeypatch.setattr(trs, "audit_event", lambda *a, **k: None)
    trs.save_gst_rates(5, 9, 9)
    insert = [c for c in calls if c[0].lstrip().startswith("INSERT INTO gst_rates")]
    assert len(insert) == 1
    sql, params = insert[0]
    assert "date_trunc('month'" in sql and "calc_start_date" in sql and "CURRENT_DATE)" in sql
    assert params == (9.0, 9.0, 5)


# ── 3. IT2025 twin ────────────────────────────────────────────────────────────
def test_setup_function_writes_an_it2025_twin():
    body = _fn_sql("fn_complete_society_setup")
    assert "jsonb_typeof(v_item->'it2025') = 'object'" in body
    twin = body[body.index("jsonb_typeof(v_item->'it2025')"):]
    twin = twin[: twin.index("END LOOP")]
    assert "'IT2025'" in twin and "DATE '2026-04-01'" in twin
    # the RATE is the one the Admin / CA entered, never one taken from the statutory table
    assert "(v_item->>'rate')::NUMERIC" in twin and "it2025'->>'rate'" not in twin


def test_twin_matches_the_engine_cutover_date():
    # fn_compute_tds_pct switches Act on this exact date; the twin must start on it.
    assert "DATE '2026-04-01'" in _fn_sql("fn_compute_tds_pct")
    assert seed.TDS_IT2025_EFFECTIVE_FROM == "2026-04-01"


def test_it2025_twin_carries_statutory_figures_only():
    t = seed.it2025_twin("194C", "ind_huf")
    assert t == {"single_bill_threshold": 30000, "annual_aggregate_threshold": 100000,
                 "threshold_inclusive": False, "threshold_basis": "bill",
                 "section_2025": "Sec 393(1) Sl. 6(i) [D(a)]"}
    assert "rate" not in t and "rate_no_pan" not in t
    rent = seed.it2025_twin("194-I", "land_building")
    assert rent["threshold_basis"] == "month" and rent["single_bill_threshold"] == 50000   # not the 1961 yearly 2.4 lakh
    assert seed.it2025_twin("194-IA")["threshold_inclusive"] is True


def test_sections_without_a_2025_row_get_no_twin():
    missing = {s for (s, d, *_r) in seed.TDS_SECTION_RATE_SEED if seed.it2025_twin(s, d) is None}
    # 206AB was omitted by the Finance Act 2025; the others are simply not in the 2025 table seeded here.
    assert missing == {"192A", "193", "194F", "206AB"}


def test_discriminator_must_match_exactly():
    assert seed.it2025_twin("194C", None) is None
    assert seed.it2025_twin("194C", "ind_huf") is not None


# ── TDS tab labels ────────────────────────────────────────────────────────────
def test_tab_label_tells_the_two_acts_apart():
    from app.dash_apps.pages.tax_rates_page import act_line
    import datetime as dt
    a = act_line({"act_version": "IT2025", "effective_from": dt.date(2026, 4, 1)})
    b = act_line({"act_version": "IT1961", "effective_from": dt.date(2025, 4, 1)})
    assert a == "Income-tax Act 2025 · from 01 Apr 2026"
    assert b == "Income-tax Act 1961 · from 01 Apr 2025"


def test_tds_rows_query_selects_act_version_and_orders_by_date(monkeypatch):
    from app.services import tax_rate_service as trs
    seen = {}

    class _DB:
        def _execute(self, sql, params=None, **kw):
            seen["sql"] = sql
            return []

    monkeypatch.setattr(trs, "db", _DB())
    assert trs.tds_rows(3) == []
    assert "act_version" in seen["sql"] and "effective_from, id" in seen["sql"]


# ── 4. 'section-not-configured' is never silent ───────────────────────────────
class _CaptureDB:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def _execute(self, sql, params=None, **kw):
        if self.fail:
            raise RuntimeError("db down")
        self.calls.append((sql, params))


def test_flag_is_inserted_once_per_expense():
    db = _CaptureDB()
    assert tds_compliance.flag_unconfigured_section(db, 7, 99, "194J", "professional", "2026-10-01") is True
    sql, params = db.calls[0]
    assert "INSERT INTO compliance_flags" in sql
    assert "ON CONFLICT (source_table, source_id, rule_code) DO NOTHING" in sql
    assert params[:3] == (7, "TDS_SECTION_NOT_CONFIGURED", 99)
    assert "194J (professional)" in params[3] and "2026-10-01" in params[3]


@pytest.mark.parametrize("sid,eid,section", [(7, None, "194J"), (7, 99, None), (None, 99, "194J")])
def test_flag_needs_society_expense_and_section(sid, eid, section):
    db = _CaptureDB()
    assert tds_compliance.flag_unconfigured_section(db, sid, eid, section) is False
    assert db.calls == []


def test_a_failed_flag_write_never_raises():
    assert tds_compliance.flag_unconfigured_section(_CaptureDB(fail=True), 7, 99, "194J") is False


def test_flag_rule_code_fits_the_column():
    assert len(tds_compliance.RULE_SECTION_NOT_CONFIGURED) <= 40        # compliance_flags.rule_code VARCHAR(40)


def _suggest(db, rates):
    db.tables.setdefault("societies", []).append({"id": 1, "name": "Sunrise", "calc_start_date": "2026-04-01"})
    db.tables.setdefault("accounts", []).append({
        "id": 2312, "society_id": 1, "name": "Acc-2312", "tab_name": "InExp", "drcr_account": "Dr",
        "has_bf": False, "tds_section": "194C", "is_depreciable": False, "depreciation_percent": 0})
    db.tables.setdefault("society_compliance_settings", []).append({"society_id": 1, "tds_no_pan_action": "warn"})
    for r in rates:
        db.tables.setdefault("tds_section_rates", []).append(r)
    return tds_compliance.suggest_expense_tax_fields(db, 1, 2312, None, 40000, expense_date="2026-10-10")


def test_expense_form_warns_when_the_section_has_no_rate(patched_db):
    sug = _suggest(patched_db, rates=[])
    assert sug["tds_basis"] == "section-not-configured" and sug["tds_applies"] is False
    assert "No TDS rate is configured for section 194C" in sug["tds_config_warning"]
    assert "TDS & GST Rates" in sug["tds_config_warning"]


def test_expense_form_has_no_warning_when_the_rate_exists(patched_db):
    sug = _suggest(patched_db, rates=[
        {"id": 1, "society_id": 1, "section": "194C", "rate": 2.0, "rate_no_pan": 4.0,
         "single_bill_threshold": 30000, "annual_aggregate_threshold": 0, "effective_from": "2024-04-01"}])
    assert sug["tds_basis"] != "section-not-configured"
    assert sug["tds_config_warning"] is None
