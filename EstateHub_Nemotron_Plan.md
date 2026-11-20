# EstateHub: Implementation Plan for Nemotron 3.5 Super VL

Paste this whole file as the first message (or system prompt). Work through it in order.

---

## 0. Role and hard rules

You are modifying **EstateHub** (Python, Dash + Flask, JWT auth, PostgreSQL on **Aiven**, hosted on **Render.com**).
The code is in **alpha**. **No backward compatibility is required.**

- Delete replaced code, old callbacks, old columns and old templates. Do not keep shims, aliases, feature flags or "legacy" branches.
- You may change the DB schema freely (drop and recreate tables, rewrite seed data). Put schema changes in one migration/seed script, not scattered.
- Never invent a function, column, route, component id or import. If you have not seen it in the repo in this session, search for it first (`grep -rn`, `Glob`) and read the file.
- Make the smallest change that satisfies each requirement. Do not refactor unrelated code.
- Never print secrets (DB URL, JWT secret). Read them from environment variables only.

## 1. Working protocol (follow for EVERY slice)

1. **Locate**: grep for the feature's component ids, callback names and template strings. List the files and line ranges you will touch.
2. **Read** those files fully before editing. Quote the exact lines you will replace.
3. **Plan** in 3-6 bullets: what changes, which callbacks/IDs are affected, what gets deleted.
4. **Edit** one slice only. No edits to other slices until this one passes.
5. **Verify** (all must pass before moving on):
   - `python -m py_compile <changed files>`
   - `python -m pyflakes <changed files>` (or `ruff check`)
   - App imports: `python -c "import app"` (use the real entry module)
   - Dash callback sanity: every `Output`/`Input`/`State` id exists in some layout (or is in `suppress_callback_exceptions` with a layout that creates it); no two callbacks write the same `Output` unless `allow_duplicate=True` with `prevent_initial_call=True`.
   - Run the slice's acceptance tests in section 5 and paste the real output.
6. **Report** in this format, then stop and wait if anything failed:
   `Slice X: files changed / what deleted / commands run / result / open questions`

Do not claim a test passed unless you ran it and saw the output. If you cannot run something, say so.

## 2. Coding rules for this stack (avoid the usual errors)

**Uploads (dcc.Upload):**
- `contents` is a string `"data:<mime>;base64,<payload>"`. Always do:
  ```python
  header, b64 = contents.split(",", 1)
  raw = base64.b64decode(b64)          # bytes
  ```
- Excel: `openpyxl.load_workbook(io.BytesIO(raw), data_only=True)` or `pd.read_excel(io.BytesIO(raw), dtype=str)`. Never pass the base64 string or a `str` where bytes are needed.
- Hash with `hashlib.sha256(raw).hexdigest()` on the **bytes**.
- Check extension/MIME against an allow-list and enforce a max size before parsing.

**Database (Aiven Postgres):**
- Use a single connection helper that reads `DATABASE_URL`; Aiven requires `sslmode=require`.
- Parameterised queries only (`%s` placeholders). Never f-string SQL.
- Wrap multi-step writes in one transaction; commit once, rollback on any exception.
- Money: store as `NUMERIC(14,2)`; use `Decimal`, never `float`.

**Dash:**
- Use pattern-matching ids (`{"type":..., "index":...}`) for dynamic rows.
- Long actions use a modal with `dbc.Progress` (or `dcc.Interval` polling a job-status row); the callback that runs the work must not block longer than Render's request timeout, so run heavy work in a background thread/`background=True` callback and poll.
- Every callback that mutates data re-checks the JWT and the user's role server-side. Never trust the client.

**JWT/auth:** reuse the existing auth helper. Do not write a new one.

**Render:** no writes to local disk that must persist; store evidence files in DB or the existing object store, with the SHA-256 in the evidence register.

## 3. Requirements ledger (normalised from the owner's notes)

IDs are used in reports. "Master" means the platform master admin.

### A. Stage 2, "Seat the founding Committee"

