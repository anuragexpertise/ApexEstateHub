# EstateHub: Streamlining Brought Forward (Society onboarding)

Plan for **NVIDIA Nemotron 3.5 Super VL** to write the code. Paste this whole file as the first message.
Baseline: repo `anuragexpertise/ApexEstateHub`, commit **`fe5715e`** ("onboarding correction plan", 2026-11-20). Line numbers below are for that commit; re-grep if they have drifted. Revision 2 (2026-11-21): adds section 4A, the standard-practice corrections to the chart of accounts in `seed.py` (Provisions, Gifts Received, Gifts Given, Investments).

---

## 0. Role and hard rules

You modify **EstateHub** (Python, Dash + Flask, JWT auth, PostgreSQL on **Aiven**, hosted on **Render.com**). The code is **alpha**. **No backward compatibility is required.**

- Delete replaced code, callbacks, templates and tests. No shims, aliases, feature flags or "legacy" branches.
- Never invent a function, column, route, component id or import. If you have not seen it in the repo this session, grep for it and read it first.
- Smallest change per requirement. Do not refactor unrelated code. **Edit `ACCOUNTS` and `UP_AOA_ACCOUNT_MAPPINGS` in `database/seed.py` only as written in section 4A (slice S0A), and nothing else in that file.**
- Never print secrets. Money is `Decimal` (use `ob.money` / `database.money`), never `float`.
- Large files: **never read a whole file**. `setup_wizard.py` is 2,497 lines, `onboarding_service.py` 3,213, `onboarding_wizard_callbacks.py` 1,093. Use `Read` with `offset`/`limit` or `grep -n`, and read only the ranges named in each slice.
- You cannot push. Leave changes in the working tree.

## 1. Working protocol (every slice)

1. **Locate**: grep the ids/functions named in the slice; list files and line ranges you will touch.
2. **Read** those ranges. Quote the exact lines you will replace.
3. **Plan** in 3 to 6 bullets (changes, ids affected, what is deleted).
4. **Edit** this slice only.
5. **Verify**, all must pass before the next slice:
   - `python -m py_compile <changed files>`
   - `ruff check <changed files>` (or `python -m pyflakes`)
   - `python -c "import app.dash_apps.pages.setup_wizard, app.dash_apps.callbacks.onboarding_wizard_callbacks"` (run `pip install -r requirements.txt` first if `psycopg2` is missing)
   - `pytest -q` on the slice's tests (section 8) **and** `test/test_wizard_audit_fixes.py` (it fails on duplicate Dash component ids).
6. **Report**: `Slice X: files changed / deleted / commands run / real output / open questions`. Stop if anything failed.

Never claim a test passed unless you ran it and saw the output.

## 2. Stack rules that prevent the usual errors

