"""
Job 6 -- the screen to lock a financial year.

The authorization is policy-engine only (no database). The preview, the service and the panel are exercised against a
REAL Postgres, rolled back.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_fy_lock_screen_live.py
"""
import os
from datetime import date

import pytest

from app.security import authorization as az
from app.security.authorization import Cap, Principal, Assignment, authorize
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

SOC = 1
CAP = Cap.FINANCE_PERIOD_CLOSE


# ---- who may lock: policy engine, no database ------------------------------------------------------------------
def _p(role="admin", *assigned, society=SOC, uid=7):
    return Principal(user_id=uid, society_id=society, base_role=role,
                     assignments=tuple(Assignment(a, society, "active", None, None) for a in assigned))


def test_the_treasurer_can_lock_a_year():
    assert authorize(_p("apartment", "treasurer"), CAP, "fy_lock", target_society_id=SOC).allowed


@pytest.mark.parametrize("roles", [(), ("society_secretary",), ("committee_member",), ("accountant",)])
def test_nobody_else_can_lock_a_year(roles):
    d = authorize(_p("admin", *roles), CAP, "fy_lock", target_society_id=SOC)
    assert not d.allowed


def test_the_society_admin_cannot_lock_a_year():
    assert not authorize(_p("admin"), CAP, "fy_lock", target_society_id=SOC).allowed


def test_a_treasurer_cannot_lock_another_societys_year():
    assert not authorize(_p("apartment", "treasurer"), CAP, "fy_lock", target_society_id=2).allowed


def test_the_capability_is_only_valid_for_the_fy_lock_resource():
    assert not authorize(_p("apartment", "treasurer"), CAP, "journal_entry", target_society_id=SOC).allowed


def test_no_role_holds_both_preparing_and_locking():
    for role, caps in az.capability_matrix().items():
        assert not ({Cap.FINANCE_POST, CAP} <= set(caps)), role


def test_the_lock_callback_is_declared_with_the_capability():
    import inspect
    src = inspect.getsource(__import__("app.dash_apps.callbacks.drilldown_callbacks", fromlist=["x"]))
    i = src.index("def lock_financial_year")
    head = src[src.rindex("@app.callback", 0, i):i]
    assert "@require_session" in head and "FINANCE_PERIOD_CLOSE" in head and "@require_action(" in head


# ---- panel rendering -------------------------------------------------------------------------------------------
def _ids(component, found=None):
    found = found if found is not None else set()
    cid = getattr(component, "id", None)
    if cid:
        found.add(cid if isinstance(cid, str) else repr(cid))     # pattern-matching ids are dicts
    kids = getattr(component, "children", None)
    for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
        if k is not None and not isinstance(k, (str, int, float)):
            _ids(k, found)
    return found


def _state(**over):
    pv = {"financial_year": 2024, "ends_on": date(2025, 3, 31), "year_ended": True, "year_closed": True,
          "already_locked": False, "locked_through": None, "earlier_unlocked_years": 0, "unbalanced_journals": 0,
          "chain_problems": 0, "pending_documents": 0, "can_lock": True, "blockers": None}
    pv.update(over)
    return {"preview": pv, "locks": [], "this_lock": None, "anchor": None}


def test_panel_offers_the_form_only_to_a_role_that_can_lock():
    from app.dash_apps.drilldown import renderers
    live = renderers.render_fy_lock_panel(_state(), 2024, can_lock=True)
    assert {"fy-lock-submit", "fy-lock-reason", "fy-lock-understood", "fy-lock-resolution"} <= _ids(live)
    assert live.children is not None
    def disabled(panel, cid):
        def walk(c):
            if getattr(c, "id", None) == cid:
                return c
            kids = getattr(c, "children", None)
            for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
                if k is not None and not isinstance(k, (str, int, float)):
                    r = walk(k)
                    if r is not None:
                        return r
        return walk(panel).disabled
    assert disabled(live, "fy-lock-submit") is False
    assert disabled(renderers.render_fy_lock_panel(_state(), 2024, can_lock=False), "fy-lock-submit") is True
    blocked = renderers.render_fy_lock_panel(_state(can_lock=False, year_closed=False,
                                                    blockers="close the year first"), 2024, can_lock=True)
    assert disabled(blocked, "fy-lock-submit") is True


