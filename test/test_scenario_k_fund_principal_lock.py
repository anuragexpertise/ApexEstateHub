"""
Scenario K — Statutory principal protection in Fund Management.

The compliance gap this covers: the Corpus Fund's principal is inviolable
(RERA Sec. 11(4)(g) / UP Model Bye-Laws Ch.VII), and fn_process_fund_utilization
enforces that in the database. But the Fund Management card presented the
GROSS balance under a column headed "Available Balance" and offered every
fund with a positive balance in the draw-down dropdown, so the only place an
admin could learn that the Corpus Fund was not spendable was the error message
after they had already typed the amount and clicked submit.

These tests pin the display half of the same rule:

  * the "available to draw" figure is the headroom after the statutory
    principal, not the gross balance, and agrees exactly with what
    fn_process_fund_utilization will enforce;
  * a fully-locked fund is visible but not selectable, rather than vanishing
    (which would read as the fund having gone missing);
  * a partially-locked fund is still usable for its headroom;
  * the lock is explained in words, so "0.00 available" next to a six-figure
    balance reads as the law rather than as a bug.
"""

import pytest

from app.dash_apps.callbacks.fund_management_callbacks import (
    build_balances_table,
    build_fund_options,
    resolve_fund_type_info,
)


@pytest.fixture
def funds():
    """Three funds covering every lock case the card has to render."""
    return [
        {"acc_id": 3220, "name": "Repair & Maintenance Fund Reserve",
         "balance": 83718.75, "statutory_lock_pct": 0,
         "locked_amount": 0, "available_amount": 83718.75},
        # Fully locked: the RERA corpus principal.
        {"acc_id": 3230, "name": "Corpus Fund", "balance": 500000.0,
         "statutory_lock_pct": 100, "locked_amount": 500000.0,
         "available_amount": 0.0},
        # Partially locked: still usable, but only for the headroom.
        {"acc_id": 3210, "name": "Sinking Fund Reserve", "balance": 120000.0,
         "statutory_lock_pct": 40, "locked_amount": 48000.0,
         "available_amount": 72000.0},
    ]


class TestScenarioK_LockedFundDisplay:
    """What the balances table claims must match what the SQL will allow."""

    def test_table_shows_available_not_gross_as_the_headline(self, funds):
        text = str(build_balances_table(funds))
        # The unlocked fund's full balance is drawable, so it leads with it.
        assert "83,718.75" in text
        # The locked fund leads with its headroom (0.00), and the gross
        # balance is demoted to a secondary line.
        assert "of ₹500,000.00 held" in text

    def test_column_is_no_longer_labelled_available_balance(self, funds):
        text = str(build_balances_table(funds))
        assert "Available to Draw" in text
        assert "Available Balance" not in text

    def test_locked_principal_is_shown_for_each_locked_fund(self, funds):
        text = str(build_balances_table(funds))
        assert "₹500,000.00 protected" in text
        assert "₹48,000.00 protected" in text
        assert "100%" in text and "40%" in text

    def test_unlocked_fund_shows_no_lock(self, funds):
        text = str(build_balances_table(funds))
        row = next(r for r in str(build_balances_table(funds)).split("Tr([")
                   if "Repair & Maintenance" in r)
        assert "—" in row, "an unlocked fund has no statutory principal to show"

    def test_table_explains_the_lock(self, funds):
        """A 0.00 balance under a six-figure holding must not read as a bug."""
        text = str(build_balances_table(funds))
        assert "Statutory principal is protected" in text
        assert "RERA" in text
        # ...including the part an admin would otherwise misread: the interest
        # is still usable, it just is not drawn from the fund.
        assert "Interest Income account" in text

    def test_no_legend_when_nothing_is_locked(self):
        text = str(build_balances_table([
            {"acc_id": 3300, "name": "Gifts Received", "balance": 2500.0,
             "statutory_lock_pct": 0, "locked_amount": 0, "available_amount": 2500.0},
        ]))
        assert "Statutory principal is protected" not in text


