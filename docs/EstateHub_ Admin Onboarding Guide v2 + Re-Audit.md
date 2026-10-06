# EstateHub: Society Admin Onboarding Guide (v2) and Re-Audit

*Re-audited against upstream commit `1ecf403` ("audit onboarding"), which landed after my first pass at `367156e`. Method: static read of the code and SQL, a pyflakes pass over every changed file, and the repo's own test suite (**674 passed, 94 skipped**). I did not run the app against a database or a browser. Items I could not confirm statically are marked **verify**.*

---

## Part 1: Before the admin starts (for Master / hosting)

1. **Database must be rebuilt from the current schema.** `1ecf403` adds `users.must_change_password` and `users.setup_submit_at` and widens `email` columns, but only by editing `CREATE TABLE`. `migrate.py` has no ALTERs for them, and its own docstring says the supported install is an empty schema (`reset_database.py`). On an older database, login, password change and wizard submit will fail on the missing columns.
2. **Set SMTP** (`SMTP_HOST`, `SMTP_PORT` 587, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`) and `SECRET_VAULT_KEY` (needed to store the signing secret).
3. **When creating the society:** Plan, **Validity Date in the future** (paid plans lock out login after validity + `PLAN_GRACE_DAYS`, default 7; `Free` never expires), admin email, and an initial password of **8+ characters**.
4. Give the credentials to the admin through a private channel. The admin is prompted to change the password at first login.

## Part 2: Admin: gather this first

The wizard has **no draft save**. Closing it logs you out and discards what is on screen (only Bye-Law clicks save instantly). Keep ready:

| Item | Step |
| --- | --- |
| Address, official email (up to 100 chars), phone, registration number, **State** | 1 |
| Logo, login background (optional), secretary signature scan, UPI payment QR | 1, 2, 11 |
| Secretary name, phone, email | 2 |
| A **SIGNING_SECRET** saved in a password manager | 2, 13 |
| GST registered? GSTIN. Deducts TDS? TAN | 4, 7, 8 |
| Maintenance basis (fixed per flat or per sq ft), due day, fund rates | 9 |
| Vendor pass prices | 10 |
| Last audited balance sheet (closing balances) and which FY | 12 |
| Your own login password (asked again on the last step) | 13 |

## Part 3: Log in and first screen

1. Pick your society, press **Continue**, then email + password (Password tab).
2. **Change-password prompt:** while the password is still the one Master set, an "Account Settings" box opens. It is a prompt, not a block; it returns every login until you change it. **If you change it, use the *new* password on the last wizard step.** **Verify:** how this box stacks against the full-screen wizard; if it is hidden, change the password after setup.
3. **Lockout:** 5 wrong passwords lock the account for 15 minutes. Since the update, wrong passwords typed on the wizard's last step **also count** toward this lockout.
4. **Expired plan:** you are refused at login. Ask Master to fix the Validity Date. (The refusal text tells you to ask your "society administrator"; that is you, so ignore it.)
5. **Forgot password** now works if SMTP is set: a token is emailed, and the "Enter New Password" box opens. If the server has no email configured, the message says so; ask Master to relay or reset it.

## Part 4: The 13 wizard steps

Steps 7 and 8 appear only if you answer Yes to GST / TDS in step 4. Next/Previous or the left list moves you around.

| # | Step | What to do | Watch out |
| --- | --- | --- | --- |
| 1 | **Society Details** | Address, State, Email, Phone, Registration No. Choose gate-pass enforcement and duty hours (8-hr x3 or 12-hr x2). Optional logo and login background. | **Address, Email, Phone and Registration are now enforced**: Next and Submit both refuse blanks or bad formats. **State is not enforced.** Pick it anyway: it assigns the legal rules (UP is fully supported). Name and PAN are read-only (Master owns them). |
| 2 | **Administrator** | Secretary details and signature; create and confirm the **SIGNING_SECRET**. | See box below. Next is blocked until the two entries match and pass. |
| 3 | **Instructions** | Skippable. Now shows the short Admin Quick Start (not the 170 KB README). | Nothing to enter. |
| 4 | **Society Compliance** | GST registered? (default No), Deducts TDS? (default Yes), fund bases, GST cadence, TDS-no-PAN action, export format. | Confirm with your CA. |
| 5 | **UP AOA Compliance** | Read-only Acts and Rules. | Follows the State chosen in step 1. |
| 6 | **Bye-Laws Adoption** | Adopt / vary / not adopt each Model Bye-Law. | **Saved instantly**, as *provisional*. Nothing takes effect until a passed resolution is recorded (Part 5). Clauses 7, 39, 49, 55 cannot be dropped by default. |
| 7 | **TAN & TDS Rates** | TAN (10 chars), review rates. | **TDS Effective Date now defaults to 1 April of the current FY.** Set it to the right FY start. |
| 8 | **GSTIN & GST Rate** | GSTIN (15 chars), CGST/SGST. |  |
| 9 | **Apartment Charges** | Maintenance amount **or** rate per sq ft, due day, sinking/repair fund, interest (max 1.75%). | Both maintenance fields default to 0; set one or bills are zero. |
| 10 | **Vendor Charges** | 1-day / 7-day / 1-month pass fees. |  |
| 11 | **Accounts** | Upload payment QR; set **Accounting Start Date**; review the seeded chart. | **The start date shows the day Master created your society, not 1 April** (see R5). Set it to the first day of the FY your opening balances belong to. **No primary bank account is set**; that is intentional now (see Part 5). |
| 12 | **Brought Forward** | FY start year (defaults to the current FY) and opening balances: Assets (Dr) left, Liabilities & Equity (Cr) right. | **Must balance (total Dr = total Cr)** or the whole submit is rejected and nothing is saved; the message shows both totals. Leaving all balances blank is allowed. Keep the year aligned with the start date in step 11. |
| 13 | **Agreement** | Type **I AGREE**, enter your login password and the SIGNING_SECRET, press **Submit Setup**. | One attempt per 5 seconds (now enforced across servers). Submit is **all-or-nothing**: a failure rolls back everything, including the chart of accounts. Fix the message and resubmit. |

> **SIGNING_SECRET: one rule, enforced identically on the live hint, the Next button and Submit** At least **8 characters** with an **uppercase**, a **lowercase**, a **digit** and a **special character** (anything that is not a letter or digit). It signs every QR gate pass. You need it again for **QR reissue**. I found no screen to view or change it later, and changing it would invalidate every printed QR. Store it before you finish. *"Cannot secure the signing secret"* means `SECRET_VAULT_KEY` is missing on the server: tell Master/hosting.

## Part 5: After you submit

1. **Change your password** (avatar menu, Account Settings) if you were not prompted.
2. **Set your real bank account as primary. Do this before recording any receipt or payment.** It is no longer defaulted to the seeded "SBI A/c - Society" (the chart seeds two generic bank accounts, SBI and ICICI). Until it is set, every non-cash posting fails with: *"No primary_bank_account_id configured... set Settings > Accounts > Primary Bank Account"*. Your payment QR must belong to this bank. **Verify:** I could not find a screen labelled "Primary Bank Account" (see R1). If you cannot find it, ask Master before going live.
3. **Enrol people** (Enrolled tab): **New** for one record, or **Bulk Enroll** (template, max 500 rows). Apartments first, then apartment users; fill `apartment_size` if you bill per sq ft. Passwords are 8+ characters everywhere now, and each person is prompted to change theirs on first login. **Both paths stop at your plan's apartment limit** (Free/9Apts = 9, 99Apts = 99, 999Apts = 999). Bulk reports the over-limit rows as failed.
4. **Governance** (Settings, Society governance): hold the General Body meeting, save the Bye-Law choice, then record the Meeting and the passed Resolution. Recording it **activates** the choice automatically (order matters).
5. Review the Settings tiles once: QR timing, patrol locations, QR reissue, charge rates, TDS rates, compliance settings.

## Part 6: Troubleshooting

| Symptom | Cause / action |
| --- | --- |
| Login or password change errors mentioning a missing column | Database not rebuilt from the new schema (Part 1). |
| "Plan has expired" at login | Validity Date in the past (beyond grace). Master edits the society. |
| "Account temporarily locked" | 5 wrong passwords. Wait 15 minutes. |
| Submit says Brought Forward does not balance | Fix Dr/Cr totals shown in the message. Nothing was saved. |
| "Society Details: ..." or "Address is required." | Go back to step 1, fill the field. |
| "SIGNING_SECRET still..." | Use all four character types and 8+ characters. |
| "Invalid Admin Password" | Use your *login* password (the new one, if you changed it), not the secret. |
| "Please wait before submitting again" | Retry after 5 seconds. |
| Reset email never arrives | SMTP not configured or failing; ask Master. |
| Bank receipt fails with "No primary_bank_account_id" | Step 2 of Part 5 not done. |

---

## Part 7: Audit status

### Previously reported, now verified fixed in `1ecf403`

| Was | Verdict |
| --- | --- |
| A3 Bulk Enroll skipped plan cap | **Fixed.** One shared `remaining_apartment_slots()` used by both paths; plan keys match the Master form. |
| A4 Weak/inconsistent passwords, no first-login change | **Fixed** (min 8 everywhere; prompt at login). Prompt is dismissible (R7). |
| A5 Three secret rules | **Fixed.** One `validate_signing_secret()` used in all three places. |
| A6 Required fields unenforced; blank address wipes data | **Fixed** (Next + Submit; SQL `NULLIF(BTRIM())`). Gaps in R8. |
| A9 No Dr = Cr check | **Fixed** in SQL, before any write; BF JSON keys match. |
| A10 State write swallowed | **Fixed.** State now written inside `fn_complete_society_setup`. |
| A11 Per-worker throttle; password tries not counted | **Fixed** (DB-backed throttle, shared lockout). Lockout clock is consistently UTC. |
| A12 Wizard dumped the 170 KB README | **Fixed.** Shows `docs/ADMIN_QUICKSTART.md`; README/docs aligned on resolution activation. |
| A13 Plan expiry not enforced | **Fixed** at login and router, with grace days. |
| A14 Setup not atomic | **Fixed.** Seed + setup share one transaction; `_conn()` rolls back on error. |
| A1 Reset token never delivered; reset box never opened | **Mostly fixed**: emailed, and the token-entry box now opens. Residuals R2, R3. |
| A7 Primary bank silently SBI; text contradicted code | **Text and SQL now agree** (not defaulted). Fix is only complete if admins can set it, see R1. |
| A8 Stale 2024 dates | **Partly fixed**: TDS date, BF year, SQL default now computed. Accounting Start Date still wrong, see R5. |

### Still open or new

| ID | Sev | Finding | Evidence | Suggested fix |
| --- | --- | --- | --- | --- |
| **R1** | High (verify) | **Admin may have no clear way to set the primary bank.** The error message and Quick Start say "Settings > Accounts > Primary Bank Account". I found no field or label with that name: `primary_bank_account_id` appears only in the society-save handler and a Master-hidden list; the form is schema-introspected. Until set, all non-cash receipts and payments raise an exception. Also unconfirmed: whether admin can add a real bank account under the Bank Accounts header. | `schema_introspect.py`, `renderers.py:2841`, `estatehub.sql:4007` | Add an explicit "Primary bank" picker (BkAc children only) to the admin Accounts screen, or to wizard step 11 (my earlier suggestion: ask the bank name and name the seeded account). Confirm in a browser first. |
| **R2** | Med | **Mailer weakens TLS.** `smtp.starttls()` with no context uses Python's unverified default (confirmed in 3.12: `ssl._create_stdlib_context()`), so the server certificate is not checked. If the server lacks STARTTLS, the code swallows the error and **logs in over plaintext**. Port 465 (implicit TLS) is unsupported and will hang to the 15 s timeout. | `mailer.py` | Use `ssl.create_default_context()`, fail closed when SMTP credentials are set, add `SMTP_SSL` for 465. |
| **R3** | Med | **Reset still leaks account existence and the token.** With SMTP unconfigured, a real account gets "...email is not configured... Ask Master to relay it" while an unknown one gets "If that email exists...". Delivery latency also differs. The plaintext token is logged at WARNING in every environment, and still returned to the caller. | `auth_service.request_password_reset` | One message for all outcomes; log the token only when explicitly enabled outside production; return `None` to callers. |
| **R4** | Med | **A2 unchanged:** every society name is listed to anonymous visitors. | `shell_callbacks.load_societies` | Per-society login URL or typed society code. |
| **R5** | Med | **Accounting Start Date still defaults to the creation date.** `create_society` stamps `calc_start_date = today`, and the wizard prefers the stored value. Admin sees e.g. 2026-10-06 while the BF year defaults to FY 2026, and the Quick Start claim "dates default to 1 April" is untrue for this field. | `society_service.create_society`; `setup_wizard.py` Accounts | Default to the FY start of the stored date. |
| **R6** | Med | **Schema change needs a rebuild** (Part 1), and `must_change_password DEFAULT TRUE` will prompt every existing account if migrated by ALTER. | `estatehub.sql`, `migrate.py` | Ship a real ALTER migration, or document the rebuild. |
| **R7** | Low | First-login prompt may collide with the full-screen wizard (verify). Login refusal text for an expired plan tells the *admin* to ask "your society administrator". | `account_callbacks.py`, `plan_guard.py` | Open the prompt after setup, or inside it; role-aware message at login. |
| **R8** | Low | Validation gaps: **State not required** (no legal regime if blank); clicking a step in the sidebar skips the Society Details check (Submit still enforces it); email is truncated to 100 characters without a message. | `setup_wizard_callbacks.py` | Require State; apply the gate to sidebar clicks too. |
| **R9** | Low | Pre-existing, unrelated to onboarding: `get_current_apartment_id` is used but never imported, so a resident editing their own record hits a `NameError`. | `drilldown_callbacks.py:2244` | Import it. |

**What I corrected from my first pass:** the seeded chart has **two** bank accounts (SBI and ICICI), not one; and the Accounting Start Date default in real use is the creation date, not 2024-04-01.

*Suggested order: R1 (confirm), R2/R3 (security), R5, R4, then the rest.*