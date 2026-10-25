# ApexEstateHub Gold-Standard Plan v3

Oct 24, 2026 · @Anurag Gupta

## Summary

v2 is already out of date: the repo moved to commit `3cfe3f4` (24 Oct 2026, 06:46 IST), and seven items v2 lists as open are now done in code. What is still missing falls into five blocks:

- **Evidence modules for authorities:** rule-application register, signed per-FY compliance certificate with a public verification page, ratification-of-irregular-items register, approval ladder.
- **Tax and GST correctness:** under-protest payment state, GST exemption authority on invoices, proportionate ITC reversal, Sec 44AB flag, interest cap and simple/compound declaration, depreciation by Act version, expense apportionment.
- **Number discipline:** 297 `float(` calls remain across `app/` and `database/`; only `income_tax_export.py` uses `Decimal`.
- **Privacy:** every DPDP Act control is marked not built in the README.
- **Platform assurance:** CI runs only the hermetic job, so the \~15 live-Postgres accounting suites never run on push; no row-level security; no versioned migrations; no backup or retention procedure found.

Basis and limits: I read the code, `README.md` status tables and `ER.md` §9 at `3cfe3f4`. I did not run the tests, open the app against a database, or read any statute or gazette text, so every legal figure stays **\[Verify\]** with your CA or advocate. Nothing here is legal or tax advice.

Updates, 24 and 25 Oct: your six Phase 0 answers are recorded and every task in Phases 0 to 5 is written out with its finish test. The signing-key design has four keys per society and two top keys: `SECRET_VAULT_KEY` in the host `.env` file, and `SECRET_MASTER_KEY`, held by you outside both `.env` and the database, which is needed to change the vault key. You dropped the news feature and the monthly bill job.

Update, 25 Oct (later): the plan now covers who signs what and how spending above the ₹20,000 ladder is approved, with tasks 2.10 to 2.12 for office-bearer records, Approve and Decline buttons and signing from the resolution, and task 1.12 for the README and Setup Wizard table. No code has been changed.

## Corrections to v2

Seven v2 items are done in code. Two of them are still shown as open in the project's own README and `ER.md`, so those documents need updating.

| v2 item | What the code at `3cfe3f4` shows |
| --- | --- |
| 2. Callback-level setup enforcement | Done. `require_session` in `app/security/guards.py` raises `PreventUpdate` while the society's setup is unfinished, with an `allow_during_setup` carve-out and a fail-closed database check. `test/test_setup_guard_callbacks.py` exists. |
| 3. Interest default 1.75 | Done in `app/`. The drilldown save treats a blank rate as no interest (comment cites bye-law 46(a)). The only `1.75` left is the SQL row marked SUPERSEDED. |
| 5. Catalog edit master-only | Done. `update_instrument` in `regime_rules_admin.py` calls `_require_master` and demands a reason of minimum length. |
| X-02 aggregate turnover | Done in `gst_export.py`: an "Aggregate Turnover" worksheet under CGST s.2(6). The README and `ER.md` §9 still say not done. It covers the society's own books only, which its footer states. |
| G-02 typed vote percentage | Done for General Body decisions: the typed value is ignored and the tally comes from the register. Managing Committee decisions still take a typed value. |
| 9. Poll auto-declare and reminder | Done per a comment in `poll_callbacks.py` (restored in the polls list loader). A member-printable poll list was not found. |
| 1. Wizard labels | Mostly done via `STEP_LABELS` ("Compliance", "By-Laws Adoption", "Accounts", "GSTIN & GST Rates"). The extra steps (Legal Regime Selection, Funds, Review) remain, so the order is still a decision for you. |

Two other v2 notes also need a small change. The Security Salary `shift_fraction` edit exists, with a database trigger that recalculates the amount. The master KPI list does filter by `plan_validity` in `loaders.py` for expired and expiring plans, but I did not check every KPI list.

## Still open, verified against the code

25 gaps remain. Effort is my rough judgement: S is about a day, M a few days, L a week or more.

