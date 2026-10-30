# ApexEstateHub Gold-Standard Plan v5: Society Onboarding

Oct 30, 2026 · @Anurag Gupta

Your flow is right in shape. The code forces three changes: the President, Secretary and Treasurer must be seated before the Agreement is signed, the Treasurer must become a required signer, and nothing should post to the ledger until all four signatures are in.

**Is admin the Secretary?** No. In the code `admin` is a login role the Master creates with the society; the Secretary is an office held by a flat owner (`committee_offices`, which grants the `society_secretary` role). The admin holds no finance powers and signs nothing. Keep them separate: the admin is the society's setup custodian, and the three office-bearers are the people who bind the society. The same person may hold both, but the system treats them as two roles.

**Should the committee be seated before the Agreement?** Yes. A signer must hold a serving office on the signing date. But a seat needs an enrolled flat (`committee_offices.apartment_id` is required), so a small step comes first: enrol only the three office-bearers' flats, then seat them. Full enrolment follows the Agreement.

**Is onboarding complete when all have signed?** Yes. Today it is not: the wizard completes, posts opening balances and lets the society work, and the Agreement is created afterwards. v5 makes the sealed Agreement the activation event.

**Should the Agreement carry the Regime, Review and Brought Forward pages?** Yes, as signed annexes hashed into the sealed text. The three signers then sign the society's declared legal basis and opening financial position, not just a software licence.

## The onboarding journey

&#91;embedded content: onboarding flow · 7 stages, 1 signature gate\]