- **dcc.Upload** `contents` is `"data:<mime>;base64,<payload>"`. Use the existing `_decode(contents)` (onboarding_wizard_callbacks.py:86) which returns bytes or None. Hash the bytes, never the string.
- **openpyxl**: build with `Workbook()`, save to `io.BytesIO`, return `buf.getvalue()`; send with `dcc.send_bytes`. Read with `load_workbook(io.BytesIO(raw), data_only=True)`. Sheet titles max 31 chars, none of `[]:*?/\`.
- **Dash pattern ids**: component ids are dicts, e.g. `{"type": "sw-bf-amt", "acc_id": 1110}`. With `ALL`/`MATCH` outputs, map values to ids through `ctx.inputs_list` / `ctx.outputs_list`, **never by position**.
- Every new `Output` on `f"{P}-body"` or `f"{P}-marker"` needs `allow_duplicate=True` and `prevent_initial_call=True` (copy `sw_bf_file`, line 347).
- Every callback that writes: decorate with `@require_session`, call `_session()`, require `role == "admin"`, refuse when `ob.annexes_sealed(sid)`. Copy the pattern of `sw_bf_file` (line 357).
- Parameterised SQL only (`%s`). Multi-step DB writes in one transaction.
- Component ids must be unique across all wizard steps (`test_no_duplicate_component_ids_across_steps`).

## 3. Facts about the current code (verified at fe5715e)

**Seed tuple** `ACCOUNTS` rows are `(id, name, tab, display_name, parent_id, drcr, has_bf, depr_pct, mutuality, tds_section)`. Index **1 is the real name, index 3 is the display heading** (id 1410 is name "Loans to Owners", display "Loans & Advances Given"). The wizard renders `acc[3]`; `paired_intake.eligible_accounts()` uses `acc[1]`. **Decision: use the display name `acc[3]` everywhere in this feature.** `database.seed` imports `psycopg2`; to read `ACCOUNTS` in a test, import it normally (psycopg2 is in requirements).

**Accounts with `has_bf=True`** (id, tab, display name, side, seed parent):

| id | tab | display name | side | seed parent |
|---|---|---|---|---|
| 1110 | ImAs | Immovable Assets | Dr | 1100 Fixed Assets |
| 1120 | Fur | Furniture | Dr | 1100 |
| 1130 | Inst | Instruments & Tools | Dr | 1100 |
| 1140 | Mch | Machinery | Dr | 1100 |
| 1150 | Car | Car | Dr | 1100 |
| 1160 | Comp | Computers | Dr | 1100 |
| 1200 | Inv | Investments | Dr | **1000 Assets** |
| 1311 | SBI | SBI A/c - Society | Dr | 1310 Bank Accounts |
| 1312 | ICICI | ICICI A/c - Society | Dr | 1310 |
| 1320 | Dp | Deposits (Assets) | Dr | 1300 Current Assets |
| 1330 | CiH | Cash-in-hand | Dr | 1300 |
| 1400 | LAG | Loans & Advances Given | Dr | 1000 |
| 1410 | LnOwn | Loans & Advances Given (name "Loans to Owners") | Dr | 1400 |
| 1510 | SDrDig | Sundry Debtors (Digital) | Dr | 1500 Sundry Debtors |
| 1520 | SDrCash | Sundry Debtors (Cash) | Dr | 1500 |
| 2110 | LAT | Loans And Advances Taken | Cr | 2100 Non-Current Liabilities |
| 2240 | SCr | Sundry Creditors | Cr | 2200 Current Liabilities |
| 3100 | CapAc | Capital Account | Cr | 3000 Equity |
| 3210 | SinkFund | Sinking Fund Reserve | Cr | 3200 Reserves & Funds |
| 3220 | RepFund | Repair Fund Reserve | Cr | 3200 |
| 3230 | CorpusFund | Corpus Fund | Cr | 3200 |
| 3270 | MajRepFund | Major Repair Fund | Cr | 3200 |
| 3280 | DepFund | Depreciation Fund | Cr | 3200 |
| 3240 | Gifts | Gifts Received | Cr | **3000** |
| 3250 | Prov | Provisions | Cr | **3000** |
| 3260 | GiftGiven | Gifts Given | **Dr** | **3000** |

Parents 1000/1100/1300/1310/1500/2100/2200/3000/3200 have `has_bf=False`. 1170 Generator has `has_bf=False` and stays out.

**The table above is the state at fe5715e. Slice S0A (section 4A) changes four rows:** 1200 is renamed Non-Current Investments; 3240 moves under 3200 and becomes the Earmarked Gifts Fund; 3250 Provisions moves under 2200 Current Liabilities; 3260 Gifts Given is removed from the chart as a balance-sheet account and re-created as expense account 51200 with `has_bf=False`. After S0A there are **25** `has_bf=True` accounts (the 26 above minus 3260), and no `has_bf=True` account lies under the Income (4000) or Expense (5000) roots.

**Where things are now** (all in the Brought Forward step):
- `app/dash_apps/pages/setup_wizard.py` line 1989 `elif category == "Brought Forward":` to line 2294. Inside it: dead helpers `_render_node` (2060) and `_side` (2094) are never called; the live renderer is `_bf_account_rows(root_id)` (2124) called as `_bf_account_rows(1000)` for the left column and `_bf_account_rows(2000)` + `_bf_account_rows(3000)` for the right. Today **Assets is left, Liabilities right** (2277 to 2291). The "Funds selected for this society" card is built at 2106 to 2122 and rendered at 2264, **after** the arrears block.
- `BF_LEDGER_MANDATORY_ACCOUNTS` at `setup_wizard.py:18`.
- Statement intake: ids `sw-bf-tpl`, `sw-bf-xlsx`, `sw-bf-pdf`, `sw-bf-file`, `sw-bf-status`, `sw-bf-files`, `sw-bf-tpl-dl`. Arrears intake: `sw-bf-pr-tpl`, `sw-bf-pr-xlsx`, `sw-bf-pr-pdf`, `sw-bf-pr-file`, `sw-bf-pr-status`, `sw-bf-pr-files`, `sw-bf-pr-tpl-dl`. Callbacks `sw_bf_template` (333), `sw_bf_file` (358), `sw_bf_pr_tpl` (382), `sw_bf_pr_file` (402) in `onboarding_wizard_callbacks.py`.
- Grid inputs: `{"type":"sw-bf-amt","acc_id":N}`, `{"type":"sw-bf-remarks","acc_id":N}`, ledger modal `sw-bf-ledger-*`, `sw-bf-attach`. Row collection: `_bf_rows(form)` (callbacks:165) and `_raw_step_values` branch `brought_forward` (callbacks:262). `wizard_nav` State list at callbacks:438 to 460. `_gather` (callbacks:103) turns an ALL-pattern State into `{type: {acc_id: value}}` and a plain-id State into `{id: value}`.
- Statement parser/applier: `paired_intake.eligible_accounts` (248), `check_balance_rows` (259), `apply_balances` (325). It reads sheets `Assets (Dr)`, `Liabilities & Equity (Cr)`, `Tally`. Template builder `xlsx_templates.build_balances_template` (379), helpers `_bf_accounts_sheet` (408), `_bf_tally_sheet` (438).
- Arrears: `pending_receivables.py` internal keys `FIELDS = ("flat_number","amount","overdue_days","remarks")`, `_ALIASES` (26), `parse_upload` (271, reads sheet "Receivables"), `build_template` (319), `clean_rows` (111), `total` (167), `sdr_total` (177). `paired_intake.apply_pending_receivables` (413) **raises when the arrears total differs from Sundry Debtors**; saves rows to draft `brought_forward.receivables`. There is **no visible arrears grid** in the stage today.
- Annex C: `onboarding_service._annex_c` (1895 to 1977). Constants `FUND_TABS`, `BANK_TABS`, `RECEIVABLE_TABS` at `onboarding_service.py:50-52`. Step validation: `validate_step` branch `brought_forward` (885 to 898) already blocks Next when arrears do not tie to Sundry Debtors and when Dr != Cr.

**Defect found (drives decision D3):** the blocking control `bank_agrees` in `_annex_c` can never pass for any society with a bank, cash or deposit balance. It needs either `draft.brought_forward.reconciliation` (written only by `save_bank_reconciliation`, which has **no callers**) or `annex_c_inputs.bank_agrees` (written only by `save_annex_inputs`, which has **no callers**). `_rec_status` (callbacks:288) is also uncalled.

**Dead code with no callers** (verified by grep): `xlsx_templates.build_bf_template` (68), `build_statement_template` (136), `build_statement_templates` (161), `STATEMENT_COLUMNS` (133), `BALANCES_SHEET` (376).

## 4. Requirements ledger (the owner's 16 points)

Target stage order, top to bottom:

1. **R1** Financial Year (start year, `sw-bf-fy`) and As-on date (`sw-bf-as-on`). Keep as is, first thing in the stage.
2. **R2** Card **"Funds selected for this society"**, directly after R1 (move it up; content unchanged).
3. **R3** Statement buttons (in a labelled block "Statement"):
   - **Download 'Statement' template** (id `sw-bf-tpl`)
   - **Upload 'Filled Statement'** (`sw-bf-xlsx`, `.xlsx`)
   - **Upload 'Statement.pdf'** (`sw-bf-pdf`, `.pdf`)
   - **Fill 'Brought Forward' Grid** (`sw-bf-file`)
4. **R4** Apt-Arrears buttons (labelled block "Apt-Arrears") plus a visible **Apt-Arrears grid** (new `dash_table.DataTable`, id `sw-bf-arrears-grid`):
   - **Download 'Apt-Arrears' template** (`sw-bf-pr-tpl`)
   - **Upload 'Filled Arrears'** (`sw-bf-pr-xlsx`)
   - **Upload 'Apt-Arrears.pdf'** (`sw-bf-pr-pdf`)
   - **Fill 'Apt-Arrears' Grid** (`sw-bf-pr-file`)
5. **R5** **Annex C controls** panel (new, id `sw-bf-controls`), live. Exactly three controls (section 6).
6. **R6** Every parent/group row shows a **calculated total** of its `has_bf=True` children. Totals are display only and are **never stored** (stored rows stay per account, so Annex C cannot double count).
7. **R7** Layout swap: **Liabilities & Equity (Cr) on the left, Assets (Dr) on the right.**
8. **R8 to R16**: the group tree in section 5.

Keep the existing component ids listed in R3/R4 (relabel only) so callbacks do not need renaming.

**Owner's second instruction (2026-11-21) supersedes parts of the first list:**
- **R15 (Gifts Given as a Dr line)** is withdrawn. Gifts given are an expense, so they have no Brought Forward row (section 4A).
- **R9 (Reserves & Funds)** now lists Gifts Received only as the **earmarked** fund; **Provisions leave R9** and join Current Liabilities (R11).
- **R13 (Current Assets)** no longer contains Investments; long-term Investments become **Non-Current Investments**, shown with Fixed Assets under a Non-Current Assets header.

## 4A. Chart of accounts corrections in `database/seed.py` (do first, slice S0A)

Why: four accounts were classified against standard accounting practice, and `fn_balance_sheet_fy`, the statutory mapping and this stage all read that classification. The owner asked for the chart itself to be corrected, not only the screen layout.

| Account | Today | Standard practice | Change |
|---|---|---|---|
| **Provisions** (3250) | Cr, under **3000 Equity** | A provision is a liability | parent **3000 to 2200** (Current Liabilities). Stays Cr, `has_bf=True`, tab `Prov` |
| **Gifts Received** (3240) | Cr, under **3000 Equity**, one account for every gift | A gift is **income** if general, a **fund** if given for a stated purpose | split into two accounts (below) |
| **Gifts Given** (3260) | **Dr**, under **3000 Equity**, `has_bf=True` | A gift given is an **expense** | removed; re-created as expense **51200** |
| **Investments** (1200) | Dr, directly under 1000 Assets, shown as a current asset | Long-term investments are **non-current** | renamed Non-Current Investments |

### 4A.1 Exact edits to `ACCOUNTS`

Row format is `(id, name, tab, display_name, parent_id, drcr, has_bf, depr_pct, mutuality, tds_section)`. Make exactly these edits and no others (keep the column alignment of neighbouring rows):

1. **3250 Provisions**: change `parent_id` `3000` to `2200`.
   `(3250,  "Provisions", "Prov", "Provisions", 2200, "Cr", True, 100, None, None),`
2. **3240**: becomes the earmarked fund. Keep id and tab. New name and display, parent `3200`:
   `(3240,  "Earmarked Gifts Fund", "Gifts", "Gifts Received (Earmarked Fund)", 3200, "Cr", True, 100, None, None),`
3. **3260 Gifts Given**: delete the row.
4. **New 51200** (expense), inserted after the 51190 row and before 5200:
   `(51200, "Gifts Given", "GiftGiven", "Gifts & Donations Given", 5100, "Dr", False, 100, None, None),`
   (it sits with the other expense accounts under 5100; `has_bf=False` because profit-and-loss accounts never carry a brought-forward balance.)
5. **New 4140** (general income), inserted after the 4130 row:
   `(4140,  "Donations & Gifts Received", "DonInc", "Donations & Gifts Received (General)", 4100, "Cr", False, 100, "non_mutual", None),`
   `non_mutual` is the conservative choice: gifts and sponsorship from outsiders are taxable receipts. The CA can reclassify member donations.
6. **1200**: change name and display only, keep parent 1000, tab `Inv`, `has_bf=True`:
   `(1200,  "Non-Current Investments", "Inv", "Non-Current Investments", 1000, "Dr", True, 100, None, None),`

Do not touch any other row. Do not renumber anything else. 3240, 3250 and 1200 keep their ids so existing postings and the investment register keep working.

### 4A.2 Other seed.py edits (same file)

- `UP_AOA_ACCOUNT_MAPPINGS` (line 1306): change the 1200 description text to `"Non-Current Investments"` (head stays `INVESTMENTS`); add `(3240, "OTHER_LIABILITIES", "Earmarked gifts fund")` and `(4140, "OTHER_INCOME", "Donations & Gifts Received")`. Both heads already exist in `STATUTORY_HEADS_UP_AOA`. Look at how other 5xxxx expense accounts are mapped: if they are mapped, map 51200 the same way using an existing head; if none are mapped, add nothing for 51200.
- `RECEIPT_TYPES` (about line 2404): the sample receipt "Corporate Sponsorship Gift - Winter Fete" (2,500, vendor2, cheque 000512) is general sponsorship income. Change its account from `3240` to `4140`. Update the comment `22 -> 3240 (Gifts)` (about line 2388) to `22 -> 4140 (DonInc)`.

### 4A.3 Other files

- `app/dash_apps/pages/setup_wizard.py` lines 2018 to 2020 (the fallback label dict in the Brought Forward branch): set `3240` to `"Gifts Received (Earmarked Fund)"` and delete the `3260` entry.
- `database/estatehub.sql` about line 11777, `fn_gst_default_supply_class`: add `'Gifts'` to the `'not_a_supply'` tab list (an earmarked fund movement is not turnover). Update the comments at about lines 16371 and 19982 that say "3240 Gifts Received" to "3240 Earmarked Gifts Fund". Read about lines 8605 to 8630: a comment there uses "Gifts Given" as the example of a Dr child inside a Cr tree; if the code is generic, change only the example wording; if the code depends on that account, stop and report.
- `schemes/fund_register.py` lines 229 and 241: change the wording "Gifts Received (3240)" to "Earmarked Gifts Fund (3240)". Grep `test/` for those exact strings first and update any test that pins them.
- `database/default_accounts_estateacc.py` line 245: the `'donation'` row has `'account_hint': 'Gifts Received'`. Read how `account_hint` is resolved and change the hint so it still resolves, now to the new general income account (4140).
- `app/services/onboarding_service.py` line 50: `FUND_TABS` gains `"Gifts"` (earmarked gifts are restricted money, so the funds control must cover them). This constant moves to `bf_controls.py` in slice S2; add `"Gifts"` in the new location.
- Grep the repo for `"Investments"` / `'Investments'` used as a lookup key (not as display text) before renaming 1200. If anything looks the account up by that name, change the lookup to the id or tab `Inv`.

### 4A.4 Tests that pin the old names (update, do not skip)

- `test/test_fund_register.py` line 146: `by_id[3240][1] == "Gifts Received"` becomes `"Earmarked Gifts Fund"`.
- `test/test_fund_controls_live.py` lines 241 and 245: expected name `"Gifts Received"` becomes `"Earmarked Gifts Fund"` (live-Postgres test; update it even if it will be skipped).
- Run `grep -rn "3260\|GiftGiven\|Gifts Given" app database test schemes` and clear every hit.

### 4A.5 New test `test/test_chart_of_accounts_standard.py`

Import `ACCOUNTS` from `database.seed`, index by id, and assert:
- 3250: parent 2200, `Cr`, `has_bf`.
- 3240: parent 3200, `Cr`, `has_bf`, name `Earmarked Gifts Fund`.
- 3260 does not exist; 51200: parent 5100, `Dr`, `has_bf` is False, tab `GiftGiven`.
- 4140: parent 4100, `Cr`, `has_bf` is False, mutuality `non_mutual`.
- 1200: display `Non-Current Investments`, `Dr`, `has_bf`.
- No account has the same id twice, every `parent_id` exists, and **no `has_bf=True` account has an ancestor 4000 or 5000** (walk the parent chain).
- `UP_AOA_ACCOUNT_MAPPINGS` contains 3240 and 4140, and every mapped account id exists in `ACCOUNTS`.

### 4A.6 Checks before you finish S0A

1. **Receipt form**: find how the receipt screen builds its account list (grep for where `RECEIPT_TYPES` accounts or the receipt account dropdown are loaded). Report whether 3240 (now under 3200) and 4140 are both selectable when recording a gift. **Do not change the form in this plan**; report the finding so the owner can decide.
2. **Investment register**: find how the investment/deposit register stores and reads its account (`acc_id` 1200 in the seed rows near line 802). Confirm the rename does not break it.
3. `python scripts/build_scheme_sql.py --check` still exits 0.
4. Existing development databases must be dropped and re-seeded (alpha, no backward compatibility). **Write no ALTER or UPDATE migration.**

Known limits, flagged and not built: nothing moves a spent earmarked gift from 3240 to income (the CA posts a journal); the investment register has one account, so investments maturing within 12 months of the balance sheet date are strictly current but still sit in Non-Current Investments (the CA can reclassify); `2290 TDS to IT` is a Dr account under Current Liabilities (a set-off against TDS payable, left as is).

## 5. Group layout (R6 to R16), one data structure

Create **`app/services/bf_layout.py`** (pure Python, no Dash, no DB). It is the only place that knows the grouping. The seed parents still differ from this grouping (1200 sits directly under 1000, 1400 under 1000, 1410 under 1400), so **do not derive groups from `ACCOUNTS` parents**.

A node is a dict with optional `acc` (account id with its own amount input) and optional `children` (list of nodes), plus `key` and `label` for headers. Leaves are plain ints.

```python
LAYOUT = {
  "Cr": [   # LEFT column, titled "Liabilities & Equity (Cr)"
    {"key": "eq",  "label": "Equity",                  "children": [3100]},
    {"key": "res", "label": "Reserves & Funds",        "children": [3230, 3270, 3220, 3210, 3280, 3240]},
    {"key": "ncl", "label": "Non-Current Liabilities", "children": [2110]},
    {"key": "cl",  "label": "Current Liabilities",     "children": [2240, 3250]},
  ],
  "Dr": [   # RIGHT column, titled "Assets (Dr)"
    {"key": "nca", "label": "Non-Current Assets", "children": [
        {"key": "fa", "label": "Fixed Assets", "children": [1110, 1140, 1130, 1120, 1160, 1150]},
        1200]},                                   # Non-Current Investments
    {"key": "ca",  "label": "Current Assets", "children": [
        {"key": "bank", "label": "Bank A/c", "children": [1311, 1312]},
        1320, 1330]},
    {"key": "lag", "label": "Loans & Advances Given", "acc": 1400, "children": [1410]},
    {"key": "sdr", "label": "Sundry Debtors", "children": [1510, 1520]},
  ],
}
```

Rules:
- **Total of a node = (its own amount if it has `acc`) + sum of child totals.** Header rows are read-only text; leaf and `acc` rows have the `sw-bf-amt` input. (1400 and 1410 are both `has_bf=True`; this rule keeps both and never double counts.)
- Order inside groups follows the owner's lists (R12 order: Immovable, Machinery, Instrument & Tools, Furniture, Computer, Car).
- 3210 Sinking Fund Reserve and 3280 Depreciation Fund are not in the owner's list but are `has_bf=True` and opt-in; they stay in the layout and are **hidden** when the fund catalogue says the society has not opted in (`bf_info(acc_id, held_keys, up)["hidden"]`, already used at `setup_wizard.py:2048`). A group whose children are all hidden is not rendered.
- Gifts Given (old 3260) is no longer a balance-sheet account (section 4A); it has no row here.
- Provisions (3250) is a Current Liabilities line; the earmarked gifts fund (3240) is a Reserves & Funds line.
- Non-Current Assets is a layout header only (no account); it totals Fixed Assets plus Non-Current Investments (1200).
- Fixed Assets children **all need ledger rows** (R12) and so do Non-Current Investments and Deposits (R13): the ledger-mandatory set becomes the current set **plus 1110** (Immovable Assets, currently missing) and **plus 3240** (one ledger line per gift purpose or donor), **minus 1510 and 1520** (their detail now lives in the Apt-Arrears grid). Final set: `{1110,1120,1130,1140,1150,1160, 1200, 1311,1312,1320,1330, 1410, 3210,3220,3230,3240,3270,3280}`. Edit `BF_LEDGER_MANDATORY_ACCOUNTS` in `setup_wizard.py:18`.

API of `bf_layout.py`:
- `side_nodes(side, is_hidden) -> list[node]` (hidden accounts and empty groups removed).
- `roll_up(side_nodes, amounts: dict[int, Decimal]) -> dict[str, Decimal]` keyed by node `key`, plus the side total under `"_total"`.
- `ordered_account_ids(is_hidden) -> list[int]` (Cr side first, then Dr; used by the template).
- Import-time `_validate()` asserts: every layout id exists in `database.seed.ACCOUNTS` with `has_bf=True`; **every `has_bf=True` account appears exactly once**; each id sits under the side that equals its `drcr`. A failure must raise at import so a wrong id can never silently drop an account (it would unbalance Dr/Cr).

## 6. Annex C controls (R5)

Create **`app/services/bf_controls.py`** (pure). Move the three constants here (with `"Gifts"` added to `FUND_TABS`, section 4A.3) and re-export from `onboarding_service` (`from app.services.bf_controls import BANK_TABS, FUND_TABS, RECEIVABLE_TABS`) because `test/test_annex_c_from_draft.py:9` reads `ob.RECEIVABLE_TABS`. Do not import `onboarding_service` from `bf_controls` (circular import).

```python
def totals(rows, accs) -> dict   # rows: [{"acc_id","bf_amount"}]; accs: {id: {"tab_name","drcr_account"}}
  # -> dr, cr, fund_cr (Cr rows with tab in FUND_TABS), bank_dr (Dr rows with tab in BANK_TABS), debtors_dr (Dr rows in RECEIVABLE_TABS)