| Area | Gap | Evidence | Effort |
| --- | --- | --- | --- |
| Government | Rule-Application Register | README marks it not built; no code found | M |
| Government | Signed per-FY compliance certificate with a public verification page | README marks it not built; `compliance_certificate` appears nowhere | M |
| Government | Ratification-of-irregular-items register | `ER.md` §7 and §9 list it as a new module | L |
| Government | Automatic reversal when ratification expires (G-04) | `fn_expire_overdue_ratifications` raises a compliance flag only; nothing links a posting to its authorising decision | L |
| Government | Delegation-of-powers approval ladder (G-06) | Not built; needs a policy decision first | L |
| Government | Advocate opinions behind provisional bye-law figures (G-05) | `advocate_opinion_ref` exists; no opinions stored | External |
| Income tax | Under-protest payment state | No `under_protest` in `app/` or `database/` | M |
| Income tax | Sec 44AB tax-audit flag | `statutory_rules.py` says "no Sec. 44AB flag yet" | S |
| Income tax | Form 26AS / AIS match; 80P and 80AC treatment | README marks all not built; 80P is a CA question | M |
| Income tax | Expense apportionment, depreciation by Act version, brought-forward losses (A-03, I-01) | `ER.md` §9 | L |
| Income tax | TDS limits: no IT2025 row for 192A; rent tested per bill, not per month; 194-IA and 194Q lack inputs | `ER.md` §9 T-01 | M |
| Income tax | Arrears interest: no cap check, no simple or compound declaration (I-02) | `ER.md` §9 | S |
| GST | Fund-exemption authority printed on invoices (X-01) | Stored and enforced by `ck_fund_gst_exempt_authority`; no print path found | S |
| GST | Proportionate ITC reversal for exempt supplies (X-03) | Only the s.18(6) disposal reversal exists | M |
| GST | E-invoicing applicability check | README marks it not built | S |
| GST | Turnover worksheet covers one PAN's books in one state; s.2(6) is PAN-wide and all-India | Footer in `gst_export.py` | CA input |
| Accounting | Explicit Cash-in-Hand ledger leg | Deliberately deferred (`ER.md` A-02) | L |
| Accounting | Source-document guard missing on `payables` and `receivables` | `ER.md` A-01 note | M |
| Accounting | Voucher sequence is platform-wide, receipts are hash strings | README partial | M |
| Numbers | 297 `float(` calls; worst files: `financial_statements_export.py` 32, `ledger_export.py` 16, `gst_export.py` 13, `asset_export.py` 12 | `grep` of `app/` and `database/` | M |
| Privacy | DPDP consent, data-principal rights, retention, breach workflow, grievance officer | Five README rows marked not built | L |
| Platform | CI runs only the hermetic job | `.github/workflows/tests.yml`: no Postgres job, no dependency, secret or static scans | S |
| Platform | No row-level security or cross-tenant test suite | No `CREATE POLICY` anywhere | M |
| Platform | No versioned migrations | `migrate.py` applies one file to an empty database | M |
| Platform | Loose dependency pins; `Flask-Cors` listed twice; no backup, restore or retention procedure found | `requirements.txt`; search of `app/`, `database/`, `scripts/`, `docs/` | S |

## Not checked: needs a run, not a read

These eight items cannot be settled by reading code. Each has a one-step check.

| Item | What I saw | How to settle it |
| --- | --- | --- |
| Live-Postgres test suites pass | About 15 `*_live.py` files exist; I did not run them | Start Postgres 16, run `pytest test`, record the result |
| Seeded legal URLs point to the right document | URLs live in `kpi_rule_links` and `legal_instrument_catalog` | Script an HTTP check of every URL, then read each target once |
| NOC list "Body Text" and Security Salaries due duplicate columns | `body_text` is saved on `nocs` and `society_agreements`; `schema_introspect.py` names it near line 340 | Open both lists as admin and compare columns |
| Every master KPI list respects plan validity | `loaders.py` filters by `plan_validity` in at least two places | Open each master KPI list with an expired-plan society |
| Patrol cron runs in production and feeds salary deductions | `scripts/patrol_cron.py` raises missed-patrol alerts; `Procfile` has no schedule; no deduction link found | Confirm the scheduler on ApexWeave and trace a missed scan to a payable |
| Per-flat undivided interest after enrolment | `fill_undivided_interest` exists in the UP compliance callbacks | Enrol a test society and check the flats' percentages sum to 100 |
| Enrolled lists open a working profile | `test_team_committee_profiles.py` exists | Click through one owner, tenant and team profile |
| `conversation.xlsx` | The wizard guidance banners come from it; I did not re-check it against the new onboarding flow | Open each wizard step and compare its banner with the file |

## What each authority must be able to do

Gold standard means each audience can verify the books without asking you. Each row gives the test that proves it, and what the code already has.

