# ApexEstateHub Gold-Standard Plan v4

Oct 28, 2026 · @Anurag Gupta

## Where the repo stands

Since v3 (`3cfe3f4`) the repo moved to `ee9579a` on branch `master`: Phases 1 and 2 are built except the items noted; Phase 3 is built for 3.1, 3.2, 3.4 and 3.8; Phase 4 is in progress (tasks 4.1–4.7 partially built; numbered migrations exist via `database/migrations/001_society_signing_keys.sql`); Phase 5 is built for tasks 5.1–5.4 (assurance records, guards, views/functions in `database/estatehub.sql`, service layer in `app/services/assurance.py`, release gate in `scripts/release_check.py`, docs in `docs/PHASE5_ASSURANCE.md`, tests added). The full suite shows 1103 passing, 2 failing (environment-related in this run), 586 skipped. The previously noted 9 failing tests from before this work are being addressed as part of C.1.

Basis and limits: I read the code, `README.md`, the Phase 0 tracker, CI config and `requirements.txt`, and ran the suite and the endpoint and callback gates against a local Postgres 16. I read no statute or gazette text, so every legal figure stays **\[Verify\]** with your CA or advocate. Nothing here is legal or tax advice.

| Phase | Built in code | Not built |
| --- | --- | --- |
| 0 | 0.1 records; 0.2 tables/engines/service exist; adviser decisions stored (`app/services/adviser_decisions.py`) | 0.2 screen; 0.3 to 0.6 need people or the host dashboard |
| 1 | 1.1 CI with Postgres job, pip-audit, bandit, gitleaks; 1.2 key vault; 1.3 ledger anchors; 1.6 GST authority on invoices; 1.8 s.44AB flag; 1.9 interest wording; 1.10 committee tally from register; 1.12 README signing table | 1.4 scheduling on the host; 1.5 under-protest state; 1.7 proportionate ITC reversal; 1.11 list column fixes |
| 2 | 2.1 to 2.8, 2.9 (`conversation.xlsx`), 2.10, 2.11 | 2.12 hard link from a document to its authorising resolution; fund-withdrawal Approve and Decline screen |
| 3 | 3.1 and 3.2 signed auditor checks and tie-out; 3.4 Decimal money policy; 3.8 source-document guard and per-society vouchers | 3.3, 3.5, 3.6, 3.7, 3.9 |
| 4 | Part of 4.1–4.7: migrations (`database/migrations/001_society_signing_keys.sql`), signing/vault, anchor scripts, basic tests exist; tenant isolation/RLS not yet enforced; role tests, backups/retention, DPDP partially scaffolded | 4.1 enforcement, 4.2 full role tests, 4.3 full migration framework/rollback/version table, 4.4 backups/restore drill with retention holds, 4.5 full key drills, 4.6 DPDP flows/erasure policy, 4.7 full accessibility/mobile checklist |
| 5 | 5.1–5.4 built (engagements/findings, rule opinions, release verifications, guards, views/functions, service, `scripts/release_check.py`, docs, tests) | None in code; assurance activities require external people/reviewers |

Two v3 statements are now wrong. v3 said no versioned migrations existed; one numbered file now does, though the main schema is still a single `estatehub.sql`. v3 counted 297 `float(` calls; the same search now finds 135 lines, most of them in `renderers.py` (49) and `fund_management_callbacks.py` (16), which are display and form code rather than ledger maths.

## What changed from v3

v4 keeps v3's phase numbers and task ids so every commit and test still maps to a task, and changes five things.