def test_panel_for_a_locked_year_shows_it_locked_with_no_form():
    from app.dash_apps.drilldown import renderers
    st = _state(already_locked=True, can_lock=False, locked_through=2024)
    st["this_lock"] = {"locked_at": date(2026, 4, 2), "locked_by_name": "Treasurer", "notes": "Audit signed off",
                       "anchor_id": 1}
    st["anchor"] = {"society_id": 1, "ledger_seq": 40, "head_hash": "ab" * 32, "row_count": 40,
                    "anchored_at": date(2026, 4, 2), "signature": "cd" * 32}
    panel = renderers.render_fy_lock_panel(st, 2024, can_lock=True)
    assert "fy-lock-submit" not in _ids(panel)
    text = repr(panel)
    assert "is locked" in text and "Audit signed off" in text and ("ab" * 32) in text


def test_closing_card_still_renders_without_a_lock_state():
    from app.dash_apps.drilldown import renderers
    card = renderers.render_fy_closing_card(rows=[], error=None, fy_options=[2024], selected_fy=2024)
    assert "fy-lock-submit" not in _ids(card)
    card = renderers.render_fy_closing_card(rows=[], error=None, fy_options=[2024], selected_fy=2024,
                                            lock_state=_state(), can_lock=True)
    assert "fy-lock-submit" in _ids(card)


# ---- the preview and the service, against a real database -------------------------------------------------------
live = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)
psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture()
def conn():
    if not live_db_enabled():
        pytest.skip(LIVE_DB_REASON)
    c = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_fy_lock_preview') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with the FY lock preview is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


class Shim:
    def __init__(self, cur):
        self.cur = cur

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.cur.execute(sql, params)
        if fetch_one or fetch_all:
            cols = [d[0] for d in self.cur.description]
            out = [dict(zip(cols, r)) for r in self.cur.fetchall()]
            return (out[0] if out else None) if fetch_one else out


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


PAST_FY = date.today().year - 3          # long over, whatever today's date


def close_year(cur, fy):
    cur.execute("""INSERT INTO fy_closures (society_id, financial_year, surplus, reserve_pct, reserve_transferred, status)
                   VALUES (%s,%s,0,0,0,'no_surplus') ON CONFLICT DO NOTHING""", (SOC, fy))


def key(monkeypatch):
    # Anchors are signed with society 1's SIGNING_LEDGER key, wrapped under the seed's SECRET_VAULT_KEY.
    import os
    from app.services import secret_vault
    if not os.getenv(secret_vault.ENV_NAME):
        import pytest
        pytest.skip("SECRET_VAULT_KEY must be the key the database was seeded with")