| Audience | Acceptance test | Already in code | To add |
| --- | --- | --- | --- |
| Chartered accountant and auditor | Reproduce every statement figure from ledger lines using only the tie-out report | Immutable ledger, hash chain, anchors, FY locks, cash-voucher report, read-only Auditor portal with `auditor_checks.py` | Tie-out report; schedule-format statements with comparatives and notes; signed and dated check results; sampling and exceptions lists; `Decimal` in all exports |
| Income-tax authorities | Every TDS row shows both the 1961 and 2025 section and the rate in force on its date | Effective-dated TDS rows with `section_2025`; cash receipt limit enforced; working paper labelled as such | Boundary-date tests (31 Mar and 1 Apr 2026); deposit and challan reconciliation; 44AB flag; depreciation; 26AS match |
| GST authorities | A GST officer can read the turnover worksheet and every exempt invoice names its authority | s.2(6) worksheet; resolution and opinion references required for fund exemption; GSTR-1 and 3B shaped summaries; RCM register | Authority printed on invoices; ITC apportionment; books-to-return reconciliation and mismatch report; invoice numbering, HSN/SAC and place-of-supply review |
| Government and registrar | An officer verifies a society's compliance from one certificate without logging in | Resolution validity enforced in the database; ratification tracking; statute catalogue with status, source and last-verified date | Compliance certificate and public verification page; rule-application register; evidence pack; verifier name and notification number on each catalogue row |
| All of them | A new tester cannot read another society's data or act as a role they lack | `check_callback_guards.py`; authorisation tests for resident and platform surfaces | Cross-tenant tests for every service function; negative tests for Auditor read-only and the other new roles; row-level security or equivalent |

I did not verify boundary-date coverage in `test_scenario_tds_compliance.py`, invoice numbering, or whether the catalogue has verifier and notification columns. Treat those cells as to be checked.

## Signing keys: one per society per purpose

Each society gets four independent signing keys, so a leak or rotation of one touches nothing else. A signed record can then be proved authentic without trusting the database owner.

| Key | Signs | Checked by | If rotated |
| --- | --- | --- | --- |
| `SIGNING_QR` | Gate-pass, vendor, security, patrol and receipt QR payloads | Scan endpoints | Old QR versions are revoked and reissued |
| `SIGNING_NOC` | Each issued NOC: a hash of the exact `body_text` with NOC id, flat and date | Public NOC verification page | Old NOCs keep verifying under their key version |
| `SIGNING_AGREEMENT` | Agreements, declared poll results (tally only, never who voted), resolutions and minutes | Public verification page | Old records keep verifying |
| `SIGNING_LEDGER` | Ledger anchors, FY-lock certificates, auditor check results, the per-FY compliance certificate | Auditor portal, verification page, `anchor_ledgers.py --verify` | Needs Secretary and Treasurer; a fresh anchor is signed straight away |

The design rules, which I chose from standard key-management practice:

1. **Two top keys, kept apart.** `SECRET_VAULT_KEY` sits in the host `.env` file, never in the database, and wraps every signing key. `SECRET_MASTER_KEY` sits in neither `.env` nor the database; you hold it, and it is the only key that can authorise a change of `SECRET_VAULT_KEY`. Each signing key is 32 random bytes made by the server and stored wrapped in a new `society_signing_keys` table (society, purpose, version, public key id, wrapped key, status, dates). The key id is random, not derived from the key.
2. **No human knows a signing key.** Today the admin's typed passphrase is the QR key itself. It becomes a step-up password, stored as a one-way hash like login passwords, used only to confirm sensitive actions such as QR reissue and key rotation. It signs nothing.
3. **Every signature says how it was made.** Each signed record stores purpose, key version, algorithm, signing time and the hash of the exact text signed.
4. **Purposes cannot be swapped.** Every signed message starts with a label such as `ApexEstateHub/v1/NOC/society:123`, so a QR tag can never pass as a NOC signature.
5. **Full-length signatures for documents.** NOC, agreement and ledger use the full 256-bit HMAC-SHA256. QR keeps its short tag because it must fit a code; the nonce, server-side lookup and scan rate limit protect it.
6. **Rotation keeps history.** A new version is created and the old one is retired but kept, so a 2027 agreement still verifies in 2032. A revoked key marks every signature made after the compromise date as untrusted.
7. **Keys never leave one module.** Decryption happens only inside a single signing service. Keys never appear in logs, exports, error text or the Auditor SQL pages. Key creation, rotation and revocation are written to `audit_events`.
8. **The platform anchor key retires.** `LEDGER_ANCHOR_SECRET` goes once `SIGNING_LEDGER` is live. The database holds only wrapped keys, and `SECRET_VAULT_KEY` stays in the host `.env` file, off the database host, so the property the old key gave is kept. Any anchor already signed with the old key is labelled legacy and still verifies.

**Custody of the two top keys.**

