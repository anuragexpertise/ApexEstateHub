"""
Scenario J — Statutory reserve appropriation at FY close.

The compliance gap this covers: nothing in the product ever moved a share of
net surplus into the Reserve Fund, so the reserve only ever grew by manual
journal entry and a society could pass years of audit with no statutory
appropriation at all. This scenario tests the automatic path:

  * fn_fy_close_preview tells the admin, BEFORE committing to an irreversible
    ledger write, what the appropriation would be and every reason the close
    is blocked.
  * fn_fy_close_reserve_appropriation posts a balanced two-leg journal
    (Dr Income Expenditure A/c, Cr Reserve Fund) for a fixed share of the
    year's net surplus, in ONE journal, then records the closure.
  * The close is idempotent. A double click, or two admins racing, must not
    appropriate the reserve twice — the second call reports already_closed
    having posted nothing.
  * A deficit year is still closeable (recording status 'no_surplus' and
    posting no journal). Gating the close on there being a surplus would leave
    a loss-making year permanently open.
  * The reserve account is resolved the way the SQL resolves it: an unlocked
    RESERVE_FUND-mapped account is preferred over a statutorily-locked Corpus
    Fund, even though both map to the same statutory head.

The seed mirrors the real UP_AOA_2010 ids (3220 Repair & Maintenance Fund
Reserve, 3230 Corpus Fund, 5100 Income Expenditure A/c) so the resolution
ordering is exercised the way it is in production.
"""

import pytest

from app.dash_apps.drilldown import loaders
from app.dash_apps.drilldown.renderers import (
    render_fy_closing_card,
    render_reserve_appropriation_panel,
)


def _seed_surplus_world(patched_db, income=100000.0, expense=40000.0):
    """A society with a full year's books: net surplus = income - expense."""
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": "2026-04-01",
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
        "name": "Master Admin", "linked_id": None,
    })
    patched_db.tables.setdefault("accounts", []).extend([
        # Cr side of the books — the funds the surplus is appropriated into.
        {"id": 2, "society_id": 1, "name": "Capital Account", "tab_name": "CapAc",
         "drcr_account": "Cr", "has_bf": True, "statutory_lock_pct": 0},
        {"id": 3220, "society_id": 1, "name": "Repair & Maintenance Fund Reserve",
         "tab_name": "RepFund", "drcr_account": "Cr", "has_bf": True,
         "statutory_lock_pct": 0},
        {"id": 3230, "society_id": 1, "name": "Corpus Fund (Sinking Fund)",
         "tab_name": "SinkFund", "drcr_account": "Cr", "has_bf": True,
         "statutory_lock_pct": 100.0},
        # The debit leg of the year-end journal.
        {"id": 5100, "society_id": 1, "name": "Income Expenditure A/c",
         "tab_name": "InExp", "drcr_account": None, "has_bf": False,
         "statutory_lock_pct": 0},
        # Income and expense lines that produce the surplus.
        {"id": 2311, "society_id": 1, "name": "Society Maintenance Charge",
         "tab_name": "IncExp", "drcr_account": "Cr", "has_bf": False,
         "statutory_lock_pct": 0},
        {"id": 2312, "society_id": 1, "name": "Repair & Maintenance Expenses",
         "tab_name": "IncExp", "drcr_account": "Dr", "has_bf": False,
         "statutory_lock_pct": 0},
        {"id": 633, "society_id": 1, "name": "Cash-in-hand", "tab_name": "CurAs",
         "drcr_account": "Dr", "has_bf": True, "statutory_lock_pct": 0},
    ])
    # FY 2025-26 activity. Four legs, not two: maintenance income is a Cr
    # posting and repairs are a Dr posting, and each needs its counterpart for
    # the year's Dr and Cr totals to agree. The cash account is on the Dr side
    # of both — Cr when the expense is paid out — which is the ordinary case
    # and the reason the fake checks balance on the postings, not on each
    # account's drcr_account.
    patched_db.tables.setdefault("transactions", []).extend([
        {"id": 1, "society_id": 1, "acc_id": 2311, "amount": income,
         "entry_side": "Cr", "mode": "cash", "status": "paid",
         "trx_date": "2025-06-01", "acc_particulars": "Maintenance collected",
         "created_by": 1},
        {"id": 2, "society_id": 1, "acc_id": 633, "amount": income,
         "entry_side": "Dr", "mode": "cash", "status": "paid",
         "trx_date": "2025-06-01", "acc_particulars": "Cash received",
         "created_by": 1},
        {"id": 3, "society_id": 1, "acc_id": 2312, "amount": expense,
         "entry_side": "Dr", "mode": "cash", "status": "paid",
         "trx_date": "2025-07-01", "acc_particulars": "Repairs paid",
         "created_by": 1},
        {"id": 4, "society_id": 1, "acc_id": 633, "amount": expense,
         "entry_side": "Cr", "mode": "cash", "status": "paid",
         "trx_date": "2025-07-01", "acc_particulars": "Cash paid out",
         "created_by": 1},
    ])