class TestScenarioK_FundDropdown:
    """The dropdown is where an admin picks a target, so it must not offer
    a fund whose entire balance is law-protected."""

    def test_fully_locked_fund_is_listed_but_disabled(self, funds):
        options = {o["value"]: o for o in build_fund_options(funds)}
        corpus = options["3230"]
        assert corpus["disabled"] is True
        assert "Corpus Fund" in corpus["label"]
        assert "statutory principal" in corpus["label"]

    def test_fully_locked_fund_is_not_silently_dropped(self, funds):
        """Hiding it would leave an admin thinking the fund had disappeared."""
        options = {o["value"] for o in build_fund_options(funds)}
        assert "3230" in options

    def test_partially_locked_fund_is_selectable_for_its_headroom(self, funds):
        options = {o["value"]: o for o in build_fund_options(funds)}
        sinking = options["3210"]
        assert sinking["disabled"] is False
        # The label must quote the real headroom, not a fixed zero.
        assert "72,000.00" in sinking["label"]

    def test_unlocked_fund_is_selectable_and_shows_full_balance(self, funds):
        options = {o["value"]: o for o in build_fund_options(funds)}
        repair = options["3220"]
        assert repair["disabled"] is False
        assert "83,718.75" in repair["label"]

    def test_zero_balance_fund_is_omitted(self, funds):
        options = {o["value"] for o in build_fund_options(
            funds + [{"acc_id": 3300, "name": "Provisions", "balance": 0.0,
                      "statutory_lock_pct": 0, "locked_amount": 0,
                      "available_amount": 0.0}])}
        assert "3300" not in options

    def test_dropdown_amount_matches_the_table_headroom(self, funds):
        """One rule, two surfaces: the dropdown and the table must agree, or
        the admin reads a different number depending on where they look."""
        table = str(build_balances_table(funds))
        for fb in funds:
            if float(fb["statutory_lock_pct"]) <= 0:
                continue
            option = next(o for o in build_fund_options(funds)
                          if o["value"] == str(fb["acc_id"]))
            headroom = f"{fb['available_amount']:,.2f}"
            assert headroom in option["label"]
            assert headroom in table


class TestScenarioK_LockMatchesEnforcement:
    """
    The card's arithmetic and fn_process_fund_utilization's must be the same
    rule, or the UI will advertise headroom the database then refuses.

    The real function computes:  locked = balance * lock_pct / 100
                                available = balance - locked  (floored at 0)
    loaders.get_fund_balances has the SQL equivalent, so the two agree. The
    card, though, receives available_amount from the loader and must fall back
    to the same formula if an older/stubbed row lacks that key — that
    fallback is the card's own production logic, and is what is tested here.
    """
    @staticmethod
    def _enforced_available(balance, lock_pct):
        locked = round(balance * lock_pct / 100, 2)
        return max(balance - locked, 0)

    @pytest.mark.parametrize("balance,lock_pct", [
        (500000.0, 100), (120000.0, 40), (83718.75, 0),
        (1.0, 100), (999.99, 33),
    ])
    def test_fallback_headroom_equals_enforced_headroom(self, balance, lock_pct):
        # A row as the loader would have produced it if available_amount were
        # ever missing — the card must derive the same number the SQL enforces.
        row = {
            "acc_id": 1, "name": "Corpus Fund", "balance": balance,
            "statutory_lock_pct": lock_pct,
            "locked_amount": round(balance * lock_pct / 100, 2),
        }
        expected = self._enforced_available(balance, lock_pct)
        assert expected == max(balance - row["locked_amount"], 0)

        # The dropdown label is the observable output of that derivation. A
        # locked fund states the headroom as "X drawable"; an unlocked one
        # just quotes the balance, which is the same number.
        label = build_fund_options([row])[0]["label"]
        if lock_pct > 0:
            assert f"{expected:,.2f} drawable" in label
        else:
            assert f"₹{expected:,.2f}" in label

    def test_zero_balance_locked_fund_is_omitted_not_advertised(self):
        """Nothing to draw from, so it is not offered at all — the ₹0.00
        label is reserved for a fund that holds money it may not spend."""
        row = {"acc_id": 1, "name": "Corpus Fund", "balance": 0.0,
               "statutory_lock_pct": 100, "locked_amount": 0.0}
        assert build_fund_options([row]) == []

    def test_loader_supplied_available_amount_wins_over_recomputation(self):
        """When the loader does supply the figure, the card must show exactly
        that figure — the SQL and the Python must not disagree by a rounding
        step and have the card silently paper over it."""
        row = {
            "acc_id": 1, "name": "Corpus Fund", "balance": 500000.0,
            "statutory_lock_pct": 100, "locked_amount": 500000.0,
            "available_amount": 0.0,
        }
        label = build_fund_options([row])[0]["label"]
        assert "₹0.00 drawable" in label

    def test_a_fully_locked_fund_advertises_no_headroom(self):
        row = {"acc_id": 3230, "name": "Corpus Fund", "balance": 500000.0,
               "statutory_lock_pct": 100, "locked_amount": 500000.0}
        assert self._enforced_available(row["balance"],
                                         row["statutory_lock_pct"]) == 0.0
        assert build_fund_options([row])[0]["disabled"] is True


class TestScenarioK_FundTypeMetadata:
    """The lock is only meaningful next to the fund's statutory purpose."""

    def test_corpus_is_labelled_as_interest_only(self):
        info = resolve_fund_type_info("Corpus Fund")
        assert "Corpus Fund" in info["label"]
        assert "interest" in info["purpose"].lower()
        assert "inviolable" in info["purpose"].lower()

    def test_unrecognised_fund_falls_back_to_its_own_name(self):
        info = resolve_fund_type_info("Gifts Received")
        assert info["label"] == "Gifts Received"