- **A1** Remove the card/field "Minutes evidence (mandatory)". The registration certificate is already uploaded by the master.
- **A2** Move the buttons **"Election Results xlsx template"** and **"Fill forms from Election Results.xlsx"** into the card **"Seat all three from Election Results.xlsx"**.
- **A3** That card is the **first** card of the stage. It contains: the two buttons from A2, plus an upload control **"Election Results minutes (pdf/png/jpg)"**. Each uploaded file is saved to the evidence register with its SHA-256.
- **A4** Next, in this order: Seated President, Seated Secretary, Seated Treasurer, Grievance Officer (DPDP Act).
- **A5** Then the card **"CA / advocate review questionnaire (optional but recommended)"**.
- **A6** Remove the card **"Optional documents (non-blocking)"** from Stage 2 and move its content to the Setup Wizard:
  - "Cash-count certificate" and "Audited statements": **delete** (Brought Forward already has account/label template download + upload pairs with PDF).
  - "CA letter on TDS / GST rates": split into two items, **"TDS Rates"** and **"GST Rates"**, in the Setup Wizard.
- **A7** "Seat all three" shows a **modal with a progress bar** while it runs.

### B. Setup Wizard, "Brought Forward"

- **B1** Provide an xlsx **template** for upload with sections **Assets (Dr)** and **Liabilities & Equity (Cr)**. Show **every account where `account.has_bf = True`**.
- **B2** Fix the receivables upload error: `a bytes-like object is required, not 'str'` (see section 2, Uploads; almost certainly a base64 string or text passed to a bytes API, or `StringIO` vs `BytesIO`). Find the real line from the traceback or by reproducing it.
- **B3** If Sundry Debtors > 0, show a **warning symbol** when "Ledger-rows" are not filled. Ledger-rows are **mandatory** (warning must clear only when filled) for: Fixed Assets, Investments, Current Assets, Loans & Advances Given, Sundry Debtors (digital and cash, separately), and **Reserves and Funds as a separate group**.
- **B4** "Gifts Given" is on the **Dr** side.
- **B5** Merge: reading the **`Tally`** sheet of `brought_forward.xlsx` must fill the Wizard's Brought Forward grid directly (so the 18 accounts no longer have to be typed by hand).
- **B6** The **arrears-by-flat** template download is paired with its own upload (`pending_receivables.xlsx`). Keep them as a clear template/upload pair.
- **B7** Create a **simplified Brought Forward stage**: one screen, in this order: (1) set Financial year + As-on date, (2) upload `brought_forward.xlsx` + signed statements PDF, (3) grid auto-filled from Tally, (4) arrears upload, (5) four bank/cash statement balances + scans, (6) the Annex C check results panel.
- **B8** Move TDS Rates and GST Rates (from A6) into the Setup Wizard as their own small steps.

### Known behaviour to preserve (from the owner's own testing, now the spec)

- Template sheet `Account Balances` has exactly six columns and a locked account list. `as_on_date` is the text `YYYY-MM-DD` and must equal the wizard's As-on date; refuse upload if As-on date is unset.
- Labels are required for Deposits and for the Sundry Debtors accounts (FD number or flat number).
- Unknown flats are **not rejected**; the "Registered flats" sheet only normalises spellings (`C-101` becomes `C101`). Opening dues attach when the flat is enrolled.
- Annex C has seven controls, including: debits = credits; funds <= bank + cash + deposits; arrears-by-flat total = Sundry Debtors; each bank/cash balance = its statement balance.
- Upload alone does not fill the arrears table or the statement balances.
- The importer ignores the `Tally` sheet today; B5 changes that (Tally becomes an input).

## 4. Slice order (do not reorder)