def _seed_deficit_world(patched_db):
    """A society whose expenses exceed income: a loss year, still closeable."""
    _seed_surplus_world(patched_db, income=40000.0, expense=100000.0)


class TestScenarioJ_ClosePreview:
    """The read-only preview the admin sees before committing."""

    def test_preview_reports_surplus_and_proposed_transfer(self, patched_db):
        _seed_surplus_world(patched_db)  # surplus 60000 -> 25% = 15000
        preview, err = loaders.get_fy_close_preview(1, 2025)
        assert err is None
        assert float(preview["surplus"]) == 60000.0
        assert float(preview["proposed_transfer"]) == 15000.0
        assert float(preview["reserve_pct"]) == 25.0

    def test_preview_is_closeable_when_books_balance(self, patched_db):
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert preview["books_balanced"] is True
        assert preview["can_close"] is True
        assert preview["blockers"] is None

    def test_preview_prefers_unlocked_reserve_over_locked_corpus(self, patched_db):
        """Both 3220 and 3230 map to statutory head RESERVE_FUND, and 3230
        has a 100% statutory lock, so the appropriation must resolve to 3220.
        Crediting a law-protected corpus instead would be a compliance bug."""
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert preview["reserve_acc_id"] == 3220
        assert "Repair & Maintenance" in preview["reserve_acc_name"]

    def test_preview_blocks_when_books_are_unbalanced(self, patched_db):
        _seed_surplus_world(patched_db)
        # An unbalanced posting: expense Dr with no matching credit.
        patched_db.tables["transactions"].append({
            "id": 99, "society_id": 1, "acc_id": 2312, "amount": 5000.0,
            "entry_side": "Dr", "mode": "cash", "status": "paid",
            "trx_date": "2025-08-01", "acc_particulars": "Unmatched entry",
            "created_by": 1,
        })
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert preview["books_balanced"] is False
        assert preview["can_close"] is False
        assert "do not balance" in preview["blockers"]

    def test_deficit_year_is_closeable_with_a_note(self, patched_db):
        """A loss year has no surplus to appropriate, but it still has to be
        closeable — otherwise it can never be closed and every later year
        inherits an open predecessor. The reason is a NOTE, not a blocker."""
        _seed_deficit_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert float(preview["surplus"]) < 0
        assert float(preview["proposed_transfer"]) == 0.0
        assert preview["can_close"] is True
        assert preview["blockers"] is None
        assert "no net surplus" in preview["notes"]

    def test_preview_after_close_reports_already_closed(self, patched_db):
        _seed_surplus_world(patched_db)
        loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert preview["already_closed"] is True
        assert preview["closure_status"] == "closed"
        assert preview["can_close"] is False


