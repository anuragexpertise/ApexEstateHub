"""Task 1.7 screen: who sees it, what it offers, how it is wired, what the CSV holds. No database needed."""
import csv
import io
from datetime import date

import pytest

from app.dash_apps.callbacks import itc_callbacks as ic


def _ids(node, out=None):
    out = [] if out is None else out
    cid = getattr(node, "id", None)
    if cid is not None:
        out.append(cid)
    kids = getattr(node, "children", None)
    for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
        if hasattr(k, "children") or hasattr(k, "id"):
            _ids(k, out)
    return out


def _text(node) -> str:
    return str(node)


PROVISIONAL = {"by": None, "ref": None, "on_date": None, "debit_acc_id": None, "credit_acc_id": None, "nonbusiness_pct": 0,
               "confirmed": False, "postable": False, "status": "provisional"}
CONFIRMED = {**PROVISIONAL, "by": "CA R. Gupta", "ref": "CA/ITC/1", "on_date": date(2026, 10, 1), "debit_acc_id": 2, "credit_acc_id": 3,
             "confirmed": True, "postable": True, "status": "confirmed"}


def _row(i, status, kind="period", **kw):
    base = dict(id=i, financial_year=2026, tax_head="cgst", kind=kind, period_start=date(2026, 4, 1) if kind == "period" else None,
                period_end=date(2026, 4, 30) if kind == "period" else None, c2=90000, d1=15000, d2=0, reversal=15000,
                already_reversed=0, net_amount=15000, status=status, basis="GSTR-2B Apr-2026")
    return {**base, **kw}


@pytest.fixture()
def stub(monkeypatch):
    monkeypatch.setattr(ic, "get_current_user_id", lambda: 9)
    monkeypatch.setattr(ic.itc, "may_act", lambda sid, uid, db=None: True)
    monkeypatch.setattr(ic.itc, "is_admin", lambda sid, uid, db=None: True)
    monkeypatch.setattr(ic.itc, "formula_status", lambda sid, db=None: PROVISIONAL)
    monkeypatch.setattr(ic.itc, "accounts", lambda sid, db=None: [{"id": 2, "name": "ITC Reversed"}, {"id": 3, "name": "ITC Ledger"}])
    monkeypatch.setattr(ic.itc, "register", lambda sid, fy=None, db=None: [_row(1, "draft"), _row(2, "posted"), _row(3, "reversed")])
    return monkeypatch


def test_nothing_is_drawn_for_someone_who_may_not_act(stub):
    stub.setattr(ic.itc, "may_act", lambda sid, uid, db=None: False)
    assert ic.itc_section(1) is None
    assert ic.itc_section(None) is None


def test_the_banner_says_provisional_until_the_ca_confirms(stub):
    t = _text(ic.itc_section(1))
    assert "PROVISIONAL" in t and "nothing can be posted" in t
    stub.setattr(ic.itc, "formula_status", lambda sid, db=None: CONFIRMED)
    t = _text(ic.itc_section(1))
    assert "PROVISIONAL" not in t and "CA R. Gupta" in t and "CA/ITC/1" in t


def test_a_confirmed_formula_without_accounts_still_warns(stub):
    stub.setattr(ic.itc, "formula_status", lambda sid, db=None: {**CONFIRMED, "postable": False, "debit_acc_id": None})
    assert "journal accounts are not chosen" in _text(ic.itc_section(1))


def test_only_the_administrator_sees_the_ca_confirmation_form(stub):
    assert {"itc-ca-by", "itc-ca-ref", "itc-ca-save", "itc-ca-dr", "itc-ca-cr"} <= {i for i in _ids(ic.itc_section(1)) if isinstance(i, str)}
    stub.setattr(ic.itc, "is_admin", lambda sid, uid, db=None: False)
    ids = {i for i in _ids(ic.itc_section(1)) if isinstance(i, str)}
    assert "itc-ca-save" not in ids and "itc-compute" in ids                 # an office-bearer can still work out drafts


