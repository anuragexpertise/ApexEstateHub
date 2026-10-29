"""Task 1.7 service layer: who may act, who may record the CA's confirmation, safe messages. No database needed."""
from datetime import date

import pytest

from app.services import itc_reversal_service as svc


class FakeDB:
    def __init__(self, role="admin", offices=(), error=None, result=None):
        self.role, self.offices, self.error, self.result, self.calls = role, list(offices), error, result, []

    def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        if "FROM users" in sql:
            return {"role": self.role}
        if "FROM committee_offices" in sql:
            return self.offices
        if self.error and ("fn_" in sql or "UPDATE" in sql):
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    import app.security.service_guard as sg
    monkeypatch.setattr(sg, "audit_event", lambda *a, **k: True)


ARGS = dict(kind="period", fy=2026, tax_head="cgst", t=200000, t1=0, t2=50000, t3=10000, t4=50000, e=200000, f=1200000,
            basis="GSTR-2B Apr-2026", period_start=date(2026, 4, 1), period_end=date(2026, 4, 30))


def test_compute_passes_decimals_and_every_argument_to_the_database_function():
    d = FakeDB(result={"id": 5})
    assert svc.compute(1, 9, db=d, **ARGS) == 5
    sql, p = d.calls[-1]
    assert "fn_compute_itc_reversal" in sql and p[0] == 1 and p[1] == "period" and p[5] == "cgst"
    assert str(p[6]) == "200000" and str(p[11]) == "200000" and p[13] == "GSTR-2B Apr-2026" and p[14] == 9


def test_an_ordinary_user_cannot_compute_post_reverse_or_discard():
    d = FakeDB(role="apartment")
    for call in (lambda: svc.compute(1, 9, db=d, **ARGS), lambda: svc.post(1, 9, 3, db=d),
                 lambda: svc.reverse(1, 9, 3, "x", db=d), lambda: svc.discard(1, 9, 3, db=d)):
        with pytest.raises(svc.ItcRefused, match="administrator or a serving office-bearer"):
            call()


def test_a_serving_office_bearer_may_work_out_a_reversal_but_not_record_the_ca_confirmation():
    d = FakeDB(role="staff", offices=[{"id": 1, "office_code": "treasurer"}], result={"id": 2})
    assert svc.compute(1, 9, db=d, **ARGS) == 2
    with pytest.raises(svc.ItcRefused, match="Only the administrator can record"):
        svc.record_ca_confirmation(1, 9, "CA R. Gupta", "REF-1", date.today(), 10, 11, db=d)


@pytest.mark.parametrize("kw, message", [
    (dict(by="  "), "who confirmed"),
    (dict(ref=""), "who confirmed"),
    (dict(debit_acc_id=10, credit_acc_id=10), "two different accounts"),
    (dict(debit_acc_id=None), "two different accounts"),
    (dict(nonbusiness_pct=101), "between 0 and 100"),
    (dict(nonbusiness_pct=-1), "between 0 and 100"),
])
def test_the_ca_confirmation_must_be_complete(kw, message):
    base = dict(by="CA R. Gupta", ref="REF-1", on_date=date(2026, 10, 1), debit_acc_id=10, credit_acc_id=11, nonbusiness_pct=0)
    base.update(kw)
    d = FakeDB()
    with pytest.raises(svc.ItcRefused, match=message):
        svc.record_ca_confirmation(1, 9, db=d, **base)
    assert not any("UPDATE" in c[0] for c in d.calls)


def test_the_admin_records_the_confirmation_with_the_accounts_the_ca_chose():
    d = FakeDB()
    svc.record_ca_confirmation(1, 9, " CA R. Gupta ", " REF-1 ", date(2026, 10, 1), 10, 11, 5, db=d)
    sql, p = d.calls[-1]
    assert "itc_reversal_confirmed_by=%s" in sql and p[0] == "CA R. Gupta" and p[1] == "REF-1" and p[3:5] == (10, 11) and str(p[5]) == "5"


@pytest.mark.parametrize("bad", ["abc", "1,000"])
def test_a_figure_that_is_not_a_number_is_refused_politely(bad):
    with pytest.raises(svc.ItcRefused, match="is not a number"):
        svc.compute(1, 9, db=FakeDB(), **{**ARGS, "t": bad})


def test_unknown_kind_or_tax_head_is_refused_before_the_database():
    d = FakeDB()
    for kw in ({"kind": "weekly"}, {"tax_head": "vat"}):
        with pytest.raises(svc.ItcRefused):
            svc.compute(1, 9, db=d, **{**ARGS, **kw})
    assert not any("fn_compute" in c[0] for c in d.calls)


def test_database_refusals_become_clean_messages():
    d = FakeDB(error=Exception("ERROR:  The CA has not confirmed the ITC reversal formula\nCONTEXT: PL/pgSQL function fn_post_itc_reversal"))
    with pytest.raises(svc.ItcRefused) as e:
        svc.post(1, 9, 3, db=d)
    assert str(e.value).startswith("The CA has not confirmed") and "CONTEXT" not in str(e.value)
    d = FakeDB(error=Exception('duplicate key value violates unique constraint "uq_itc_register_live"'))
    with pytest.raises(svc.ItcRefused, match="Discard the draft or reverse"):
        svc.compute(1, 9, db=d, **ARGS)
    d = FakeDB(error=Exception('new row violates check constraint "ck_itc_period_dates"'))
    with pytest.raises(svc.ItcRefused, match="inside the financial year"):
        svc.compute(1, 9, db=d, **ARGS)


def test_formula_status_is_provisional_until_confirmed_and_postable_only_with_accounts():
    d = FakeDB(result={"by": None, "ref": None, "on_date": None, "debit_acc_id": None, "credit_acc_id": None, "nonbusiness_pct": 0})
    s = svc.formula_status(1, db=d)
    assert s["status"] == "provisional" and not s["confirmed"] and not s["postable"]
    d = FakeDB(result={"by": "CA", "ref": "r", "on_date": date(2026, 10, 1), "debit_acc_id": None, "credit_acc_id": 3, "nonbusiness_pct": 0})
    s = svc.formula_status(1, db=d)
    assert s["status"] == "confirmed" and not s["postable"]
    d = FakeDB(result={"by": "CA", "ref": "r", "on_date": date(2026, 10, 1), "debit_acc_id": 2, "credit_acc_id": 3, "nonbusiness_pct": 0})
    assert svc.formula_status(1, db=d)["postable"]