1. **Status is explicit.** Every task now says built, partly built or open, checked against the code, not against the README.
2. **Phase 3 is split in two.** What can be built without the CA (3.1, 3.2, 3.4, 3.8, all done) is separated from what waits on a CA layout or formula (3.3, 3.5, 3.6, 3.7, 3.9). Waiting work gets a written question for the CA instead of a guess.
3. **Gaps found while building become tasks.** The fund-withdrawal Approve and Decline screen, the hard link from a document to its resolution (2.12), a screen to classify GST accounts, the adviser-decisions screen (0.2), and a fix for the seeded demo data that makes the tie-out and compliance certificate fail.
4. **Hosting is now a decision, not an assumption.** The repo and the Phase 0 tracker say Render and Aiven; you work on ApexWeave and NeonDB. The scheduler, backup and restore tasks cannot be finished until that is settled.
5. **Phase 5 implemented.** Tasks 5.1–5.4 are built in code (assurance tables/guards/views/functions in `database/estatehub.sql`, service in `app/services/assurance.py`, release gate in `scripts/release_check.py`, docs in `docs/PHASE5_ASSURANCE.md`, tests). Assurance activities still require external reviewers; the system enforces gates and labels remain provisional until evidence is recorded. Current suite shows 1103 passing, 2 failing (environment-related), 586 skipped.

## Open work carried forward

Twenty items remain from v3. Effort is my rough judgement: S about a day, M a few days, L a week or more.

| Task | What is missing | Blocked by | Effort |
| --- | --- | --- | --- |
| 0.2 screen | Per-society screen for adviser decisions; the tables, engines and service exist (`app/services/adviser_decisions.py`) | Nothing | M |
| 0.3 to 0.6 | Advocate opinions, retention answer, UP RERA notification 7098 read, host scheduler check | People, host dashboard | External |
| 1.4 | Anchors daily, patrol hourly, ratification expiry daily are not scheduled; `Procfile` has only `web` | Host decision (see below) | M |
| 1.5 | Under-protest payment state; no `under_protest` anywhere in `app/` or `database/` | Nothing | M |
| 1.7 | Proportionate ITC reversal for exempt supplies | CA's formula and worked example | M |
| 1.11 | NOC list and Security Salaries list column problems, not yet confirmed in the app | A look at both lists | S |
| 2.11 follow-up | Approve and Decline screen for fund withdrawals | Nothing | M |
| 2.12 | A document cannot yet be marked signed from its resolution's Signatures panel | Nothing | M |
| 3.3 | Schedule-format statements, comparatives, notes, accrual policy, fund appropriation entry | CA signs off the layout | L |
| 3.5 | Depreciation by Act version, expense apportionment, brought-forward losses | CA worked example; resolution text | L |
| 3.6 | TDS challan and deposit reconciliation, quarterly statements, 192A row for the 2025 Act, rent per month, 194-IA and 194Q inputs, 31 Mar and 1 Apr 2026 tests | CA forms and figures | L |
| 3.7 | GST books-to-return reconciliation, invoice numbering, HSN/SAC, place of supply, e-invoice check, all-India s.2(6) worksheet | CA input | L |
| 3.9 | Form 26AS and AIS comparison from an imported file | A sample file from the CA | M |
| GST accounts | No screen to classify accounts under s.2(6); today only `fn_set_gst_supply_class` from SQL | Nothing | M |
| Demo data | Seeded data makes the `expenses_vs_ledger` tie-out fail (12 expenses with no ledger lines) and leaves the compliance certificate at fail (no ledger anchor) | Nothing | S |
| Lingering `float(` | 135 lines remain, mostly display and form code; rule parameters and vote weights are meant to stay | Nothing | S |
| Failing tests | Environment-related failures in some test environments (e.g. production checks); core functionality tests mostly passing (1103 passed). Review and fix as needed. | Nothing | M |
| Provisional figures | Committee quorum (more than half), GST authority, wizard interest-resolution capture and 44AB thresholds need advocate or CA confirmation | Advocate, CA | External |
| Phase 4 | 4.1–4.7 partly built (migrations, vault/signing exist); needs enforcement (RLS/cross-tenant tests), full role tests, migration framework/rollback/version table, backups/retention/holds, key drills, DPDP flows/erasure, accessibility/mobile | Phases 1 to 3 mostly done; can run in parallel with CA-gated work per decision 7 | M to L |
| Phase 5 | 5.1–5.4 built in code; assurance activities (engage reviewers, record opinions/reports) pending external parties | External reviewers/people | External |

## Phased plan

