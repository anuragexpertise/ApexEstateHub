# UP AOA: regime, funds, banks, spend controls, votes, office-bearers

Code: `schemes/fund_register.py` (funds, parameters, account routes, billing channels; also read by `database/seed.py`),
`app/services/up_aoa_fund_catalog.py` (screens), `database/estatehub.sql` (controls). Researched 13-14 Oct 2026 from the
UP Apartment Act 2010 and the Model Bye-Laws of 16 Nov 2011 (full text) and press reports of the July 2026 UP RERA IFMS
amendment (notification text not read). The 2011 Rules were read through excerpts only. Not legal advice.

## 1. Regime = State + Constitution
The regime is the named bundle of instruments that govern a society: central Acts, State Act, Rules, Model Bye-Laws.
`scheme_for(state, constitution)` picks it (the billing engine uses the same call). Today only UP + AOA has a researched pack,
`UP_AOA_2010`; every other pair gets `GENERIC` (central laws only). The Setup Wizard shows the choice and, for the picked
State, what each constitution gives (`regime_options`).

## 2. Funds: only the prescribed ones, and those the society opts into
| Fund (account) | Status | When / how it arrives | Rate | Verified |
|---|---|---|---|---|
| IFMS Corpus (3230) | Statutory: Act s.14(5) proviso; UP RERA Reg. 47 as amended 13.07.2026 | once, from the promoter at handover; never billed | by project type and unit category; reported group housing about 20-100, commercial 40 / 50; unit unconfirmed | **provisional** |
| Major Repair Fund (3270) | Model Bye-Law 39 (also 3(1)(d), 37) | on each transfer, from the transferor; also common-area rent and bye-law 37 levies | 1/2% of transfer value | checked |
| Reserve Fund (3220) | Model Bye-Law 46(c) | not billed; appropriated from surplus at FY close | none in law; app default 25% | **provisional** (the 25%) |
| Sinking Fund (3210) | optional, society resolution | on the monthly bill from the resolution date, or at FY close | none in UP law | provisional |
| Repair & Maintenance Fund (3220) | optional, society resolution | with the monthly bill | none in UP law | provisional |

* Brought Forward lists only these: the prescribed funds, plus an optional fund once the society opts in. Share capital is a
  Capital Account item, not a fund. Rent reserve and the bye-law 37 levy are routes into the Major Repair Fund.
* 3220 serves both the Reserve Fund and the optional Repair & Maintenance Fund. Sinking and Repair collected "at FY close"
  join the Reserve pool; they do not post to 3210 / their own account.
* Billing finds 3210 and 3220 by NAME (`Sinking Fund Reserve`, `Repair & Maintenance Fund Reserve`): do not rename them.
* A new mandatory levy that departs from the Model Bye-Laws needs 2/3rd of owners and the competent authority's prior approval
  (bye-law 58; Act s.14(6)).

## 3. How money reaches the books (the nine channels)
| # | Channel | In the app |
|---|---|---|
| 0 | No bill (IFMS) | automatic: opening balance, interest to Interest Income |
| 1 | Every maintenance bill (Sinking, Repair) | automatic, only if opted (`fn_auto_generate_receivables`) |
| 2 | Entrance or transfer | automatic: 1/2% transfer fee (`fn_record_apartment_transfer`), entrance fee 1,000 + share on admission |
| 3 | Monthly budget basis | partly: a monthly budget and fund amounts are billed by undivided interest; no annual budget record or approval step (bye-law 11) |
| 4 | Special major repairs (bye-law 37) | **manual**: no estimate, approval or per-flat split recorded |
| 5 | Surplus at FY close | automatic (`fn_fy_close_reserve_appropriation`) |
| 6 | Events | automatic: ticket sales are income |
| 7 | Common-area rent (bye-law 3(1)(d)) | **manual**: no lease or rent schedule |
| 8 | Non-mutual income (advertising, hoarding) | **manual**: account flagged non-mutual; no contract register |

## 4. Banks and the QR
Each fund can be allotted its own bank account (`fund_bank_account_map`, Fund Management page). The app holds ONE payment QR,
the primary account's. So `fn_resolve_bank_leg` now books **UPI always to the primary bank**; cheque, bank transfer and card
follow the fund's mapped account. To move UPI-collected fund money to the fund's own account, record `fn_transfer_between_banks`.
Before this change a UPI payment for a mapped fund was booked to a bank it never reached.

## 5. Using fund money: resolutions, signatures, audit
* `fn_process_fund_utilization` now requires a resolution reference and date **in the database** (the form already did).
* `fund_spend_policy` (per society; no row = one signature): `min_signatories`, `cosign_above`, `signatory_offices`. A withdrawal
  above `cosign_above` stays *pending* until that many different serving office-bearers sign (`fn_sign_fund_utilization`);
  then it is confirmed and posted. The principal lock is re-checked when the money moves.
* Existing maker/checker (`approval_steps`, RBAC `approval_threshold`) covers payments, not fund withdrawals; the new policy covers those.
* `fn_fund_management_audit(society)` reports: regime recorded; prescribed accounts mapped to their statutory head; IFMS lock;
  opted funds billed without a rate; primary bank; funds kept in another bank (UPI warning); spend policy; reachable signatories;
  President/Secretary/Treasurer recorded; withdrawals without a resolution; withdrawals stuck over 30 days; overdrawn funds.
* Still display-only: the approving body per fund (General Body vs Managing Committee) in Fund Management.

## 6. Votes
One vote per flat (all family members share it) was already enforced. The weight is now chosen when the poll is created:
`apartment` (equal), `undivided_interest`, `area` (flat area / total, frozen), `custom` (weights typed as `FLAT=weight`, frozen
before the first vote, `fn_set_poll_weights`). Weighted polls use the society's quorum and majority rules; an online poll is
still not a General Body resolution (bye-law 10).

## 7. Office-bearers
`committee_offices`: President, Vice-President, Secretary, Joint Secretary, Treasurer (one active holder each) and Working
Committee members, each tied to a **flat** and a named holder with a login. `fn_appoint_office_bearer` refuses a flat that cannot
stand for election (`fn_get_standing.ineligible_stand`: overdue bill, loan arrears, bye-law 7). `fn_committee_current` lists the
committee with each flat's dues, loans, vote, standing and NOC flags and whether the holder can sign. Not built: screens for
this, the election workflow that fills the table from a poll, and role grants for the new offices.

## 8. Open findings (not fixed here)
1. `schemes/UP_AOA_2010.toml` cites **bye-law 46(d)** for a depreciation fund and marks it `checked`; in the gazetted text 46(d) is
   *raising loans*, and no depreciation fund appears in the Model Bye-Laws.
2. `fn_ensure_depreciation_fund` uses account **3240**, which `seed.py` names *Gifts Received*; the function sees it exists and maps
   it to `DEPRECIATION_FUND`, so depreciation would be credited to Gifts Received. Its per-sq-ft branch also reads
   `apartments.built_up_area`, a column that does not exist (the table has `apartment_size`).
3. `DEFAULT_SINKING_FUND_RATE = 0.25` / `DEFAULT_REPAIR_FUND_RATE = 0.75` are labelled rupees per sq ft per month; the benchmarks
   they echo are percentages of construction cost per year (Maharashtra practice, not UP law).
4. Check the IFMS slabs and unit against notification 7098/U.P. RERA/Regulation/2026-27 (13.07.2026) itself.
5. A `.env` was committed once and deleted in commit `cbe11ac`; it is still in git history. Rotate any credentials it held.