def make_entry(cur, fy):
    sdr = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE 'Sundry Debtors' LIMIT 1", (SOC,))
    inc = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND tab_name='SocM' ORDER BY id LIMIT 1", (SOC,))
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id)
                   VALUES (%s,'Dr',%s,%s,10,'journal','paid',%s),(%s,'Cr',%s,%s,10,'journal','paid',%s)""",
                (SOC, date(fy, 6, 1), sdr, j, SOC, date(fy, 6, 1), inc, j))


def test_preview_blocks_a_year_that_has_not_ended(cur):
    fy = date.today().year + 1
    cur.execute("SELECT can_lock, blockers FROM fn_fy_lock_preview(%s,%s)", (SOC, fy))
    can, why = cur.fetchone()
    assert not can and "has not ended" in why


def test_preview_blocks_an_unclosed_year_and_clears_once_closed(cur):
    cur.execute("SELECT can_lock, blockers FROM fn_fy_lock_preview(%s,%s)", (SOC, PAST_FY))
    can, why = cur.fetchone()
    assert not can and "close the year first" in why
    close_year(cur, PAST_FY)
    cur.execute("SELECT can_lock, blockers FROM fn_fy_lock_preview(%s,%s)", (SOC, PAST_FY))
    assert cur.fetchone() == (True, None)


def test_preview_counts_pending_documents_as_a_warning_not_a_blocker(cur):
    close_year(cur, PAST_FY)
    inc = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND tab_name='SocM' ORDER BY id LIMIT 1", (SOC,))
    apt = one(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))
    cur.execute("""INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role, mode, receipt_date, status)
                   VALUES (%s,%s,'old',100,%s,'apartment','upi',%s,'pending')""", (SOC, inc, apt, date(PAST_FY, 7, 1)))
    cur.execute("SELECT can_lock, pending_documents FROM fn_fy_lock_preview(%s,%s)", (SOC, PAST_FY))
    assert cur.fetchone() == (True, 1)


def test_the_service_locks_anchors_and_records_the_anchor_against_the_lock(cur, monkeypatch):
    from app.services import fy_lock_service as svc
    key(monkeypatch)
    close_year(cur, PAST_FY)
    make_entry(cur, PAST_FY)
    db = Shim(cur)
    uid = one(cur, "SELECT id FROM users WHERE society_id=%s LIMIT 1", (SOC,))
    ok, msg, det = svc.lock_fy(SOC, PAST_FY, uid, "Audit signed off by the CA", True, None, db)
    assert ok, msg
    assert "cannot be undone" in msg and det["anchor"] and det["lock_id"]
    st = svc.get_lock_state(SOC, PAST_FY, db)
    assert st["this_lock"]["anchor_id"] == det["anchor"]["anchor_id"] and st["anchor"]["signature"]
    assert st["preview"]["already_locked"] is True and st["preview"]["can_lock"] is False
    # and it really is locked
    cur.execute("SELECT fn_check_fy_lock(%s,%s)", (SOC, date(PAST_FY, 6, 1)))
    assert "locked" in cur.fetchone()[0]


def test_the_service_refuses_without_a_reason_or_acknowledgement(cur, monkeypatch):
    from app.services import fy_lock_service as svc
    key(monkeypatch)
    close_year(cur, PAST_FY)
    db = Shim(cur)
    assert not svc.lock_fy(SOC, PAST_FY, None, "short", True, None, db)[0]
    ok, msg, _ = svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", False, None, db)
    assert not ok and "never be reopened" in msg
    assert one(cur, "SELECT count(*) FROM fy_locks WHERE society_id=%s AND locked_through=%s", (SOC, PAST_FY)) == 0


def test_the_service_refuses_an_unclosed_year_and_a_second_lock(cur, monkeypatch):
    from app.services import fy_lock_service as svc
    key(monkeypatch)
    db = Shim(cur)
    ok, msg, _ = svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", True, None, db)
    assert not ok and "close the year first" in msg
    close_year(cur, PAST_FY)
    make_entry(cur, PAST_FY)
    assert svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", True, None, db)[0]
    ok, msg, _ = svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", True, None, db)
    assert not ok and "already locked" in msg


def test_a_broken_chain_blocks_the_lock_and_the_ledger_is_not_anchored(cur, monkeypatch):
    from app.services import fy_lock_service as svc
    key(monkeypatch)
    close_year(cur, PAST_FY)
    make_entry(cur, PAST_FY)
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=%s AND ledger_seq = 1", (SOC,))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    ok, msg, _ = svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", True, None, Shim(cur))
    assert not ok and "hash chain" in msg
    assert one(cur, "SELECT count(*) FROM ledger_chain_anchors WHERE society_id=%s AND method='fy_lock'", (SOC,)) == 0


def test_the_database_itself_refuses_to_lock_on_a_broken_chain(cur):
    close_year(cur, PAST_FY)
    make_entry(cur, PAST_FY)
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=%s AND ledger_seq = 1", (SOC,))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute("SELECT fn_lock_fy(%s,%s,NULL,NULL,'x')", (SOC, PAST_FY))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    assert "hash chain" in str(e.value)


def test_a_passed_resolution_can_be_cited_and_an_unpassed_one_cannot(cur, monkeypatch):
    from app.services import fy_lock_service as svc
    key(monkeypatch)
    close_year(cur, PAST_FY)
    make_entry(cur, PAST_FY)
    ok, msg, _ = svc.lock_fy(SOC, PAST_FY, None, "A perfectly good reason", True, 987654, Shim(cur))
    assert not ok and "not a passed resolution" in msg


def test_the_lock_callback_is_classified_in_the_authorization_manifest():
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    m = json.loads((root / "docs" / "authz_manifest.json").read_text(encoding="utf-8"))
    entry = m["endpoints"]["callback:drilldown_callbacks.py::lock_financial_year"]
    assert entry == {"classification": "action", "actions": [Cap.FINANCE_PERIOD_CLOSE]}
