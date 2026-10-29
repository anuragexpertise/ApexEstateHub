# `float(` audit (Plan v4, C.9)

Searched 29 Oct 2026: `grep -rn "float(" app database --include=*.py`, 135 lines before this change. Rule: **no `float(` where a rupee amount is
added, compared, stored or used to match a stored amount.** Rupee amounts use `database/money.py` (`D`, `money` to the paisa, `rupee` for TDS).

## Converted to Decimal (money paths)

| Where | What was a float | Now |
|---|---|---|
| `fund_management_callbacks.py` | withdrawal and appropriation amount; fund balance, locked amount, drawable headroom (`fund_drawable_amount`), the lock computation; option labels | `money` / `D`; lock rounded half-up to the paisa as `fn_process_fund_utilization` does |
| `drillin_callbacks.py` | amount `<= 0` check | `D` |
| `bulk_enroll_callbacks.py` | salary per shift, asset purchase value read from a spreadsheet | `money` (Decimal) |
| `drilldown_callbacks.py` | salary per shift saved from the security form | `money` |
| `bank_reconcile_callbacks.py` | amount used to match stored receipts/expenses (`amount = %s`); debit, credit, balance of every uploaded statement line | `D` / `money` |
| `setup_wizard_callbacks.py`, `setup_wizard.py` | brought-forward balances; "amount > 0" checks | `money` (sent as text in the JSON), `D` |
| `database/seed.py` | the advance overpayment amount | `money` |
| `renderers.py` | Income and Expenditure totals and surplus; the TDS amount and net amount on the printed expense | `Decimal` sums; TDS is the stored amount, else `rupee()` |

## Kept, by reason

* **Percentages and rates, not rupees:** majority and quorum percentages, vote weights, statutory lock percentage, reserve percentage, GST and TDS
  rates (`governance_callbacks.py`, `adviser_*`, `master_rules_*`, `tax_rate_service.py`, `regime_rules_admin.py`, `statutory_rules.py`,
  `up_aoa_actions.py` weight, `setup_wizard*` rate fields, `tax_rates_page.py`, `poll_callbacks.py` weights). A rule parameter is parsed from its
  shortest text form and held in `NUMERIC` by the database; none is added to money.
* **Display only, at the edge:** `f"{float(v):,.2f}"` and similar formatting in `renderers.py` (49 lines before, mostly formatting, running
  balance cells, chart and ticket price display), `card_catalogue_callbacks.py`, `committee_page.py`, `gst_accounts_page.py`,
  `up_compliance_card.py`, `up_compliance_callbacks.py`, `fund_management_callbacks.py` labels, `seed.py` progress messages. The value is
  already rounded in the database; the float exists only to be printed.
* **JSON and file edges that need a number:** the Excel export (`up_aoa_actions.py` 640), the reconcile `dcc.Store` amount (`bank_reconcile_callbacks.py`
  753), the ticket-price store on the event card. Nothing is added or compared after the conversion.
* **Not money:** map coordinates (`qr_callbacks.py`), hours (`job_runner.py`), sort keys (`drilldown_callbacks.py` 2952).

If a new `float(` is added near an amount, convert it or add it to this list with its reason.