class TestScenarioJ_ClosePostsReserve:
    """The write path: a balanced journal and a recorded closure."""

    def test_close_transfers_a_quarter_of_surplus_to_the_reserve(self, patched_db):
        _seed_surplus_world(patched_db)
        result, err = loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        assert err is None
        assert result["status"] == "closed"
        assert float(result["surplus"]) == 60000.0
        assert float(result["reserve_transferred"]) == 15000.0
        assert result["reserve_acc_id"] == 3220

    def test_close_posts_exactly_two_legs_in_one_journal(self, patched_db):
        _seed_surplus_world(patched_db)
        result, _ = loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        legs = [t for t in patched_db.tables["transactions"]
                if t.get("journal_id") == result["journal_id"]]
        assert len(legs) == 2
        debit = next(t for t in legs if t["entry_side"] == "Dr")
        credit = next(t for t in legs if t["entry_side"] == "Cr")
        assert debit["acc_id"] == 5100, "debit the P&L accumulator"
        assert credit["acc_id"] == 3220, "credit the reserve fund"
        # Double entry: the two legs must be equal and opposite.
        assert float(debit["amount"]) == float(credit["amount"]) == 15000.0

    def test_close_never_credits_a_statutorily_locked_corpus(self, patched_db):
        _seed_surplus_world(patched_db)
        loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        locked = [t for t in patched_db.tables["transactions"]
                  if t.get("acc_id") == 3230 and t.get("source_table") == "fy_close"]
        assert locked == [], "the 100%-locked Corpus Fund must never be debited/credited here"

    def test_close_is_idempotent(self, patched_db):
        _seed_surplus_world(patched_db)
        first, _ = loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        second, err = loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        assert err is None
        assert first["status"] == "closed"
        assert second["status"] == "already_closed"
        # The second call must report the ORIGINAL journal, not create a new one.
        assert second["journal_id"] == first["journal_id"]
        appropriation_legs = [t for t in patched_db.tables["transactions"]
                              if t.get("source_table") == "fy_close"]
        assert len(appropriation_legs) == 2, "a double click must not double-appropriate"

    def test_close_records_the_closure_with_the_actor(self, patched_db):
        _seed_surplus_world(patched_db)
        loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        history = loaders.get_fy_closure_history(1)
        assert len(history) == 1
        row = history[0]
        assert row["financial_year"] == 2025
        assert row["status"] == "closed"
        assert float(row["reserve_transferred"]) == 15000.0
        assert row["closed_by_username"] == "Master Admin"

    def test_deficit_year_closes_without_posting_a_journal(self, patched_db):
        _seed_deficit_world(patched_db)
        result, err = loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        assert err is None
        assert result["status"] == "no_surplus"
        assert float(result["reserve_transferred"]) == 0
        assert result["journal_id"] is None
        assert [t for t in patched_db.tables["transactions"]
                if t.get("source_table") == "fy_close"] == []
        # ...and it is recorded as closed, not left open forever.
        assert loaders.get_fy_closure_history(1)[0]["status"] == "no_surplus"

    def test_closure_history_is_most_recent_first(self, patched_db):
        _seed_surplus_world(patched_db)
        patched_db.tables["fy_closures"].extend([
            {"id": 1, "society_id": 1, "financial_year": 2023, "status": "closed",
             "surplus": 100.0, "reserve_pct": 25.0, "reserve_transferred": 25.0,
             "reserve_acc_id": 3220, "reserve_acc_name": "Repair & Maintenance Fund Reserve",
             "contra_acc_id": 5100, "journal_id": 1, "closed_by": 1, "closed_at": "2024-04-01"},
            {"id": 2, "society_id": 1, "financial_year": 2024, "status": "closed",
             "surplus": 200.0, "reserve_pct": 25.0, "reserve_transferred": 50.0,
             "reserve_acc_id": 3220, "reserve_acc_name": "Repair & Maintenance Fund Reserve",
             "contra_acc_id": 5100, "journal_id": 2, "closed_by": 1, "closed_at": "2025-04-01"},
        ])
        years = [r["financial_year"] for r in loaders.get_fy_closure_history(1, 10)]
        assert years == sorted(years, reverse=True)