- `SECRET_VAULT_KEY` lives in the ApexWeave host `.env` file and nowhere else. It never goes in the repository, logs, chat, email or the database.
- `SECRET_MASTER_KEY` is generated offline and held by you, outside the host and outside every database. The app never holds it. It is used only on the day you change `SECRET_VAULT_KEY`.
- To change the vault key, you run a rotation tool on your own machine with the master key. It creates a new vault key, re-wraps every society's signing keys in one database transaction, and checks that a sample unwraps and verifies. You then put the new key in `.env` and restart, and the old key is destroyed after the check.
- The master key has teeth because of database permissions: the app's own login can add and read wrapped keys but cannot overwrite them. Only the rotation tool, using a separate login that is kept with the master key, can re-wrap.
- Recovery: the tool also writes a copy of the vault key sealed so that only the master key opens it. Keep that file with your sealed backups, outside `.env` and the database. If `.env` is lost, you recover the vault key from it.
- Change the vault key on suspected exposure, when a custodian changes, and once a year as a routine.
- Before the first live society, rehearse on a database copy: change the vault key, then recover it from the sealed file, then verify one anchor.

The limit to state plainly: anyone who controls the ApexWeave host and the database can sign as any society, because the vault key sits in the host `.env`. The master key stops the vault key being swapped or the wrapped keys being rewritten; it does not protect against someone who has taken over the running host. Independence for authorities comes from the paper certificate the Secretary and Treasurer sign and file, and from the CA holding copies of anchor heads. The database owner alone cannot forge a signature.

## Who signs what, and how large spending is approved

Today the code has one approver for ordinary spending, a co-signing engine for fund withdrawals that I found no screen for, and no signing record on documents. The plan builds on the office-bearer records the system already keeps in `committee_offices`.

| Record | Today (read in the code at `3cfe3f4`) | Planned signers | Sealed with |
| --- | --- | --- | --- |
| Ordinary expense | Accountant prepares, Treasurer or President approves; the code blocks anyone approving their own item; no amount ladder | Up to the ladder limit: accountant prepares, Secretary or Treasurer approves. Above it: see the rules below | `SIGNING_AGREEMENT` |
| Fund withdrawal | The database enforces a resolution reference and co-signatures above a set amount; I found no Python call to its signing or policy functions | Same engine, with Approve and Decline buttons | `SIGNING_AGREEMENT` |
| NOC | Admin issues it and the Secretary's signature image prints | Admin prepares, Secretary signs, the system confirms no dues from the ledger | `SIGNING_NOC` |
| Agreement | Admin creates it at setup; the text names an authorised signatory but no signing is recorded | President and Secretary sign for the society under a resolution; the platform operator signs for the platform | `SIGNING_AGREEMENT` |
| Resolution and minutes | Votes and majority are checked in the database; `minutes_signed_by` and its date exist but nothing sets them | Chair and Secretary sign; the system records the tally | `SIGNING_AGREEMENT` |
| Poll result | Admin declares it | Secretary or President declares it; the system seals the tally | `SIGNING_AGREEMENT` |
| Ledger anchor certificate | Code notes say the Secretary and Treasurer sign the printed copy and file it with the CA | Same, and each also signs in the app | `SIGNING_LEDGER` |

The planned signers are my defaults. Each society can change the signer list per document type, in the same way the fund policy already lists the offices that may sign.

### Spending ladder

1. **Up to ₹20,000** (your bye-law 49 default): the accountant prepares and the Secretary or Treasurer approves. The preparer can never approve their own item.
2. **Above ₹20,000:** the payment cannot post until a Managing Committee resolution is recorded and at least 2 different serving office-bearers have signed. The count is adjustable from 1 to 5 per society, and the database enforces it as it already does for fund withdrawals.
3. **Committee and General Body:** unlimited by default, as you set. A society may add a General Body threshold of its own; it is off by default.
4. **Safeguards:** a person holding two offices counts once; a signer must hold the office on that date; nobody signs a payment to their own flat; several payments to the same payee within a set period are added together, so splitting a bill does not avoid the limit; if the Treasurer seat is vacant a fallback rule applies, like the one already used for tax rates; spending taken before approval becomes a "to ratify" item (task 2.4).

### Approve and Decline

Each eligible office-bearer sees the pending item with its amount, payee, account and a link to the authorising resolution, and two buttons.

- **Approve** asks them to re-enter their own login password. The existing login lockout applies.
- **Decline** needs a written reason, stops the item and tells the preparer.
- Every action stores the user, their office, the time and a hash of the exact item. When the required signatures are in, the record is sealed with `SIGNING_AGREEMENT` and the payment is released for posting.