Four phases remain, in this order: **C** closes the gaps that need no outside input, **3** finishes the CA-gated statements and returns, **4** hardens the platform, **5** brings in independent assurance. Phase C is new and uses its own ids so v3's numbers stay stable. Phase 4 can start in parallel with Phase 3 once C.1 to C.4 are green, because tenant isolation and migrations do not wait on the CA.

### Phase C: close the build

No CA or advocate input is needed for any task here.

| # | Task (v3 id) | Done when | Effort |
| --- | --- | --- | --- |
| C.1 | Fix the 9 failing tests, deciding for each whether the code or the test is stale | The full suite, live suites included, passes in CI with no known failures | M |
| C.2 | Seed data that passes its own checks: ledger lines for the 12 seeded expenses, and a ledger anchor | Tie-out and compliance certificate pass on a fresh seeded database | S |
| C.3 | Under-protest payment (1.5): held item, recorded dispute, excluded from interest and default status, reversal-only correction | A disputed bill stops accruing interest; deciding it posts the right entries | M |
| C.4 | Document-to-resolution link (2.12): expenses, agreements, NOCs and minutes cannot be marked signed until every required signer has signed on the resolution | A document without the full signature set stays unsigned, tested in the database | M |
| C.5 | Fund-withdrawal Approve and Decline screen, using the same password confirmation and sealing as expenses | A wrong password never approves; Decline stops the withdrawal | M |
| C.6 | Adviser-decisions screen (0.2) and a GST account-classification screen | A society records an opinion reference and classifies an account without SQL | M |
| C.7 | Fix NOC and Security Salaries list columns (1.11) after opening both lists as admin | One column each, no duplicates | S |
| C.8 | Scheduler (1.4) on the chosen host: anchors daily with verify, patrol hourly, ratification expiry daily, on the restricted login, with a run log and a failure alert | A week of runs logged; a forced failure alerts the master | M |
| C.9 | Remaining `float(` in money paths, found by search and judged one by one; the rest documented as display only | No `float(` left where a rupee amount is added, compared or stored | S |

Gate for Phase C: C.1 to C.9 done, one live test per Phase 2 and 3 task in place (see Test debt below), and `README.md` status marks match the code.

### Phase 3: CA-gated statements and returns

Open this phase with one written question pack for the CA. Each task starts only when its answer is in the repo. Tasks 3.1, 3.2, 3.4 and 3.8 are already built.

| # | Task | Question for the CA | Done when |
| --- | --- | --- | --- |
| 3.3 | Schedule-format statements, comparatives, notes, accrual policy, fund appropriation entry per `UP_AOA_FUNDS.md` section 8 | Which layout and note set do you sign? | CA signs the layout |
| 3.5 | Depreciation by Act version, expense apportionment, brought-forward losses | One worked example per item | Example reproduces to the paisa |
| 3.6 | TDS challan and deposit reconciliation, quarterly statements, 192A row, rent per month, 194-IA and 194Q inputs, boundary tests | Forms, rates and the 31 Mar and 1 Apr 2026 treatment | Payable equals deposited; boundary tests pass |
| 3.7 | GST books-to-return reconciliation, invoice numbering, HSN/SAC, place of supply, e-invoice check, s.2(6) worksheet for other turnover; includes 1.7 | ITC formula, numbering scheme, HSN list | Mismatch report empty on clean data, flags a planted error |
| 3.9 | Form 26AS and AIS comparison | A sample file and the matching rule | Differences listed per deductor |

### Phase 4: platform hardening

| # | Task | Done when | Effort |
| --- | --- | --- | --- |
| 4.1 | Tenant isolation: cross-tenant test for every service function, then row-level security or an equivalent; there is no `CREATE POLICY` in `estatehub.sql` today | No test reads or writes another society's rows | M |
| 4.2 | Role tests: Auditor read-only, accountant prepares, admin approves, proven by refusals from the server | Each forbidden action is refused | M |
| 4.3 | Numbered migrations from `database/migrations/001`: every schema change after go-live is a numbered file with rollback notes and a schema-version table | A migration applies and rolls back on a copy | M |
| 4.4 | Backups, restore drill, 5-year retention configurable per society with a hold; depends on the host decision | Restore works; nothing purged inside retention | M |
| 4.5 | Key drills: vault key change with the master key, recovery from the sealed file, revoke and re-issue one society's key, re-anchor, incident runbook | Each drill passes and is recorded with date and attendees | M |
| 4.6 | DPDP: consent records, versioned privacy notice, access, correction and erasure, grievance officer, breach procedure; erasure never edits the ledger **\[Verify current rule status\]** | A test erasure leaves the ledger chain valid | L |
| 4.7 | Accessibility and mobile check of the four new portals | Checklist passed on a phone and a screen reader | S |