class TestScenarioJ_PanelGating:
    """
    The panel is the only writing control on a read-only card, so its gating
    is the security boundary. can_post comes from the server-side session
    (app/security/audit_context.py), never from client state.
    """

    @staticmethod
    def _submit(preview, can_post):
        panel = render_reserve_appropriation_panel(preview, fy=preview["fy"],
                                                   can_post=can_post)
        found = {}

        def walk(node):
            kids = getattr(node, "children", None)
            if isinstance(kids, (list, tuple)):
                for k in kids:
                    walk(k)
            elif kids is not None:
                walk(kids)
            if getattr(node, "id", None) == "fy-close-reserve-submit":
                found["disabled"] = node.disabled
                found["label"] = node.children[1]

        walk(panel)
        return found

    def test_admin_with_a_surplus_can_post(self, patched_db):
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        btn = self._submit(preview, can_post=True)
        assert btn["disabled"] is False
        assert "Transfer to Reserve" in btn["label"]

    def test_non_admin_cannot_post(self, patched_db):
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert self._submit(preview, can_post=False)["disabled"] is True

    def test_button_is_disabled_when_books_do_not_balance(self, patched_db):
        _seed_surplus_world(patched_db)
        patched_db.tables["transactions"].append({
            "id": 99, "society_id": 1, "acc_id": 2312, "amount": 5000.0,
            "entry_side": "Dr", "mode": "cash", "status": "paid",
            "trx_date": "2025-08-01", "acc_particulars": "Unmatched",
            "created_by": 1,
        })
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert self._submit(preview, can_post=True)["disabled"] is True

    def test_button_is_disabled_once_the_year_is_closed(self, patched_db):
        _seed_surplus_world(patched_db)
        loaders.close_fy_with_reserve_appropriation(1, 2025, created_by=1)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        assert self._submit(preview, can_post=True)["disabled"] is True

    def test_deficit_year_button_says_no_appropriation(self, patched_db):
        """The label must not promise a transfer that will not happen."""
        _seed_deficit_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        btn = self._submit(preview, can_post=True)
        assert btn["disabled"] is False
        assert "no appropriation" in btn["label"]
        assert "Transfer to Reserve" not in btn["label"]

    def test_panel_shows_the_amount_and_the_destination(self, patched_db):
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        text = str(render_reserve_appropriation_panel(preview, fy=2025, can_post=True))
        assert "15,000.00" in text
        assert "60,000.00" in text
        assert "Repair & Maintenance Fund Reserve" in text

    def test_panel_explains_a_blocker_rather_than_a_bare_disabled_button(self, patched_db):
        _seed_surplus_world(patched_db)
        patched_db.tables["transactions"].append({
            "id": 99, "society_id": 1, "acc_id": 2312, "amount": 5000.0,
            "entry_side": "Dr", "mode": "cash", "status": "paid",
            "trx_date": "2025-08-01", "acc_particulars": "Unmatched",
            "created_by": 1,
        })
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        text = str(render_reserve_appropriation_panel(preview, fy=2025, can_post=True))
        assert "out of balance" in text

    def test_card_omits_the_panel_when_no_preview_is_supplied(self, patched_db):
        """The existing read-only callers pass no preview; the card must keep
        working exactly as before rather than rendering an empty shell."""
        _seed_surplus_world(patched_db)
        card = render_fy_closing_card(rows=[], error=None, fy_options=[2025],
                                      selected_fy=2025, society_id=1)
        assert "Statutory Reserve Appropriation" not in str(card)

    def test_card_renders_the_panel_when_a_preview_is_supplied(self, patched_db):
        _seed_surplus_world(patched_db)
        preview, _ = loaders.get_fy_close_preview(1, 2025)
        history = loaders.get_fy_closure_history(1)
        card = render_fy_closing_card(
            rows=[], error=None, fy_options=[2025], selected_fy=2025, society_id=1,
            reserve_preview=preview, reserve_history=history, can_post_reserve=True)
        text = str(card)
        assert "Statutory Reserve Appropriation" in text
        assert "15,000.00" in text
