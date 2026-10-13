# UP AOA funds: status, rate, applicability

Source of truth in code: `app/services/up_aoa_fund_catalog.py` (read by the Setup Wizard's **Funds** and
**Brought Forward** steps). Researched 13 Oct 2026 from the UP Apartment Act 2010 (full text), the Model Bye-Laws of
16 Nov 2011 (full text, Notification 3977/8-1-11-115 D.A./02 T.C.-I) and reports of the July 2026 UP RERA IFMS
amendment. The UP Apartment Rules 2011 were read through excerpts only.

| Fund (account) | Status | When levied | Rate | Verified |
|---|---|---|---|---|
| IFMS Corpus / Corpus Fund (3230) | **Statutory** - Act s.14(5) proviso; UP RERA Reg. 47 as amended 13.07.2026 | One-time, by the promoter, at registration of the deed; AOA receives it at handover | By project type and unit category; reported group housing about 20-100, commercial 40 / 50; unit (sq ft or sq m) unconfirmed | **Provisional** - notification text not read |
| Major Repair Fund (3270) | **Model Bye-Law** - bye-law 39 (2nd proviso), 3(1)(d), 37 | On each transfer, paid by the transferor | 1/2% of transfer value | Checked |
| Common-area rent reserve (books to 3270) | **Model Bye-Law** - 3(1)(d) | As licence income arrives; needs all members' written consent and the competent authority's permission | None | Checked |
| Major-repair special levy (one-off bill) | **Model Bye-Law** - 37 | After the Board approves an engineer's estimate | Each owner's share of the estimate | Checked |
| Reserve Fund (3220) | **Model Bye-Law** - 46(c): common profits are the nucleus | Not levied; appropriated from surplus at FY close | No percentage in law; app default 25% | **Provisional** (the 25%) |
| Entrance fee / share capital (3100) | **Model Bye-Law** - 4 and 6 | On becoming a member, including every transferee | 1,000 entrance fee; at least one share | Checked |
| Sinking Fund (3210) | **Optional - Provisional** | Only after a General Body resolution | None in UP law | Provisional |
| Repair & Maintenance Fund (3220) | **Optional - Provisional** (routine repairs are already common expenses, Act s.18, bye-laws 25 and 35) | With the monthly assessment; a separate head only by resolution | None in UP law | Provisional |

Notes
- A new mandatory levy that departs from the Model Bye-Laws needs 2/3rd of owners and the competent authority's prior
  approval (bye-law 58; Act s.14(6)).
- 0.25% (sinking) and 0.75% (repair) of construction cost a year are Maharashtra co-operative benchmarks, not UP law.
- Account 3220 is shared: the Reserve Fund appropriation at FY close and the Repair & Maintenance reserve both use it.

Open items found while researching
1. `schemes/UP_AOA_2010.toml` cites **bye-law 46(d)** for the depreciation fund (`depreciation_fund_*`, marked
   `checked`). In the gazetted text 46(d) is *raising loans with the competent authority's approval*; no
   depreciation fund appears in the Model Bye-Laws. Treat those parameters as society policy and re-label them.
2. `DEFAULT_SINKING_FUND_RATE = 0.25` and `DEFAULT_REPAIR_FUND_RATE = 0.75` are labelled "rupees per sq ft per month"
   in `setup_wizard.py`, but the benchmarks they echo are percentages of construction cost per year.
3. Check the IFMS figures and the rate unit against the notification itself:
   7098/U.P. RERA/Regulation/2026-27 dated 13.07.2026 (UP RERA website).