1. **S0, Recon (no edits).** Find and list: Stage 2 layout file, Setup Wizard layout/callbacks, Brought Forward importer, Annex C checker, evidence register model, accounts model (`has_bf`), template-generation code. Output a table: requirement ID to file:line. Ask questions about anything ambiguous (section 6) **before** S1.
2. **S1, B2 bug.** Reproduce, fix, add a regression test with a real small xlsx built in the test.
3. **S2, Evidence upload + SHA (A3).** Shared helper `save_evidence(raw_bytes, filename, mime, kind) -> sha256`. Test: same file twice gives the same SHA, one register row policy as already implemented.
4. **S3, Stage 2 restructure (A1, A2, A4, A5, A6 removal part).** Pure layout/callback move; delete the removed card and its callbacks.
5. **S4, Seat-all modal + progress (A7).**
6. **S5, Brought Forward template + importer (B1, B4, B5).** Single template generator; importer reads `Account Balances` and `Tally` and fills the grid.
7. **S6, Ledger-row warnings (B3).**
8. **S7, Arrears pair (B6).**
9. **S8, Simplified Brought Forward stage (B7) and Wizard TDS/GST steps (A6, B8).**
10. **S9, Full regression:** run the end-to-end path with the owner's sample files (24 accounts, 6 uploaded, 18 from Tally; expect all seven Annex C controls to pass with SBI 200,000, ICICI 200,000, Deposits 100,000, Cash 100,000, totals 1,800,000 Dr = 1,800,000 Cr).

## 5. Acceptance tests (write them as pytest files, run them)

- **S1:** uploading a valid `pending_receivables.xlsx` returns parsed rows, no exception; uploading a non-xlsx returns a user-visible error, not a stack trace.
- **S2:** evidence row has correct SHA-256 of the bytes; unsupported extension rejected; oversize rejected.
- **S3:** the Stage 2 layout's top-level card order equals: Seat-all card, President, Secretary, Treasurer, Grievance Officer, CA questionnaire. No component id from removed cards remains in the repo (`grep` returns nothing).
- **S4:** the progress modal opens on click and closes on completion/error; failure leaves DB unchanged (transaction rolled back).
- **S5:** template contains every account with `has_bf=True` and none without; Gifts Given is Dr; importing the sample file fills 24 grid rows; debits equal credits.
- **S6:** with Sundry Debtors > 0 and empty ledger rows, a warning symbol is shown for each mandatory group (Fixed Assets, Investments, Current Assets, Loans & Advances Given, Sundry Debtors digital, Sundry Debtors cash, Reserves and Funds); it clears per group when filled.
- **S7:** arrears total must equal Sundry Debtors; unknown flats accepted.
- **S8:** the six steps appear in the stated order; skipping a required step blocks the final submit.
- **S9:** all seven Annex C controls pass on the sample data; lowering bank/cash/deposits by 1 makes the funds control fail.

## 6. Ask the owner before coding (if not answered by the repo)

1. Is "Grievance Officer" required to be seated, or optional like the CA questionnaire?
Ans 1. Yes, mandatory (DPDP Act requirement - need not be an owner)
2. Should TDS Rates and GST Rates be free-entry tables or an upload of the CA's letter (PDF) plus entered rates?
Ans 2. Leave them. TDS /GST rates are default displayed can be edited/ or uploaded. their CA letter (PDF) should be paired evidence
3. For Reserves and Funds: one ledger-row group or one per fund?
Ans 3. One per fund
4. Where should evidence files live on Render (DB blob, Aiven, or an object store)? 
Ans 4. Leave it now.may shift later to some cloud store
5. Is a seeded/dev reset (drop and recreate all tables) acceptable on the Aiven alpha database?
Ans 5. Yes, drop and recreate all tables

## 7. Stop conditions

Stop and report (do not push on) if: a test fails twice after fixes; you need to touch more than the planned files; a requirement conflicts with existing code; or you are unsure which of two similarly named components is live. Report what you found; do not guess.

## 8. Definition of done

All requirement IDs A1-A7 and B1-B8 are implemented; removed code is deleted (no dead callbacks, no unused imports); `pytest` passes; `pyflakes`/`ruff` is clean; the app starts; S9 passes; and the final report lists each requirement ID with the file and test that proves it.