### Phase 5: independent assurance

| # | Task | Done when |
| --- | --- | --- |
| 5.1 | External CA review of the books engine and statements | Report received; every finding closed or accepted in writing |
| 5.2 | Advocate review of rule packs and bye-law figures | Opinion reference stored against each rule |
| 5.3 | Penetration test with the key vault and verification pages in scope | Findings closed; retest passes |
| 5.4 | Re-verify the Income-tax Act 2025 transition and the July 2026 IFMS amendment before each release | Dated check recorded per release |

Only after 5.1 to 5.3 should anyone say "audit-grade".

## Decisions needed

Seven decisions hold up work. The first blocks two tasks outright.

| # | Decision | Why it matters | Blocks | Who |
| --- | --- | --- | --- | --- |
| 1 | Which host runs production: Render with Aiven (what `README.md`, `Procfile` and the Phase 0 tracker say) or ApexWeave with NeonDB (what you use) | Scheduler, backup and restore steps differ by host; the repo's docs may describe the wrong one | C.8, 4.4 | You |
| 2 | Committee quorum: is more than half correct | Provisional in code; wrong figure would refuse or pass real meetings | C.4, 5.2 | Advocate |
| 3 | Does a login-password confirmation satisfy the bye-laws and the IT Act for resolutions and approvals | It records who confirmed, not a legal e-signature; paper minutes stay meanwhile | 5.2 | Advocate |
| 4 | Retention beyond 5 years for any record class | Sets the purge rule and the hold | 4.4 | CA |
| 5 | Sections 80P and 80AC for an AOA | The software computes neither and claims neither | 3.5 | CA |
| 6 | Holder of the sealed `SECRET_MASTER_KEY` backup | Losing it and `.env` together makes every signing key unrecoverable | 4.5 | You |
| 7 | Whether Phase 4 starts alongside Phase 3 | Tenant isolation and migrations do not wait on the CA | Schedule | You |

Provisional figures stay labelled provisional in the product until an opinion reference is stored against each. The 44AB thresholds, the GST authority wording and the wizard's interest-resolution capture are in that group.

## Engineering standards and gates

Every phase ends only when these gates pass in CI on a fresh seeded Postgres 16.

1. **Suite green.** `pytest test` with live suites enabled passes with no known failures. Currently 1103 passing, 2 failing (environment-related), 586 skipped; remaining failures tracked under C.1.
2. **Authorisation gates.** `scripts/inventory_endpoints.py --check` and `scripts/check_callback_guards.py` pass; any new callback is classified in `docs/authz_manifest.json` (255 endpoints, 132 still marked legacy-gated).
3. **Scans.** `pip-audit`, `bandit` and `gitleaks` pass, as in `.github/workflows/tests.yml`.
4. **One schema file.** New columns go inline in `database/estatehub.sql`, with no `IF NOT EXISTS` guards; after go-live, changes are numbered files under `database/migrations`.
5. **Money.** Decimal everywhere through `database/money.py`: paisa for ledgers, whole rupee for TDS, floats only at JSON and display edges.
6. **Ledger.** Append-only and hash-chained; correction is by reversal only.
7. **Status honesty.** README marks (✅, 🟡, ⬜) change in the same commit as the code.

**Test debt.** v3 required a live-Postgres test at the end of each Phase 1 and 2 task. At your instruction the Phase 2 and Phase 3 code was built without new tests, so the signing, ratification, certificate, tie-out and source-document guard code is covered only by the existing suite and manual runs. Closing this is a task in its own right and should come before Phase 4 starts: one live test per Phase 2 and 3 task, each proving its "done when" line.