The limit: a password confirmation records who confirmed. It is not a legal e-signature, and whether it satisfies the bye-laws and the IT Act for resolutions is a question for your advocate **\[Verify\]**. Keep signed paper minutes and upload them.

### Office-bearer records

For every post (President, Vice-President, Secretary, Joint Secretary, Treasurer and each Working Committee member) the system keeps flat number, name, email, phone and a signature image.

- Pick the flat first. The owner's name, email and phone fill in from the enrolled record and stay editable.
- Flat number and name are drill-ins to the flat's profile and the person's profile, in the existing list and profile style.
- `committee_offices` has the holder's name, flat and login, but I saw no email, phone or signature columns, so those are new.
- The signature image prints on NOCs, agreements and minutes, in place of the single `secretary_sign` the letterhead uses today.
- The same block appears in the Setup Wizard's Administrator step, and again under Governance for later changes.

### Resolution drill-in for signing

Expenses, agreements, NOCs and minutes link to their authorising resolution. The resolution's profile has a Signatures panel: the required signers, who has signed, and a Sign button for the signed-in office-bearer, who confirms with their login password. After the last signature the record is sealed and edits are blocked.

## Phased plan

Your Phase 0 answers are recorded, so Phase 0 now waits only on opinions and sign-offs and building starts at Phase 1, which gives the most assurance per effort. I moved the Postgres 16 CI job to the start of Phase 1 so every later gate is proved by a test that runs on push.

&#91;embedded content: phased plan · 6 phases, 6 gates\]

Phase 5 is the only point after which "audit-grade" should appear in marketing.

### Phase 0: record the answers, collect the sources

Effort: S for the recording, then waiting on advisers.

| # | Task | Done when |
| --- | --- | --- |
| 0.1 | Write your six answers into `README.md` and `ER.md`, and update the statuses they now misstate (aggregate turnover, vote percentage) | Docs match the code at the new commit |
| 0.2 | List every provisional figure that needs an opinion: the 2/3 policy and 1/2 resolution majorities, the cash ceiling, the bye-law 46(d) depreciation-fund label, and the two rules the seed already marks "disputed" (bye-law 7 year basis, poll majority basis) | One list, each row with a rule key and the question for the advocate |
| 0.3 | Treasurer or Auditor obtains the advocate opinions, and the CA sign-offs on TDS and GST defaults | Each reference is held, ready to enter in Phase 2 |
| 0.4 | Retention: keep your 5-year default, configurable per society, and ask the CA whether any Act that applies needs longer **\[Verify\]** | Written answer from the CA |
| 0.5 | Read UP RERA notification 7098 of 13.07.2026 for the IFMS units | Provisional IFMS rates replaced or kept with a note |
| 0.6 | Check ApexWeave scheduled jobs: number allowed, shortest interval, time zone, run logs, whether jobs share the app's secret settings | One-page note feeding task 1.4 |

### Phase 1: foundations and correctness gaps

Build order: 1.1, then 1.2 and 1.3 together, then 1.4, then the rest in any order. Each task ends with a live-Postgres test that runs in CI.

