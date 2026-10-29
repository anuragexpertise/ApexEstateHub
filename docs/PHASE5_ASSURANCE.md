# Phase 5: independent assurance (Gold-Standard Plan v4)

Status: **Provisional.** The record-keeping and the gates are built and tested. The assurance itself (a CA review, advocate
opinions, a penetration test) has not happened, because it can only be done by people outside this repository. Until it
has, the product's wording is the one `fn_assurance_label()` returns: *"Provisional: independent assurance incomplete"*.

**Do not say "audit-grade" until `python scripts/release_check.py status` exits 0.** It exits 0 only when 5.1, 5.2 and 5.3
are all closed and every rule still has an opinion.

**Limit.** The database checks that a reference, a document hash, a date and an independence declaration were stored. It
cannot judge whether an opinion or a report is sound. A person has to read them. A stored reference is evidence, not a verdict.

## What is built

| Task | Evidence the system holds | What the database refuses | Proved by |
|---|---|---|---|
| 5.1 External CA review | `assurance_engagements` (task 5.1: reviewer, credential, scope, commit reviewed, report ref and SHA-256) and `assurance_findings` | Closing without a report hash, without a declared independence, or with an open finding; accepting a finding without a written-acceptance reference, who accepted and when; editing a closed engagement | `test_5_1_*`, `test_closed_engagement_*` |
| 5.2 Advocate review of rule packs and bye-law figures | `rule_opinion_references`: one current opinion per platform rule (57) and per decision type (11), with adviser, reference, date, document SHA-256, conclusion and what it covers | Closing 5.2 while any rule has no covering opinion; an opinion for a rule that does not exist; editing or deleting an opinion. A `disputes` opinion is stored but does **not** cover the rule | `test_5_2_*` |
| 5.3 Penetration test | Same engagement tables (task 5.3) | Accepting a finding (pen-test findings must be fixed); closing without a passed retest dated on or after the report; closing while any non-info finding has not passed its retest | `test_5_3_*` |
| 5.4 Re-verify before each release | `release_verifications`: one dated record per release tag for the **Income-tax Act 2025 transition** and the **July 2026 IFMS amendment**, with the source actually read | Editing or deleting a record; a future date; `rules_updated` with no rule named | `test_5_4_*` |
| "Audit-grade" rule | `v_assurance_status`, `fn_audit_grade_claim_allowed()`, `fn_assurance_label()` | Nothing to refuse: it answers. It is judged live, so withdrawing an opinion or adding a rule with no opinion makes the claim false again | `test_audit_grade_claim_*` |

Every state change is written to `audit_events`. Code: `app/services/assurance.py` (master only). Schema: the "Phase 5"
block at the end of `database/estatehub.sql`.

## How to run each task

**5.1 and 5.3.** Create the engagement with its scope and the commit under review, record the reviewer and credential when
they start, store the report's SHA-256 (`assurance.sha256_file`) when it arrives, enter every finding under the reviewer's own
reference, close each with the fixing commit, then close the engagement. For 5.3 add the retest result and date to each
finding. For 5.1 a finding may instead be accepted in writing (Board resolution or letter reference).

**5.2.** `python scripts/release_check.py worklist` lists every rule and decision type with no opinion. Record one opinion per
row with `assurance.record_rule_opinion`. Advocate opinions for bye-law figures and statutory-source rules; CA opinions for
TDS, GST and income-tax rows. These rows stay provisional until the opinion is stored.

**5.4, before every release.** Read the Income-tax Act 2025 transition provisions and the July 2026 IFMS amendment (and UP
RERA notification 7098 of 13.07.2026, still unread per task 0.5) against the seeded rows. Record both items for the release
tag. Then `python scripts/release_check.py gate <tag>` must pass. A record with no adviser reference passes but prints
**PROVISIONAL**; get the CA's reference to clear that.

## Scope packs for the reviewers

Hand these over with the repository at a named commit. All legal and tax figures are **[Verify]** with the reviewer.

### 5.1 CA: books engine and statements
In scope: ledger posting and the hash chain, anchors and FY-lock certificates, tie-out report, auditor checks, financial
statements and exports, Decimal and rounding policy (paisa for ledgers, whole rupee for TDS), TDS and GST computation as built.
**Not yet built, so not assurable:** schedule-format statements and notes (3.3), depreciation, apportionment and brought-forward
losses (3.5), TDS challan reconciliation and quarterly statements (3.6), GST books-to-return reconciliation and ITC
reversal (3.7), Form 26AS/AIS matching (3.9). A review before those are finished will report them as gaps. Ask for that to be
stated in the report, not silently skipped.

### 5.2 Advocate: rule packs and bye-law figures
In scope: the 68 rows in `v_rule_assurance`. Open questions already named in the plan: committee quorum (more than half),
whether a login-password confirmation satisfies the bye-laws and the IT Act for resolutions, the GST authority wording,
44AB thresholds, the wizard's interest-resolution capture, the 269ST to s.186 mapping behind the cash receipt limit, sections 80P
and 80AC for an AOA, and the two rules the seed marks disputed.

### 5.3 Penetration test
In scope: the signing-key vault (`app/services/secret_vault.py`, `signing_service.py`, `scripts/rotate_vault_key.py`), the public
verification pages (`app/routes/verify.py`: NOC, agreement, resolution, compliance certificate), QR scan endpoints and their rate
limit, login, lockout and step-up password, tenant isolation, role separation (Auditor read-only, accountant prepares, admin
approves), and the endpoint inventory in `docs/authz_manifest.json`. Out of scope unless agreed: the hosting provider's platform.
State plainly to the tester the known design limit: anyone who controls the host and the database can sign as any society,
because the vault key sits in the host environment.
**Sequencing.** Tenant isolation (4.1) and role tests (4.2) are open in Plan v4. Testing before them produces findings you
already know about. Run 5.3 after Phase 4, and retest after fixes.

## Still needs people (nothing here can be done in code)

| Item | Who | Stays provisional until |
|---|---|---|
| Choose and engage the CA reviewer; obtain the report and credential | You, Treasurer or Auditor | Engagement closed with report hash |
| Obtain advocate and CA opinions for 68 rows | Treasurer or Auditor | `release_check.py worklist` is empty |
| Choose a penetration tester, agree scope, fix, retest | You | Retest passed and engagement closed |
| Read the Income-tax Act 2025 transition and IFMS amendment per release | Whoever releases | A release record with an adviser reference |
| Decision 1 (production host) | You | The scheduler and backup evidence the reviewers will ask for |