def test_the_compute_form_has_every_figure_of_the_formula(stub):
    ids = {i for i in _ids(ic.itc_section(1)) if isinstance(i, str)}
    assert {"itc-kind", "itc-fy", "itc-pstart", "itc-pend", "itc-head", "itc-t", "itc-t1", "itc-t2", "itc-t3", "itc-t4", "itc-e", "itc-f",
            "itc-basis", "itc-compute", "itc-csv-btn"} <= ids


def test_each_row_offers_only_what_its_status_allows(stub):
    typed = [i for i in _ids(ic.itc_section(1)) if isinstance(i, dict)]
    by = lambda ty: {i["id"] for i in typed if i["type"] == ty}
    assert by("itc-post") == {1} and by("itc-discard") == {1}                # a draft: post or discard
    assert by("itc-reverse") == {2} and by("itc-reason") == {2}              # a posted row: reverse, with a reason
    assert all(i["id"] != 3 for i in typed)                                  # a reversed row: nothing


def test_the_register_shows_the_steps_and_the_basis(stub):
    t = _text(ic.itc_section(1))
    assert "15,000.00" in t and "90,000.00" in t and "GSTR-2B Apr-2026" in t and "CGST" in t and "2026-04-01" in t


def test_the_annual_row_shows_what_the_months_already_reversed(stub):
    stub.setattr(ic.itc, "register", lambda sid, fy=None, db=None: [_row(5, "draft", kind="annual", already_reversed=20000, reversal=80000, net_amount=60000)])
    t = _text(ic.itc_section(1))
    assert "Annual" in t and "20,000.00" in t and "60,000.00" in t


def test_the_financial_year_starts_in_april():
    assert ic.current_fy(date(2026, 3, 31)) == 2025 and ic.current_fy(date(2026, 4, 1)) == 2026 and ic.current_fy(date(2026, 12, 31)) == 2026


class _App:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(fn):
            self.fns[fn.__name__] = fn
            return fn
        return deco


def test_every_callback_registers_and_is_session_guarded():
    app = _App()
    ic.register_itc_callbacks(app)
    assert set(app.fns) == {"_confirm", "_compute", "_post", "_discard", "_reverse", "_csv"}
    assert all(hasattr(fn, "__wrapped__") for fn in app.fns.values()), "every callback must carry @require_session"


def test_the_section_is_mounted_on_the_tax_rates_tab():
    import inspect
    from app.dash_apps.pages import tax_rates_page
    assert "itc_section" in inspect.getsource(tax_rates_page)


def test_csv_holds_every_step_basis_and_status(monkeypatch):
    from app.services import itc_reversal_service as svc
    row = {**_row(1, "posted"), "financial_year": 2026, "t_total": 200000, "t1_non_business": 0, "t2_exempt_only": 50000, "t3_blocked": 10000,
           "t4_taxable_only": 50000, "e_exempt_value": 200000, "f_total_turnover": 1200000, "nonbusiness_pct": 0, "c1": 140000,
           "formula_status": "confirmed", "journal_id": 77, "reversal_journal_id": None, "basis": "GSTR-2B, \"turnover\" worksheet"}
    monkeypatch.setattr(svc, "register", lambda sid, fy=None, db=None: [row])
    rows = list(csv.reader(io.StringIO(svc.export_csv(1))))
    head, line = rows[0], dict(zip(rows[0], rows[1]))
    assert head[:3] == ["id", "financial_year", "tax_head"] and "basis" in head and len(rows) == 2
    assert line["c1"] == "140000" and line["c2"] == "90000" and line["d1"] == "15000" and line["status"] == "posted"
    assert line["journal_id"] == "77" and line["reversal_journal_id"] == "" and line["basis"] == 'GSTR-2B, "turnover" worksheet'


def test_service_helpers_for_the_screen():
    from app.services import itc_reversal_service as svc

    class DB:
        def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
            if "FROM users" in sql:
                return {"role": "admin"}
            if "FROM accounts" in sql:
                return [{"id": 1, "name": "A"}]
            return []
    assert svc.is_admin(1, 9, db=DB()) is True and svc.is_admin(1, None, db=DB()) is False
    assert svc.accounts(1, db=DB()) == [{"id": 1, "name": "A"}]
    assert svc.may_act(1, 9, db=DB()) is True and svc.may_act(None, 9, db=DB()) is False