| # | Task | Done when | Effort |
| --- | --- | --- | --- |
| 1.1 | CI: add a Postgres 16 job that runs every `*_live` suite, plus dependency, secret and static scans. Pin versions in `requirements.txt` and remove the duplicate `Flask-Cors` | A failing live test or a known-vulnerable package fails the push | S |
| 1.2 | Signing-key vault: `society_signing_keys` table (the app's database login can add and read wrapped keys but not overwrite them), one signing service, `SECRET_VAULT_KEY` read from the host `.env` file with a multi-key wrapper, a rotation tool that needs `SECRET_MASTER_KEY` and a separate database login, four keys created when a society is set up, QR moved onto `SIGNING_QR`, admin passphrase turned into a hashed step-up password | A key for one purpose cannot verify another purpose's signature; production refuses to start without a valid vault key; the app login cannot overwrite a wrapped key; a vault-key change without the master key is refused; QR scans still pass | M |
| 1.3 | `SIGNING_LEDGER` anchors: sign anchors and FY-lock certificates with the society's ledger key, record the key version, update `anchor_ledgers.py --verify`, retire `LEDGER_ANCHOR_SECRET` | An old anchor still verifies after a key rotation; a rewritten chain fails | M |
| 1.4 | Scheduled jobs on ApexWeave: anchors daily with verify, patrol hourly, ratification expiry daily. Jobs use the restricted database login, write to a job-run table, and alert the master on failure | A week of runs in the log; a forced failure raises an alert | M |
| 1.5 | Under-protest payment: a disputed item is held, the dispute is recorded with reason, date and resolution reference, and it is left out of interest and default status until decided. Correction is by reversal only | A disputed bill stops accruing interest; deciding it posts the right entries | M |
| 1.6 | Print the GST exemption authority on every exempt invoice and receipt: resolution reference, opinion reference and who gave it | Invoice shows the authority; an exempt invoice without it cannot be issued | S |
| 1.7 | Proportionate ITC reversal for exempt supplies, with a register and journal. The formula needs CA sign-off first | Worked example from the CA reproduces to the paisa | M |
| 1.8 | Sec 44AB flag with effective-dated thresholds **\[Verify\]**, shown on the dashboard and calendar | Flag turns on at the threshold in a test | S |
| 1.9 | Interest: print "Simple Interest - Bye-law 46(a) - Rate \<rate> via Resolution by GBM" with the real rate and resolution number; refuse to bill interest if no resolved rate exists; calculate simple interest only. An interest cap stays off until an advocate gives an opinion | Invoice text matches your wording; no rate means no interest | S |
| 1.10 | Managing Committee decisions: derive the vote percentage from the committee vote register instead of a typed value | Typed value is ignored, as for General Body decisions | S |
| 1.11 | Fix the NOC list and Security Salaries list column problems after confirming them in the app | Lists show one column each and no duplicates | S |
| 1.12 | Add the "Who signs what" table to README.md, with the ✅, 🟡 or ⬜ status marks the README already uses, and as guidance in the Setup Wizard's Administrator and Agreement steps. Update it as each signing task lands | README and wizard describe today's behaviour accurately | S |

### Phase 2: signed records and registers

This phase makes every record an authority relies on provable. Tasks 2.1, 2.2, 2.11 and 2.12 need Phase 1's key vault; task 2.5 needs 2.10 and 2.11.

| # | Task | Done when | Effort |
| --- | --- | --- | --- |
| 2.1 | Sign NOCs with `SIGNING_NOC`. The admin prepares, the Secretary signs with their own login password, and their signature image prints on the NOC. Add hash, signature, signer, key version and time to `nocs`; a public page recomputes the hash of the stored text and shows valid, superseded or revoked. The 30-day expiry stays | Editing a stored `body_text` makes verification fail | M |
| 2.2 | Sign with `SIGNING_AGREEMENT`: agreements (President and Secretary for the society, the platform operator for the platform), declared poll results (Secretary or President declares; tally only), resolutions when passed (with the hash of the vote-register summary) and minutes (Chair and Secretary). Each signer confirms with their own login password and is recorded. Block edits after signing with a database trigger | A tampered resolution or poll result fails verification; each record lists who signed and when; no voter identity appears in any signed poll record | M |
| 2.3 | Rule-application register: each posting linked to rule key, layer, decision, resolution number, advocate-opinion reference and effective dates, exportable | Auditor can trace any posting to its rule and authority | M |
| 2.4 | Ratification-of-irregular-items register with automatic reversal. Add a link from a posting to its authorising decision; on expiry or rejection post a reversal through `fn_post_reversal_journal`. Covers spend before approval, emergency spend, arrears write-off and interest waiver | An expired item reverses itself and shows in the register | L |
| 2.5 | Approval ladder as an optional per-society setting with a UI under Governance, built by extending the fund-withdrawal co-signing engine (`fund_spend_policy`, `fund_utilization_signoffs`) to all spending. Defaults: up to ₹20,000 the Secretary or Treasurer approves (bye-law 49, as you set); above it, a Managing Committee resolution plus at least 2 different serving office-bearers (adjustable 1 to 5); Committee and General Body unlimited, with an optional General Body threshold. Safeguards and the Approve and Decline flow are in the section above. Spend taken early becomes a "to ratify" item feeding task 2.4. Needs tasks 2.10 and 2.11 | A spend over the limit cannot post without the resolution and the required signatures, tested in the database; Decline stops the item; one person signing twice, or signing for their own flat, is refused | L |
| 2.6 | Per-FY compliance certificate: generated from the data, signed with `SIGNING_LEDGER`, with a public verification page showing only minimal fields. Lists each check with pass, fail or exception, its date, and every provisional item | An officer verifies a society's compliance from the certificate alone | M |
| 2.7 | Statute catalogue workflow: each row carries source URL, notification number, date verified, verifier and status. Only Treasurer or Auditor can mark a row verified, and only with an opinion reference. Unverified rows are labelled and never drive enforcement | No row shows "checked" without source text and an opinion | M |
| 2.8 | Weighted General Body tally per apartment from the register, and per-flat undivided interest filled after enrolment | Tally matches the register on a test meeting; flat shares sum to 100% | M |
| 2.9 | Refresh `conversation.xlsx` for the new onboarding flow | Guidance banners match the wizard steps | S |
| 2.10 | Office-bearer records: for every post (President, Vice-President, Secretary, Joint Secretary, Treasurer, Working Committee members) capture flat number, name, email, phone and signature image. Pick the flat first and the owner's name, email and phone fill in, editable. Flat number and name are drill-ins to the flat's profile and the person's profile. Shown in the Setup Wizard's Administrator step and under Governance; needed before 2.5 | Every serving post has all four fields or shows as incomplete; the signature image prints on NOCs, agreements and minutes | M |
| 2.11 | Approve and Decline buttons on pending expenses, fund withdrawals and documents for eligible office-bearers. The screen shows amount, payee, account and the authorising resolution. Approve asks for the signer's own login password (existing lockout applies); Decline needs a written reason. Each action stores user, office, time and the hash of the exact item; when the required signatures are in, the record is sealed with SIGNING\_AGREEMENT | A wrong password never approves; Decline stops the item; a sealed record fails verification if the item is edited | L |
| 2.12 | Resolution drill-in for signing: expenses, agreements, NOCs and minutes link to their authorising resolution. The resolution's profile has a Signatures panel with the required signers, who has signed, and a Sign button for the signed-in office-bearer (login password). After the last signature the record is sealed and edits are blocked | A document cannot be marked signed until every required signer has signed on its resolution | M |

### Phase 3: the auditor and CA experience

A CA must reproduce every figure from ledger lines without asking you.

| # | Task | Done when | Effort |
| --- | --- | --- | --- |
| 3.1 | Auditor portal: the eight checks (chain, balance, cash vouchers, reconciliation, receipt chains, tamper refusal, vote summary, instrument catalog) run in one click, and each result is dated and signed with `SIGNING_LEDGER` | Stored, signed result for each check | M |
| 3.2 | Tie-out report proving statements equal ledger equal source documents | Report passes on test data; a planted difference is caught | M |
| 3.3 | Schedule-format statements with comparatives and notes, a stated accrual policy, and the fund appropriation entry per `UP_AOA_FUNDS.md` section 8 | CA signs off the layout | L |
| 3.4 | Replace all 297 `float(` calls with `Decimal` and set the rounding policy: paisa for ledgers, rupee for TDS **\[Verify\]** | No `float(` in money paths; tests compare to the paisa | M |
| 3.5 | Depreciation by Act version, expense apportionment (assumption approved by resolution), brought-forward losses. 80P and 80AC stay a CA question | CA's worked example reproduces | L |
| 3.6 | TDS: challan and deposit reconciliation, quarterly statements and certificates in the CA's forms, a 2025-Act row for 192A, rent tested per month, inputs for 194-IA and 194Q, and boundary tests on 31 Mar and 1 Apr 2026 | Payable equals deposited; boundary tests pass | L |
| 3.7 | GST: books-to-return reconciliation with a mismatch report, invoice numbering, HSN/SAC, place of supply, e-invoice check, and a worksheet for the society's other all-India turnover under s.2(6) | Mismatch report is empty on clean data and flags a planted error | L |
| 3.8 | Source-document guard for `payables` and `receivables`; voucher sequence per society | A posting without a source document is refused | M |
| 3.9 | Form 26AS and AIS comparison from an imported file | Differences listed per deductor | M |

### Phase 4: platform hardening

| # | Task | Done when | Effort |
| --- | --- | --- | --- |
| 4.1 | Tenant isolation: cross-tenant tests for every service function, and row-level security or equivalent | No test reads or writes another society's rows | M |
| 4.2 | Role tests: Auditor read-only, accountant prepares and admin approves, proven by negative tests | Each forbidden action is refused by the server | M |
| 4.3 | Numbered migrations with rollback notes and a schema-version table, before any real society goes live | A migration applies and rolls back on a copy | M |
| 4.4 | Backups and restore drill; retention default 5 years, configurable per society, with a hold for disputes or audits | Restore from backup works; nothing is purged inside the retention period | M |
| 4.5 | Key drills: change `SECRET_VAULT_KEY` on a database copy using `SECRET_MASTER_KEY`, recover the vault key from the sealed file, revoke and re-issue one society's key, re-anchor. Write the incident runbook for a suspected key leak | Each drill passes and is recorded with date and who attended | M |
| 4.6 | DPDP: consent records, versioned privacy notice, access, correction and erasure workflow, grievance officer, breach procedure, read-access logging. Erasure pseudonymises personal fields and never edits the ledger **\[Verify current rule status\]** | A test erasure leaves the ledger chain valid | L |
| 4.7 | Accessibility and mobile checks of the four new portals | Checklist passed on a phone and a screen reader | S |

### Phase 5: independent assurance

| # | Task | Done when |
| --- | --- | --- |
| 5.1 | External CA review of the books engine and statements | Report received, every finding closed or accepted in writing |
| 5.2 | Advocate review of the rule packs and bye-law figures | Opinion references stored against each rule |
| 5.3 | Penetration test, with the signing-key vault and verification pages in scope | Findings closed; retest passes |
| 5.4 | Re-verify the Income-tax Act 2025 transition and the July 2026 IFMS amendment before each release | Dated check recorded per release |

Only after 5.1 to 5.3 should anyone say "audit-grade".

## Decisions, risks and sources

Your six Phase 0 answers (24 Oct) and where each lands:

| Question | Your answer | Lands in |
| --- | --- | --- |
| Wizard steps | Keep all steps | Labels only; task 0.1 |
| Cash-in-Hand leg | Deferred | Not planned; stays in the risks |
| Interest wording | "Simple Interest - Bye-law 46(a) - Rate \<rate> via Resolution by GBM" | Task 1.9 |
| Approval ladder | Optional with UI; default ₹20,000 (bye-law 49) for Secretary and Treasurer, unlimited for Committee and General Body | Task 2.5 |
| Scheduler and keys | ApexWeave has scheduled jobs; four keys per society; `SECRET_VAULT_KEY` in the host `.env` file; `SECRET_MASTER_KEY` with you, outside `.env` and the database | Tasks 1.2 to 1.4, 4.5. Dropped on 25 Oct: the news feature and the monthly bill job |
| Advisers and retention | Treasurer or Auditor files advocate opinions and CA sign-offs; 5-year default retention | Tasks 0.3, 0.4, 2.7, 4.4 |

Assumptions I made. Confirm or change any of them:

1. The compliance certificate and the auditor check results are signed with `SIGNING_LEDGER`.
2. `SIGNING_AGREEMENT` also covers minutes, as well as the agreements, polls and resolutions you named.
3. No interest cap check until an advocate gives an opinion.
4. Changing `SIGNING_LEDGER` needs both Secretary and Treasurer; the other society keys need the admin plus the step-up password.
5. The app's database login cannot overwrite a wrapped key; only the rotation tool, on a separate login kept with the master key, can re-wrap.
6. A sealed recovery file (the vault key, openable only with `SECRET_MASTER_KEY`) is kept outside `.env` and the database. I assumed your CTO also keeps a sealed backup of `SECRET_MASTER_KEY`, as he was to keep the old vault-key backup. Confirm who holds it.
7. The "Who signs what" signers are my defaults, and each society can change the signer list per document type.
8. The office-bearer block sits inside the Setup Wizard's Administrator step, not in a new step, because you asked to keep the steps as they are.
9. A signer's login password confirms their approval. That records who confirmed but is not a legal e-signature, so your advocate should confirm it, and signed paper minutes are kept as well.

Risks to keep visible:

- A "checked" flag without source text is worse than "provisional". Keep provisional figures labelled until an opinion is stored.
- Every change to posting logic must keep the ledger immutable; correction stays reversal-only.
- Role separation (accountant prepares, admin approves, auditor reads) has to be proven by tests, not by hiding menus.
- Losing `SECRET_MASTER_KEY` means the vault key can no longer be changed, and if `.env` is lost too, every society's signing keys are unrecoverable. The sealed backup, the recovery file and the drills in task 4.5 guard against that.
- A leaked `.env` plus a database dump exposes every signing key. Keep `.env` out of the repository, limit who can read host settings, and change the vault key on any suspicion.
- With the monthly bill job dropped, bills and interest are created only when someone opens the apartment list. Until then no bill exists and no interest has accrued, and the No Dues check and reports depend on that.
- The Cash-in-Hand leg stays deferred, so all-cash journals are checked against their source receipt or expense rather than by exact balance.
- The Income-tax Act 2025 transition and the July 2026 IFMS amendment are recent; re-verify before each release.

Sources: [ApexEstateHub at `3cfe3f4`](https://github.com/anuragexpertise/apexestatehub), files read: `README.md` (status tables), `ER.md` §9, `app/security/guards.py`, `app/services/regime_rules_admin.py`, `database/gst_export.py`, `app/dash_apps/callbacks/drilldown_callbacks.py`, `app/dash_apps/pages/setup_wizard.py`, `.github/workflows/tests.yml`, `requirements.txt`, and the earlier `GOLD_STANDARD_PLAN_v2.md`.