def three_controls(t, arrears_total) -> dict   # keys: "balanced", "funds_backed", "arrears_tie"
```

| key | rule | shown figures |
|---|---|---|
| `balanced` | Total Dr == Total Cr and at least one row | Dr, Cr, difference |
| `funds_backed` | Total Funds (Sinking, Repair, Corpus, Major Repair, Depreciation **and Earmarked Gifts**) **<=** Banks + Deposits + Cash-in-hand (`bank_dr`) | Funds, Banks+Deposits+CiH, headroom |
| `arrears_tie` | Sundry Debtors (Cash + Digital) == Apt-Arrears total | SDr total, arrears total, difference |

Keep the dict shape `{"passed", "reason", "blocking"}` of `_ctl` (onboarding_service.py:1814) and keep these three keys so existing readers keep working.

`_annex_c` must call `bf_controls.totals/three_controls` and **delete its inline duplicates** of these sums and controls. The Apt-Arrears total comes from `pr.clean_rows(draft_bf["receivables"], known_flat_numbers(society_id))` then `pr.total`, as it does now (line 1929), so the live panel and the sealed annex give the same answer. The live panel calls the same functions with the grid values.

Keep unchanged: `accounts_known`, `audited_statements`, `ca_review`.
**Delete** (decision D3): the `bank_agrees` control, the content keys `bank_agrees_to_statement` and `bank_reconciliation`, the `recon`/`bank_lines`/`unreconciled` code in `_annex_c`, and the now-uncalled `get_bank_reconciliation`, `save_bank_reconciliation`, `save_annex_inputs`, `reconciliation_state`, `stale_statement_errors` (and its call at `validate_step`, line 898), `_rec_status` (callbacks:288), `_reconciliation_review_rows` and `_saved_reconciliation` (`setup_wizard.py:1407 to 1416`, and the review row at 1302). **Before deleting each, grep the whole repo (`app`, `database`, `test`, `docs`) and report every other reader; if a reader outside tests exists, stop and report.** Known grep hits to inspect: `onboarding_service.py:2913`, `2938` and `undivided_declaration.py`.

## 7. Templates and importers

### 7.1 Statement template (R3)

New `xlsx_templates.build_bf_statement_template(accounts, fy, as_on) -> bytes`:
- **One sheet**, titled `str(fy)` (e.g. `"2026"`; `fy` is the wizard start year).
- Header row, exactly: `account_id, account_tab, account_name, label, side, amount, as_on_date`.
- One row per visible `has_bf` account in `bf_layout.ordered_account_ids` order. Prefilled: `account_id`, `account_tab` (tab), `account_name` (display name), `side`, `as_on_date` (wizard As-on, text `YYYY-MM-DD`). Blank: `label`, `amount`.
- Amount cells: decimal validation `>= 0` (reuse the `DataValidation` pattern at xlsx_templates.py:430). **Do not protect the sheet** (admins must be able to copy a row to add another label for the same account). The importer enforces the locked columns instead.
- No `Tally`, `Header`, `Instructions` or two-section sheets.

New parser `paired_intake.read_statement_rows(xlsx_bytes, fy) -> (rows, errors)`:
- Sheet: the one named `str(fy)`; if absent and the workbook has exactly one sheet, use it; else error "Expected a sheet named 2026".
- Normalise headers: lowercase, `-` and spaces to `_`, so `as-on-date` is accepted as `as_on_date`.
- Skip rows with blank label **and** blank amount.
- `account_id` must be in `eligible_accounts()` (rebuild it from `bf_layout`/`ACCOUNTS`, display names); `side` and `account_tab` must match the master or the row is rejected naming the row number.
- `amount`: `ob.money`, must be `>= 0`.
- `as_on_date` per row must equal the wizard As-on date; refuse the upload if the As-on date is unset.
- `label` required for 1320 Deposits (FD number). Rows for 1510/1520 must have a blank label (error: "list flats in the Apt-Arrears sheet").
- Duplicate `(account_id, label)` is an error.
- Collect **all** errors, return them together; apply nothing on any error.

`paired_intake.apply_balances` is rewritten around it. **Fill = replace**: the grid becomes exactly the sheet.
- Per account: `bf_amount` = sum of its rows; `ledger_rows` = its labelled rows as `{"flat_number": label, "amount", "overdue_days": None, "remarks": ""}` (key names unchanged, the ledger grid uses them).
- Each stored row: `{"acc_id","tab","side","bf_amount","remarks":"Per statement <as_on>","evidence_id","sha256","filename"}` where evidence is the filed Statement.pdf pair (`file_pair(... "balances" ...)` as today).
- Replace `draft.brought_forward.rows` entirely; keep `receivables`, `fy`, `as_on_date`.
- Keep the guards: sealed annexes refuse, xlsx magic/size check (`check_xlsx`), admin-only.
- **Delete** `check_balance_rows`, the Tally logic, `build_balances_template`, `_bf_accounts_sheet`, `_bf_tally_sheet`, `BALANCES_SHEET`, `build_bf_template`, `build_statement_template(s)`, `STATEMENT_COLUMNS`, and the import at callbacks:40.

`sw_bf_template` (callbacks:333): pass the wizard `fy` and `as_on`, call `build_bf_statement_template`, file name `Statement <fy>.xlsx`. Read `fy`/`as_on` from the saved draft, falling back to `fy_start_year()` (import it: `from app.utils.fiscal import fy_start_year`; the module only imports `fy_start_date` today).

### 7.2 Apt-Arrears template (R4)

Template (`pending_receivables.build_template`, rewrite): one sheet titled `str(fy)`; header exactly `flat_no, amount, due_days, remarks, as_on_date`; flat column text-formatted (keep the existing text-format trick so `07` stays `07`); `as_on_date` prefilled; keep the optional "registered flats" reference sheet. Signature becomes `build_template(fy, as_on, rows=(), known_flats=())`; update the caller at callbacks:388 and line 1041 and `test/test_pending_receivables.py:145`.

Parser (`pending_receivables.parse_upload`):
- Sheet `str(fy)`, else the first sheet (replace the hard-coded "Receivables" at line 247).
- Add header aliases: `flat_no` and `flat_number`, `due_days` and `overdue_days`; normalise `-`/spaces to `_` in `_canonical_header`. **Internal keys stay `flat_number` / `overdue_days`** (the draft, the ledger grid and `clean_rows` use them); only the file and the grid column titles change.
- If an `as_on_date` column exists, every non-blank value must equal the wizard As-on date.
- Unknown flats are **accepted** (only spellings are normalised), as today.

`paired_intake.apply_pending_receivables`: **remove the raise on tie-out mismatch** (lines 426 to 434). The tie is now shown by the `arrears_tie` control and enforced by `validate_step` on Next. Keep sealed guard, `file_pair`, and saving `bf["receivables"] = clean`.

### 7.3 Apt-Arrears grid

`dash_table.DataTable(id="sw-bf-arrears-grid")`, editable, `row_deletable=True`, `page_size=25`, columns `{id:"flat_number", name:"flat_no"}`, `{id:"amount", name:"amount", type:"numeric"}`, `{id:"overdue_days", name:"due_days", type:"numeric"}`, `{id:"remarks", name:"remarks"}`, plus a "+ Add row" button (`sw-bf-arrears-add`) and a total line. It renders from `draft.brought_forward.receivables`.
Persistence: add `State("sw-bf-arrears-grid", "data")` to `wizard_nav` (callbacks:438 to 460) and in `_raw_step_values` (callbacks:262) set `"receivables": [non-blank rows]`. `_gather` stores a plain-id State as `form["sw-bf-arrears-grid"]`.

## 8. Slices (do not reorder)

**S0, Recon (no edits).** Confirm every fact in section 3 by grep (ids, line anchors, the four dead-code claims, the `bank_agrees` defect). Run `pytest -q` on the files in section 9 and record the baseline pass/fail. Output a table: requirement id to file:line. Ask questions only about real conflicts.

**S0A, Chart of accounts corrections.** Section 4A, all of it (seed rows, mappings, sample receipt, the other files in 4A.3, the tests in 4A.4 and 4A.5, the checks in 4A.6). Verify: `pytest -q test/test_chart_of_accounts_standard.py test/test_fund_register.py test/test_wizard_audit_fixes.py`, `python scripts/build_scheme_sql.py --check`, and `python -c "import database.seed"`. **Report the two findings of 4A.6 (receipt form, investment register) before starting S1.**

**S1, `bf_layout.py` + `test/test_bf_layout.py`.** Section 5. Pure; no other file changes. Needs S0A (the layout validates against the corrected chart).
Tests: every `has_bf` account appears once; sides match `drcr`; hidden fund removed and empty group dropped; `roll_up` on the fixture in section 10 gives the stated totals; a bad id raises at import (monkeypatch).

**S2, `bf_controls.py`, rewire `_annex_c`, delete the dead reconciliation code.** Section 6. Update `test/test_annex_c_from_draft.py` (it tests `reconciliation_state` and `bank_agrees`; delete those tests, keep the arrears and balanced ones, add `funds_backed`).
Tests: `test/test_bf_controls.py`: fixture passes all three; funds 200,000 vs banks 199,999 fails `funds_backed`; arrears off by 1 fails `arrears_tie`; Dr/Cr off by 1 fails `balanced`.

**S3, Statement template + importer.** Section 7.1. Update `test/test_paired_intake.py` (balances template round trip at ~231, apply tests at ~456 to 507).
Tests: `test/test_bf_statement_template.py`: header row exact; sheet title equals `str(fy)`; template lists every visible `has_bf` account and none other (and no 3260 or 51200); Provisions has side Cr; fund hidden when not opted; round trip of the section 10 fixture fills 20+ rows; wrong As-on, wrong side, unknown id, label on 1510, missing label on 1320, duplicate label each give a row-numbered error and **apply nothing**; a non-xlsx gives a user-facing error, not a traceback.

**S4, Apt-Arrears template + importer + grid persistence.** Sections 7.2 and 7.3 (service side only: template, parser, apply). Update `test/test_pending_receivables_pair.py` (the tie-out failure test at ~145 must now expect success) and `test/test_pending_receivables.py:145`.
Tests: `test/test_bf_arrears_template.py`: header exact; both old and new header names parse; unknown flat accepted; as-on mismatch rejected; mismatch with Sundry Debtors is **not** an upload error.

**S5, Stage layout (`setup_wizard.py` BF branch).** Section 4 order; R7 swap; `bf_layout`-driven rows and header totals (`{"type":"sw-bf-total","node":<key>}` plus `sw-bf-side-total-cr` / `-dr`); the arrears grid (7.3); the controls panel container `sw-bf-controls`; relabelled buttons; new `BF_LEDGER_MANDATORY_ACCOUNTS`. Initial totals and panel are computed server-side at render from the draft using `bf_layout.roll_up` and `bf_controls`. **Delete** `_render_node`, `_side`, the duplicate heading row at 2277 to 2280, and `_bf_account_rows`'s parent-walk (replace with a layout walk). Keep the ledger modal, attachment control and `_get_aoa_label` / `_fund_badge` behaviour for fund rows.
Tests: `test/test_bf_stage_layout.py`: top-level order of the stage children equals FY/As-on, Funds card, Statement block, Apt-Arrears block, controls panel, grid; left column header is "Liabilities & Equity (Cr)"; header totals present for Equity, Reserves & Funds, Non-Current Liabilities, Current Liabilities, Non-Current Assets, Fixed Assets, Current Assets, Bank A/c, Loans & Advances Given, Sundry Debtors; Provisions is listed under Current Liabilities and Non-Current Investments under Non-Current Assets; `test_bf_ledger_warnings.py` updated for the new mandatory set (1110 warns; 1510/1520 do not); `test_fund_register.py::test_wizard_brought_forward_hides_unopted_optional_funds` and `test_wizard_audit_fixes.py` still pass.

**S6, Callbacks.** (a) The two Fill callbacks already exist; only update imports/calls to the new functions and keep the `{P}-body`/`{P}-marker` re-render. (b) New callback `sw_bf_rollup`: `Input({"type":"sw-bf-amt","acc_id":ALL},"value")`, `Input("sw-bf-arrears-grid","data")`; `Output({"type":"sw-bf-total","node":ALL},"children")`, `Output("sw-bf-side-total-cr","children")`, `Output("sw-bf-side-total-dr","children")`, `Output("sw-bf-controls","children")`. Build `amounts` from `ctx.inputs_list` by id; blank means 0; use `bf_layout.roll_up` and `bf_controls`; known flats from `ob.known_flat_numbers(sid)`. Read-only: no DB write. (c) `wizard_nav` State + `_raw_step_values` for the arrears grid (7.3).
Tests: `test/test_bf_rollup_callback.py` calling the callback function directly with a synthetic `ctx` (follow how `test/test_bf_ledger_warnings.py` and `test/test_bf_callbacks_admin_guard.py` call callbacks); non-admin refused on the Fill callbacks.

**S7, Full regression.** `test/test_bf_end_to_end.py` with the fixture in section 10: build the template, fill it, apply, build the arrears file, apply, then run `ob._annex_c` with `fake_db` and assert all three controls pass, header totals equal section 10, Dr == Cr == 800,000. Then assert lowering a bank balance below Funds fails `funds_backed`. Finish with `pytest -q` for the whole `test/` directory; the pre-existing live-Postgres tests (`ESTATEHUB_LIVE_TESTS`) may be skipped, say so.

**S8, Cleanup.** Grep for every deleted name and for `Tally`, `Assets (Dr)` sheet names, `Account Balances.xlsx` in `app test docs README.md EstateHub_Nemotron_Plan.md`; remove or update each. Update the Brought Forward paragraph of `docs/ADMIN_QUICKSTART.md` if it mentions the old template. No unused imports (`ruff`).

## 9. Existing tests that touch this stage (run before and after)

`test_annex_c_from_draft.py`, `test_bf_callbacks_admin_guard.py`, `test_bf_ledger_warnings.py`, `test_paired_intake.py`, `test_pending_receivables.py`, `test_pending_receivables_pair.py`, `test_wizard_audit_fixes.py`, `test_fund_register.py`, `test_fund_controls_live.py` (live; may be skipped), `test_agreement_print.py`, `test_annex_d_and_seal.py`, `test_undivided_declaration.py`.

## 10. Fixture for S1, S2, S7 (balances: 800,000 Dr = 800,000 Cr)

| side | account id : amount (label for ledger-mandatory accounts: "Main") |
|---|---|
| Cr | 3100:500000, 3230:100000, 3270:50000, 3220:50000, 3240:10000, 3250:20000, 2110:30000, 2240:40000 |
| Dr | 1110:200000, 1120:50000, 1200:100000, 1311:120000, 1312:80000, 1320:100000, 1330:55000, 1400:20000, 1510:40000, 1520:35000 |

Expected, left (Cr): Equity 500,000; Reserves & Funds 210,000 (230,000 before the corrections, since Provisions left it); Non-Current Liabilities 30,000; Current Liabilities 60,000 (Sundry Creditors 40,000 plus Provisions 20,000); left total 800,000.
Expected, right (Dr): Fixed Assets 250,000; Non-Current Investments 100,000; Non-Current Assets 350,000; Bank A/c 200,000; Current Assets 355,000 (Bank 200,000 + Deposits 100,000 + Cash 55,000); Loans & Advances Given 20,000; Sundry Debtors 75,000; right total 800,000.
Controls: Funds (3220 + 3230 + 3240 + 3270) = 210,000; Banks+Deposits+CiH = 355,000 (headroom 145,000). Apt-Arrears total must be 75,000 (for example 101:40000, 102:35000).

## 11. Decisions already fixed (from the repo or the owner)

- **D1** Single group layout in `bf_layout.py`. The seed is changed only as in section 4A; groups are never derived from seed parents.
- **D6** (owner, 2026-11-21) The chart follows standard practice: Provisions are a liability, Gifts Received split into general income (4140) and an earmarked fund (3240), Gifts Given is an expense (51200), long-term Investments are non-current.
- **D2** Display names (`acc[3]`) are used in the grid and the template.
- **D3** `bank_agrees` and the reconciliation code are deleted (section 6). Reason: it is unsatisfiable today and the owner's Annex C list has three controls.
- **D4** Fill = replace; per-account attachments added earlier are not kept by a Fill.
- **D5** Tally ingestion and the two-sheet template are removed; the new template is one long-form sheet.

## 12. Assumptions to confirm with the owner (cheap to change, each is one line)

1. **Funds control operator.** Owner wrote "Total Funds = Banks + Deposit + CIH". Implemented as **<=** (funds must be covered), which is the existing behaviour and the older plan. With strict equality every rupee of bank, cash and deposit would have to be a fund, so a society holding any general money could never pass. Change the operator in `bf_controls.three_controls` only.
2. **Sheet name** `"<Financial Year> {YYYY}"` is read as the plain start year, `"2026"`.
3. Column `as-on-date` is written `as_on_date`; the importer accepts both.
4. **Sundry Debtors** no longer require ledger rows (the Apt-Arrears grid is the detail); Cash/Digital split is kept as two amounts.
5. Banks (1311, 1312) and Cash-in-hand (1330) keep their existing ledger-row requirement (not changed by the owner's list).
6. **Funds** for the funds control are the six fund accounts in `FUND_TABS` (Sinking, Repair, Corpus, Major Repair, Depreciation, **Earmarked Gifts**). Earmarked gifts are restricted money, so they must be backed by bank, cash or deposits like the other funds.
7. 3210 Sinking Fund Reserve and 3280 Depreciation Fund appear only when opted in on the Funds step.
8. **Provisions** (3250) go under Current Liabilities. Provisions for gratuity can be non-current; the CA can split them.
9. **General gifts and sponsorship** are income (4140, `non_mutual`, taxable by default). Gifts given for a stated purpose are kept in the Earmarked Gifts Fund (3240) until spent; no workflow transfers a spent gift to income, the CA posts a journal.
10. **Investments** stay one register account (1200). Any maturing within 12 months are strictly current; the plan does not split them.
11. **Gifts Given** is expense 51200 with no Brought Forward row. A society that already gave gifts earlier in the same financial year has them inside its opening surplus.

## 13. Legal note on the hierarchy (web check, 2026-11-21; not legal advice)

- No statute fixes a chart-of-accounts hierarchy or balance-sheet layout for a UP Apartment Owners' Association. The UP Apartment Act 2010 leaves accounting to bye-laws (s.14(8)(e)) and prescribes no format. The UP Model Bye-Laws (cl.49(3) to 49(6), 50 to 52) require an audited annual statement with profit and loss, receipts and expenditure, and a summary of property, assets and liabilities with the valuation basis of fixed assets, plus lists of owners and loanees; they prescribe no further layout.
- ICAI's Guidance Note for non-corporate entities (from 1 April 2024; "technically recommendatory", with the authority of an ICAI Guidance Note) covers societies and adapts the Schedule III structure ("Owners' Fund" instead of "Shareholders' Fund"). A Schedule-III-style grouping (Equity, Reserves, Non-current and Current) is therefore an accepted presentation, not a legal requirement.
- The four classification points raised in the first revision are now **corrected in the chart** (section 4A): Provisions are a liability; Gifts Received are general income or an earmarked fund depending on purpose; Gifts Given is an expense; long-term Investments are non-current. These are standard presentation, not statutory requirements, so the CA should still confirm them.
- Still flagged, not changed: the bye-laws use "reserve fund" and "major repair fund" (cl.3, 39, 46), not "sinking" or "corpus" (names kept, `UP_AOA_2010` statutory mapping unchanged); `2290 TDS to IT` is a Dr account under Current Liabilities.

## 14. Stop conditions

Stop and report (do not push on) if: a test fails twice after fixes; you need to touch files not named in the slice; a requirement conflicts with existing code; a deleted symbol still has a non-test reader; or you cannot tell which of two similarly named components is live. Report what you found; do not guess.

## 15. Definition of done

S0A is done (the corrected chart, with `test_chart_of_accounts_standard.py` passing); R1 to R16 are implemented and each is proven by a named test; every deleted symbol is gone from the repo (grep returns nothing); `ruff` is clean; `pytest -q` passes (live-Postgres tests may be skipped, stated); the wizard imports; S7 passes with the section 10 fixture; and the final report lists each requirement id with its file and test.
