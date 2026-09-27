# RWA Compliance (UP) — Master integration runbook

What this adds: a new **Master Portal → "RWA Compliance (UP)"** tab that tabulates
every Act, Rule, Bye-law and Notification governing RWAs / Apartment Owners'
Associations (AOAs) in Uttar Pradesh — a child table of the existing
`legal_regime_profiles` / `UP_AOA_2010` jurisdiction system, not a replacement
for it.

Delivered as `rwa_compliance_up.patch` (git diff against `origin/master`).
Files touched:

| File | Change |
|---|---|
| `database/estatehub.sql` | New `legal_instrument_catalog` table + index |
| `database/seed.py` | `LEGAL_INSTRUMENTS_UP_AOA` (10 researched rows) + `seed_legal_instrument_catalog()`, wired into `run_seed` |
| `app/dash_apps/app_shell.py` | New sidebar tab under Master: "RWA Compliance (UP)" |
| `app/dash_apps/callbacks/shell_callbacks.py` | Route `/dashboard/master-compliance-up` + breadcrumb label |
| `app/dash_apps/pages/portal_pages.py` | `_rwa_compliance_up_page()` — renders the table, or setup instructions if the table isn't there yet |

## Option A — apply the patch normally (recommended)

```bash
git checkout master && git pull
git apply --check rwa_compliance_up.patch   # dry run
git apply rwa_compliance_up.patch
python database/seed.py                     # populates legal_instrument_catalog
```

This is the same path every prior patch in this repo has used. Skip to
Option B only when you want the schema live **without** a code deploy —
e.g. pushing straight to the Aiven database from the browser.

## Option B — push live via Master Settings → "Integrate to DB"

This reuses the existing raw-SQL executor already in the codebase
(`app/dash_apps/callbacks/customize_callbacks.py::integrate_kpi_sql`), gated
to `role == "master"`. It runs whatever you paste through `db._execute(sql)`
in one transaction (commit-on-success, rollback-on-exception) — multiple
`;`-separated statements in one paste run fine, since `db._execute` passes
an empty params tuple and psycopg2 mogrifies client-side before sending a
single simple-protocol call.

1. Log in as `master` → sidebar → **Settings** (`/dashboard/master-settings`).
2. Stay on the **KPI Inspector** sub-tab (the Portal/Tab/KPI dropdowns above
   the SQL box are for KPI queries — you can leave them alone; they aren't
   read by the Integrate handler).
3. Paste into **"SQL Query (editable)"**:

   ```sql
   CREATE TABLE IF NOT EXISTS legal_instrument_catalog (
       id SERIAL PRIMARY KEY,
       regime_code VARCHAR(30) NOT NULL REFERENCES legal_regime_profiles (code) ON DELETE CASCADE,
       instrument_type VARCHAR(30) NOT NULL CHECK (
           instrument_type IN ('Act','Rules','Bye-laws','Notification','Central Act','Central Rules')
       ),
       title VARCHAR(300) NOT NULL,
       enactment_year INT,
       issuing_authority VARCHAR(150),
       applicability TEXT,
       key_provisions TEXT NOT NULL,
       source_reference TEXT NOT NULL,
       display_order INT NOT NULL DEFAULT 100,
       status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','draft')),
       last_verified_on DATE,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       CONSTRAINT uq_legal_instrument UNIQUE (regime_code, title, enactment_year)
   );
   CREATE INDEX IF NOT EXISTS idx_legal_instrument_catalog_regime ON legal_instrument_catalog (regime_code);
   ```

4. Click **Integrate to DB**. `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF
   NOT EXISTS` make this safe to re-run if you're not sure it already ran.
5. Seed the 10 researched rows — either:
   - run `python database/seed.py` once against this database (it now calls
     `seed_legal_instrument_catalog()`, idempotent on
     `(regime_code, title, enactment_year)`), **or**
   - copy the `INSERT INTO legal_instrument_catalog (...) VALUES (...)`
     statements built from `LEGAL_INSTRUMENTS_UP_AOA` in `database/seed.py`
     and paste them into the same SQL box, then **Integrate to DB** again.
6. Open the sidebar tab **RWA Compliance (UP)**
   (`/dashboard/master-compliance-up`) to confirm the table renders.
   Until step 3–4 have run, that page itself shows this same instruction
   block (it catches the "relation does not exist" error and displays the
   CREATE TABLE SQL directly) — so there's a built-in fallback if this file
   is ever out of sync with the code.

### Guardrails already in place (nothing to configure)

- `integrate_kpi_sql` requires `auth_data.get("role") == "master"` — any
  other role gets "Unauthorized: Master role required."
- It blocks `DELETE`/`DROP` unless the pasted SQL contains the literal
  comment `-- DELETE THIS SOCIETY` — irrelevant here since this workflow is
  additive only (`CREATE TABLE IF NOT EXISTS` / `INSERT`), but worth knowing
  before pasting anything else through this box in future.

## Keeping the table current

The Acts/Rules/Bye-laws themselves don't change often, but re-verify
periodically (the Allahabad HC has ruled on interpretation before — e.g.
*Olive Country Apartment Owners Association vs State of UP*, WP 12110/2013 —
and UP-RERA rules can be amended). To refresh:

1. Re-run the same web research this list came from (UP Apartment Act 2010 /
   Rules 2011 / Model Bye-laws text, UP-RERA notifications, Allahabad HC
   rulings referencing the Act).
2. Edit `LEGAL_INSTRUMENTS_UP_AOA` in `database/seed.py` — add new rows or
   update `status` to `'superseded'` on anything replaced (don't delete rows;
   superseded instruments are still useful history).
3. Re-run `python database/seed.py`, or push the specific `INSERT ... ON
   CONFLICT (regime_code, title, enactment_year) DO UPDATE SET ...` /
   `UPDATE legal_instrument_catalog SET ...` statement via Integrate to DB
   for a single-row fix without a full reseed.
4. Update `last_verified_on` on whichever rows you re-confirmed, so the tab's
   "last verified" line stays honest.

Extending to another state (e.g. Maharashtra, already `status='draft'` in
`legal_regime_profiles`) is the same shape: add rows to
`legal_instrument_catalog` with `regime_code = 'MH_COOP_1965'` — the table
and the Master Portal tab are regime-agnostic, only the seed data above is
UP-specific.