Stages 1 to 3 prepare; stage 4 is the only gate. Before it the society cannot bill, receive or post; after it, stages 5 to 7 run in order because each needs the one before (votes need enrolled owners' shares; adviser appointments need a resolution).

## What the repo does today

Read from commit `ee9579a` (`society_service.py`, `setup_wizard*.py`, `committee_service.py`, `document_signing.py`, `team_service.py`, `database/estatehub.sql`). Nothing was run against a database.

| Stage | Today | Gap against v5 |
| --- | --- | --- |
| 1 Register | `create_society_checked` takes name, address, email, phone, secretary name and phone, PAN, registration number, plan, validity and calc start, and creates the `admin` login. State and constitution are chosen later, in the wizard | No evidence upload (registration certificate); no `onboarding_state` column; plan is a fixed list (`Free` to `unlimited`) |
| 2 Founding committee | `fn_appoint_office_bearer` and `committee_service.appoint` seat all six offices and grant the role in one transaction. The wizard says office-bearers are not entered there, only the Secretary's contact details | A seat needs an enrolled flat, so there is no way to seat the three before enrolling; the wizard gives no path |
| 3 Setup Wizard | 15 steps from Instructions to Agreement. `fn_complete_society_setup` posts opening balances at once and sets `stepup_password_hash`, the only "setup complete" flag (`setup_guard.py`). Brought Forward is checked only for Dr = Cr | The society works before anyone has signed; no check that funds are backed by bank or deposits, or that arrears tie to flats |
| 4 Agreement | The wizard's last step asks the admin to type "I AGREE". The record is created after setup. Default signers are President, Secretary and platform, minimum 3; the Treasurer is not one. The text is a licence and terms with no annexes, and its signature block names only the Secretary. `database/AGREEMENT.md` names different parties | No gate on use; Treasurer missing; no annexes; two texts that disagree; no data-processing terms |
| 5 Enrollment | `bulk_enroll_callbacks.py` loads apartments, vendors, security, apartment users and assets; `team_service.py` creates accountant, supervisor, staff and auditor logins | No privacy notice or consent at first login; the apartments table has owner\_photo and id\_proof columns, with no rule on when to collect them |
| 6 Adoption | `society_bye_laws`, `meetings`, `resolutions`, weighted polls and the Adviser Decisions screen exist. Secretary and Treasurer approve an adviser's ruling with the adviser's PDF | I found no way to record resolutions passed before the platform; no link from an adviser appointment to its resolution except for auditors |
| 7 Adviser access | The `auditor` role holds `AUDIT_VIEW` and `REPORT_EXPORT` only. `auditor_appointments` records name, firm, membership number, term and resolution | No CA or advocate login role; no access end date on any login; no signed appointment record; exports not logged as processing |

## The Agreement

The Agreement is a two-party contract with four signatures: the society, acting through its President, Secretary and Treasurer, and the platform operator. It is sealed only when all four have signed, and the sealed text is the society's declaration of its legal basis and opening financial position as well as the licence.

**Signing order.** The three office-bearers sign first, each re-entering their own password, as today. The platform signs last, which accepts the society and activates it. The admin prepares and cannot sign. Any change to the text or an annex after a signature voids the signatures already given, because each signature binds the hash of the exact text (the existing `document_signing` behaviour).

| Part | Content | Source |
| --- | --- | --- |
| Parties and authority | Society name, registration number, address, PAN; the operator's legal name and address; the committee resolution that authorises the three signers | Master record; resolution link from C.4 |
| Licence and term | Plan, validity, fees, renewal | Master record |
| Society duties | Accuracy of entries, books kept by the society, its advisers' responsibilities | Existing text, advocate to review |
| Data protection | Society is the Data Fiduciary and the operator its Data Processor; security safeguards; named sub-processors; breach intimation to the society; return or deletion on exit, subject to retention holds | New (see the DPDP section) |
| Key custody | What the platform can and cannot do with the society's signing keys, including the stated limit that whoever controls the host and database can sign as any society | Plan v3, signing keys |
| Liability, indemnity, disputes | Existing clauses 2 and 4, plus governing law and forum | Advocate to review |
| Exit | Export of the society's books, deletion schedule, hold for audits and disputes | New |
| Execution | President, Secretary, Treasurer; operator's authorised signatory | `signer_policy` for `agreement` |

**Annexes, each rendered into the sealed text and also stored with its own SHA-256:**

| Annex | Declares | Checks before it can be signed |
| --- | --- | --- |
| A Regime | State, constitution, the legal regime that follows (`UP_AOA_2010` for a UP AOA), funds opted into, the Model Bye-Law clauses marked adopted, varied or not adopted, shown as provisional until a resolution passes | Regime assigned; every provisional rule listed with its adviser status |
| B Review | The wizard's Review page as a frozen snapshot: tax rates and TAN, GST, charges, accounts, office-bearers | No open problems on the Review page; TDS and GST rates marked pending the CA's confirmation |
| C Opening financial position | As-at date and financial year; every opening balance; fund-by-fund statement; arrears by flat | Debits equal credits; each fund is backed by bank or deposit balances; arrears by flat add up to the receivables control figure; bank balances agree to the statement on the as-at date; last audited statements attached with their hash |

**Activation.** When the fourth signature lands, one database function posts the opening journal from the sealed Annex C, sets the society to active, and takes the first ledger anchor. Until then the wizard stores a draft and posts nothing. A wrong opening figure found later is corrected by reversal, never by editing, as for every other entry.

**To confirm with your advocate \[Verify\]:** the operator's exact legal entity (the code says "EstateHub, LLC"; an LLC is not an Indian entity form), stamp duty on a software licence in UP, whether a password confirmation is enough for an electronic signature under the IT Act or whether paper counterparts or Aadhaar eSign must be added, and whether a Managing Committee resolution can authorise the contract or the General Body must.

## Founding committee, enrollment and adoption

**Founding committee (stage 2).** The admin enrols only the flats of the three office-bearers and seats them with their election evidence: the resolution reference, the minutes as an uploaded file with its hash, and the term dates. The seat and its role grant happen in one transaction, as they do today. One catch for the Treasurer's eye: bye-law 7 bars members in arrears from office **\[Verify\]**, and at this point no receivables exist, so the check passes trivially. Annex C therefore declares the three office-bearers' arrears, and activation re-runs the eligibility check against the opening balances.

**Enrollment (stage 5).** Runs only after activation, so every login is created under a sealed Agreement.

| Who | Enrolled by | Login role | Minimum data |
| --- | --- | --- | --- |
| Owners | Admin, bulk file or single | `apartment`, owner | Flat, name, mobile, email, undivided-interest share. ID proof and photo only where a rule needs them |
| Family and tenants | Admin, on the owner's request | `apartment`, family or tenant | Adults only, with name and contact; no profiles or photos for children |
| Vendors and guards | Admin | `vendor`, `security` | Name, contact, PAN or ID as the payment or duty requires |
| Accountant, supervisor, staff | Admin, which needs the `roles.manage` capability | `accountant`, `supervisor`, `staff` | Name, email; the Treasurer is told when an accountant login is made |
| Vice President, Joint Secretary, working members | Admin seats under a resolution | Committee roles | Same as for the three |

Every flat needs its undivided-interest share set before any weighted vote, because votes are weighted by it (bye-laws 2(e) and 8, as cited by the engine).

**Adoption (stage 6).** Four tracks, in this order:

1. **Old resolutions.** A register import for resolutions passed before the platform: date, number, subject, decision type, the minutes as a file with its hash. They carry no vote tally, so they cannot satisfy the engine's majority checks; they are stored as evidence marked `legacy`, and each one the society still relies on is confirmed by the adviser's ruling or re-passed under track 2.
2. **New resolutions by poll or meeting.** The existing engine: Model Bye-Law clauses adopted, varied or not adopted by the General Body (two-thirds of all votes as the engine reads it **\[Verify\]**), then society policy that may only tighten, then Board parameters. Polls are weighted and secret.
3. **Adviser rulings.** The Adviser Decisions screen already lets the Secretary and Treasurer enter a CA's, advocate's or auditor's ruling with reference and PDF; until both approve, the gated actions stay blocked. v5 adds a rule: the adviser must hold an active appointment (next section) before a ruling can be entered on their behalf.
4. **Special enrollment of advisers.** The next section.

| Item | Signed by | Mechanism |
| --- | --- | --- |
| Agreement | President, Secretary, Treasurer, then platform | `agreement`, with Treasurer added to the required list |
| Legacy resolution import | Chair (President) and Secretary | `resolution` |
| New resolution and minutes | Chair and Secretary | `resolution`, `minutes` (existing) |
| Poll result | Secretary or President | `poll` (existing) |
| Adviser ruling | Secretary and Treasurer, two different people | `society_decision_approvals` (existing) |
| Adviser appointment | President, Secretary, Treasurer | New `adviser_appointment` kind |

## CA, advocate and auditor

Advisers get read-only access and an export, appointed by a resolution and signed by the President, Secretary and Treasurer. They never write into the books: their rulings are entered by the Secretary and Treasurer on their behalf, with the adviser's reference number and PDF, which is what the Adviser Decisions screen already does.

**Two kinds of appointment.** A statutory auditor is appointed and paid by the General Body (bye-laws 51 and 52 in the catalogue, marked checked). A CA or advocate engaged for advice is a committee decision **\[Verify\]**. The appointment record carries the resolution either way, and the check that the right body passed it.

**One adviser role, three kinds.** Today `users.role` has `auditor` and nothing for a CA or advocate, and no login has an end date. v5 adds an adviser appointment record (kind, name, firm, membership number, scope, term start and end, resolution, independence declaration) and ends access on the term's last day without anyone having to remember.

| Kind | Can read | Can export | Cannot |
| --- | --- | --- | --- |
| Auditor | Ledger, vouchers, statements, tie-out, signed check results, anchors and FY locks | Financial data for the appointed years, flat numbers but not owner names | Post, approve, enrol, see ID proofs |
| CA | Everything the auditor sees, plus TDS, GST and income-tax working papers and the rate confirmation | The same, plus working papers | Confirm rates directly: the Treasurer records the CA's confirmation with its reference |
| Advocate | Bye-law register, resolutions, minutes, the Agreement and Annex A, adviser rulings | Documents only | See ledgers or member details |

**Controls on every adviser login:**

- A resolution is linked, and the appointment is signed by the President, Secretary and Treasurer (new `adviser_appointment` kind).
- Independence is declared in writing at appointment: no office, flat or financial interest in the society **\[Verify\]**.
- Access stops on the term end date or on a revoking resolution, whichever is first. Revocation takes effect at once and is logged.
- Every export is logged with who, what, how many rows and when, and watermarked with the adviser's name. Processing logs are kept for at least a year under the DPDP Rules **\[Verify\]**.
- The appointment letter carries a confidentiality undertaking, because the adviser handles personal data on the society's behalf.

## UP AOA regime and financial controls

The platform's rule layers already follow the UP hierarchy; onboarding must make sure each society enters it correctly. Status marks are the repo's own (checked, provisional, disputed), and no gazette text was read for this plan, so every legal reference stays **\[Verify\]**.

| Layer | Instrument | What onboarding does with it |
| --- | --- | --- |
| L0 | UP Apartment Act 2010, Rules 2011, Model Bye-Laws notified 16 Nov 2011 | Locked. A society in Uttar Pradesh is assigned `UP_AOA_2010` effective 16 Nov 2011; without that row every rule function returns nothing, so Annex A refuses to be signed without it |
| L0 | Central tax Acts (Income-tax Act 2025, CGST Act 2017) | Rates typed at setup stay pending until the CA confirms (`ca_rates_confirmed_at`); Annex B lists each as confirmed or pending |
| L1 | The society's bye-laws, each Model clause adopted, varied or not adopted | Provisional in Annex A. Becomes active only when a passed General Body resolution is recorded; clauses the Act backs cannot be dropped |
| L2, L3 | Society policy, Board decisions | Set after activation, under adoption track 2; tighten only |

Open question the repo already carries: a UP AOA is also a society registered under the Societies Registration Act, 1860 as amended in UP, and the Act sits on top. Ask the advocate how a registered society or co-operative should be treated, and capture the registration certificate at stage 1.

**Opening-position controls (Annex C), which are what a CA looks for first:**

| Control | Why it matters |
| --- | --- |
| Debits equal credits, as today | Necessary, not sufficient |
| Arrears and advances by flat, tied to the receivables control figure | A lump-sum opening balance cannot be collected, chased or defended against a member's dispute |
| Each restricted fund (sinking, repair, corpus, reserve) is backed by bank or deposit balances | Fund withdrawals need co-signatures; an unbacked fund balance would let them spend general money |
| Bank and cash balances agree to the statement and the cash count on the as-at date | The first reconciliation starts from a proven number |
| Year-to-date carry-ins for a society that starts mid-year: amounts paid per vendor, TDS deducted and deposited, GST turnover and tax paid | TDS thresholds, GST turnover and the s.44AB flag run on the financial year; starting at zero in October understates all three. I did not find these captured at setup, so confirm |
| Last audited statements attached with their SHA-256 | The opening balances then trace to a document an auditor accepted |
| The CA's review of Annex C: reference and PDF, or "none obtained" | "None obtained" is allowed but labels the opening position unreviewed on every statement until a CA reviews it |
| Bye-law 7 re-check of the three office-bearers against the opening arrears | Closes the gap described under the founding committee |

All amounts stay Decimal to the paisa through `database/money.py`, and a wrong opening figure found later is reversed and re-posted, never edited.

## DPDP Act

The README already says the product is not DPDP-compliant: tenant isolation, least-privilege access, password hashing and the secret ballot exist, while consent records, versioned notices, rights requests, retention, breach handling and a grievance contact do not. The society holds the personal data of owners, tenants, vendors and guards, so it is the Data Fiduciary and the platform its Data Processor, which needs a written contract: the Agreement's data-protection part. The platform is a fiduciary in its own right for the Master portal's users and billing contacts, with a separate notice.

**Timing.** Per a [summary of the DPDP Rules 2025](https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/), the Rules were notified on 14 Nov 2025. Rules 1, 2 and 17 to 21 took effect at once, consent-manager rules follow later, and the notice, safeguard, breach, erasure and rights rules take effect 18 months after publication, which I calculate as about May 2027. Confirm the dates and rule numbers against the Gazette **\[Verify\]**. Build now: the first societies onboard before that date, and retrofitting consent onto live data is harder than capturing it.

| Obligation | Where it lands in onboarding | What to build |
| --- | --- | --- |
| Notice: clear, separate, plain language, lists the data and purpose, gives contact details and how to withdraw consent and complain | Stage 5, first login of every person | A versioned privacy notice per society, shown before the password change completes; a `privacy_notices` table |
| Consent, per purpose, and withdrawal | Stage 5; also visitors at the gate | `consent_records`: person, purpose, notice version, time, withdrawn time. Society records the legitimate-use basis for statutory dues and gate safety **\[Verify\]** |
| Children's data needs a parent's or guardian's verifiable consent | Stage 5, family enrolment | Do not hold child profiles or photos; record adults only. If a rule later requires a child, a guardian-consent record first |
| Reasonable security safeguards, including for processors | Whole platform; Agreement | Restrict ID-proof and photo images by role; encryption at rest on the host; access and export logs; backup and recovery drill (Phase 4.4) |
| Breach intimation to the Board and affected people | Agreement; runbook | A breach register and runbook with the platform telling the society without delay; Secretary and the grievance officer named |
| Erasure when the purpose ends, unless law requires keeping; notice before deletion; logs kept at least a year | Exit; member leaves | Retention per record class, a hold for disputes and audits, and a 48-hour notice step. Erasure blanks the person's profile and never touches ledger lines, so the hash chain stays valid |
| Rights: access, correction, erasure, grievance, nominee | A request register in the admin portal | Each request has a due date and an outcome; the Secretary or a named grievance officer answers |
| Published contact for questions | Stage 1 to 2 | A grievance officer recorded at founding committee stage and shown on the login page and every notice |

Two links to the rest of the plan. The retention answer from Phase 0.4 (5 years by default, longer only if the CA names an Act) sets the purge rule. And every adviser export is a processing event, so it is logged and kept at least a year.

## Build plan

Thirteen tasks, numbered V5.n so they sit beside v4's ids. Effort is my rough judgement: S about a day, M a few days, L a week or more. The order is the dependency order; V5.8 to V5.12 can run in parallel once V5.7 lands.

| # | Task | Done when | Effort | Depends on |
| --- | --- | --- | --- | --- |
| V5.1 | Onboarding state: `societies.onboarding_state` (registered, committee seated, setup draft, active, suspended) with a database guard | A society that is not active cannot post a receipt, expense or journal, generate bills, or log in a resident; proven in a live test | M | none |
| V5.2 | Master form: registration certificate upload with hash; state and constitution chosen at creation so the regime is assigned at stage 1; PAN format check | A society cannot be registered without a registration number and certificate; the regime row exists after creation | S | V5.1 |
| V5.3 | Founding committee step before the wizard: enrol three flats, seat the three with evidence, name the grievance officer | Three seats with evidence hashes exist before the Agreement can be opened | M | V5.1 |
| V5.4 | Two-phase Setup Wizard: save a draft (`onboarding_declarations`), post nothing | Submitting the wizard posts no ledger entry; the draft stays editable until signing starts | L | V5.1 |
| V5.5 | Annexes A, B and C rendered and checked: regime assigned, Review clean, opening-position controls from the financial section | Each failing control blocks signing; a valid seeded set passes | L | V5.4 |
| V5.6 | Agreement v2: one text (retire the mismatch with `database/AGREEMENT.md`), parties, data-protection terms, Treasurer required, annexes hashed in | The sealed Agreement shows President, Secretary, Treasurer and platform; editing after a signature voids them | M | V5.5, advocate's wording |
| V5.7 | Activation function: opening journal from sealed Annex C, bye-law 7 re-check, first ledger anchor, state active, in one transaction | The fourth signature activates the society; a failed step rolls everything back | M | V5.1, V5.5, V5.6 |
| V5.8 | Legacy resolution register import with minutes hash, marked `legacy` | An imported resolution is visible as evidence and never satisfies a majority check | S | V5.7 |
| V5.9 | Adviser appointment record and `adviser` role (Auditor, CA, Advocate) with scope, term end and automatic expiry; new `adviser_appointment` signing kind; a ruling needs an active appointment | A login stops at its term end; an Advocate is refused every ledger read; refusals proven | L | V5.7 |
| V5.10 | Export log and masking: who, what, rows, time; adviser watermark; owner names masked for auditors | Every export has a log row; an auditor export holds no owner names | M | V5.9 |
| V5.11 | DPDP core: versioned notices, consent records, rights register, grievance officer, breach register, retention with holds, erasure that keeps the ledger chain valid. Replaces v4 task 4.6 | A test erasure leaves the chain valid; a rights request has a due date and an outcome | L | V5.7 |
| V5.12 | Enrollment minimisation: ID proof and photo optional and role-restricted; adults-only family records; notice and consent at first login | A new resident cannot reach the dashboard before accepting the notice | S | V5.11 |
| V5.13 | Live tests for every done-when above, replacing the weak existence checks in `test_plan_v4_*` | Each task's line is proven against a seeded Postgres 16 in CI | M | all |

Two v4 gates still apply before the first real society goes live: tenant isolation (4.1) and role refusal tests (4.2), because V5.9 and V5.10 build on them, and the scheduler switch-on (1.4), because the activation anchor and the daily anchors depend on it.

## Decisions needed

Ten decisions hold up work. Decisions 1 to 4 block the Agreement text itself.

| # | Decision | Why it matters | Blocks | Who |
| --- | --- | --- | --- | --- |
| 1 | The operator's exact legal entity, place of registration, address and authorised signatory. The code says "EstateHub, LLC"; the product is called ApexEstateHub | The Agreement's first line; an LLC is not an Indian entity form | V5.6 | You |
| 2 | May a Managing Committee resolution authorise the contract, or must the General Body | A contract signed on a defective authority can be disowned later | V5.6 | Advocate |
| 3 | Is a login-password confirmation enough as the signature, or must the Agreement add Aadhaar eSign, a digital signature or signed paper counterparts | The code records who confirmed; it is not a legal e-signature | V5.6 | Advocate |
| 4 | Stamp duty on the licence in UP | An unstamped agreement may be inadmissible in evidence | V5.6 | Advocate |
| 5 | The Treasurer is a required signer. What happens when the Treasurer seat is vacant at onboarding: wait, or allow a named substitute | A small society may not have all three seats filled on day one | V5.7 | You, advocate |
| 6 | Who appoints which adviser: General Body for the statutory auditor, committee for a CA or advocate; wording of the independence declaration | Sets the appointment check in V5.9 | V5.9 | Advocate |
| 7 | Consent or legitimate use as the basis for dues records, gate passes and visitor logs; retention beyond 5 years for any class | Sets what the notice says and when records are purged | V5.11 | Advocate, CA |
| 8 | How a registered society or co-operative is treated when the Apartment Act also applies (carried from the README) | Decides which regime a non-AOA society gets in Annex A | V5.2 | Advocate |
| 9 | Is the CA's review of Annex C required, or optional with an "unreviewed" label | A required review slows small societies; an optional one weakens the opening figures | V5.5 | You, CA |
| 10 | May the admin and the Secretary be the same person | Allowed today; v5 keeps two capacities on record and the admin never signs as admin | V5.3 | You |

Provisional figures and wording stay labelled provisional in the product until an adviser's reference is stored against each, as in v4.

**Basis.** The code at commit `ee9579a`, Plans v3 and v4 in the repository, and the README. Nothing was run against a database, and no statute or gazette text was read. The DPDP dates come from [one published summary of the Rules](https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/) and need checking against the notification. This plan is not legal or tax advice.
