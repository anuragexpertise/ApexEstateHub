-- ============================================================================
-- migrations/001_block_coa_renumber.sql
--
-- B1a: Renumber accounts.id to depth-preserving block scheme.
--
-- NOT idempotent. Guard at top raises if run twice.
--
-- v4 changes:
--   1. Edit B — accounts.parent_account_id remapped before societies.*
--   2. trg_events_updated disabled during migration (schema bug workaround)
--   3. old_id_ref dropped at end of step 6, not step 9
--   4. ALTER SEQUENCE ... OWNED BY NONE before DROP COLUMN old_id_ref
--      (fixes "cannot drop column ... depends on sequence ownership")
--   5. step 9 split into 9a/9b/9c/9d: the block "headers" whose ids
--      collide with renumbered leaves are UPDATEd in place, not INSERTed.
-- ============================================================================

BEGIN;

-- ── 0. Guard ─────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name   = 'accounts'
           AND column_name  IN ('new_id', 'old_id_ref')
    ) THEN
        RAISE EXCEPTION
          'migrations/001_block_coa_renumber.sql has already been applied '
          'or was interrupted mid-run. Roll back / clean up before re-running.';
    END IF;
END $$;

-- ── 1. Lock ──────────────────────────────────────────────────────────────
LOCK TABLE accounts IN ACCESS EXCLUSIVE MODE;

-- ── 1b. Disable events trigger (schema bug workaround) ───────────────────
ALTER TABLE events DISABLE TRIGGER trg_events_updated;

-- ── 2. Map ───────────────────────────────────────────────────────────────
CREATE TEMP TABLE _coa_id_map (
    old_id INT PRIMARY KEY,
    new_id INT NOT NULL
) ON COMMIT DROP;

INSERT INTO _coa_id_map (old_id, new_id) VALUES
    (1,     1),
    (2,     3100),
    (21,    4100), (211,   4110), (2111,  4111), (21111, 4112),
    (21112, 4113), (21113, 4115), (2112,  4114), (212,   4120), (213,   4130),
    (22,    3240),
    (23,    5100),
    (231,   5110), (232,   5120), (233,   5130), (234,   5140), (235,   5150),
    (236,   5160), (237,   5170), (238,   5180), (239,   5190), (2310,  51100),
    (2311,  4210), (2312,  51110), (2313,  51120), (2314,  51130),
    (2315,  51140), (2316,  51150), (2317,  4220), (2318,  4230),
    (2319,  4240), (23191, 4241), (23192, 4242),
    (2320,  51160), (2321,  51170), (2322,  51180), (2323,  51190),
    (24,    5200), (25,    5210), (26,    3250), (27,    3260),
    (28,    5220), (29,    2290),
    (3,     2110), (4,     2200),
    (41,    2210), (42,    2220), (43,    2230), (44,    2231), (45,    2232),
    (5,     1110), (6,     1100), (61,    1120), (62,    1200), (63,    1300),
    (631,   1310), (6311,  1311), (6312,  1312), (632,   1320), (633,   1330),
    (634,   1340), (64,    1130), (65,    1140), (66,    1150), (67,    1160),
    (7,     1400), (8,     1500), (81,    1510), (82,    1520),
    (9,     2240),
    (101,   3210), (102,   3220), (103,   3230)
;

-- ── 3. Sanity ────────────────────────────────────────────────────────────
DO $$
DECLARE v_orphans TEXT;
BEGIN
    SELECT STRING_AGG(a.id::TEXT || ' (' || a.name || ')', ', ' ORDER BY a.id)
      INTO v_orphans
      FROM accounts a
     WHERE NOT EXISTS (SELECT 1 FROM _coa_id_map m WHERE m.old_id = a.id);

    IF v_orphans IS NOT NULL THEN
        RAISE EXCEPTION 'Unmapped account ids: %', v_orphans;
    END IF;
END $$;

-- ── 4. Add new_id, populate ──────────────────────────────────────────────
ALTER TABLE accounts ADD COLUMN new_id INT;

UPDATE accounts a SET new_id = m.new_id
  FROM _coa_id_map m WHERE a.id = m.old_id;

DO $$
DECLARE v_missing INT;
BEGIN
    SELECT COUNT(*) INTO v_missing FROM accounts WHERE new_id IS NULL;
    IF v_missing > 0 THEN
        RAISE EXCEPTION 'accounts.new_id NULL on % row(s).', v_missing;
    END IF;
END $$;

-- ── 5. Drop every FK referencing accounts(society_id, id) ────────────────
ALTER TABLE societies                 DROP CONSTRAINT IF EXISTS fk_primary_bank_account;
ALTER TABLE assets                    DROP CONSTRAINT IF EXISTS assets_acc_id_fkey;
ALTER TABLE assets                    DROP CONSTRAINT IF EXISTS assets_sale_acc_id_fkey;
ALTER TABLE assets                    DROP CONSTRAINT IF EXISTS assets_society_id_acc_id_fkey;
ALTER TABLE assets                    DROP CONSTRAINT IF EXISTS assets_society_id_sale_acc_id_fkey;
ALTER TABLE events                    DROP CONSTRAINT IF EXISTS events_account_id_fkey;
ALTER TABLE events                    DROP CONSTRAINT IF EXISTS events_society_id_account_id_fkey;
ALTER TABLE receivables               DROP CONSTRAINT IF EXISTS receivables_acc_id_fkey;
ALTER TABLE receivables               DROP CONSTRAINT IF EXISTS receivables_interest_acc_id_fkey;
ALTER TABLE receivables               DROP CONSTRAINT IF EXISTS receivables_society_id_acc_id_fkey;
ALTER TABLE receivables               DROP CONSTRAINT IF EXISTS receivables_society_id_interest_acc_id_fkey;
ALTER TABLE payables                  DROP CONSTRAINT IF EXISTS payables_acc_id_fkey;
ALTER TABLE payables                  DROP CONSTRAINT IF EXISTS payables_society_id_acc_id_fkey;
ALTER TABLE expenses                  DROP CONSTRAINT IF EXISTS expenses_acc_id_fkey;
ALTER TABLE expenses                  DROP CONSTRAINT IF EXISTS expenses_society_id_acc_id_fkey;
ALTER TABLE receipts                  DROP CONSTRAINT IF EXISTS receipts_acc_id_fkey;
ALTER TABLE receipts                  DROP CONSTRAINT IF EXISTS receipts_society_id_acc_id_fkey;
ALTER TABLE transactions              DROP CONSTRAINT IF EXISTS transactions_acc_id_fkey;
ALTER TABLE transactions              DROP CONSTRAINT IF EXISTS transactions_society_id_acc_id_fkey;
ALTER TABLE brought_forward           DROP CONSTRAINT IF EXISTS brought_forward_acc_id_fkey;
ALTER TABLE brought_forward           DROP CONSTRAINT IF EXISTS brought_forward_society_id_acc_id_fkey;
ALTER TABLE account_statutory_mappings DROP CONSTRAINT IF EXISTS account_statutory_mappings_society_id_account_id_fkey;
ALTER TABLE accounts                  DROP CONSTRAINT IF EXISTS fk_account_parent;

-- ── 6. Swap id → new_id; detach sequence; drop old_id_ref ────────────────
ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_pkey;

ALTER SEQUENCE IF EXISTS accounts_id_seq OWNED BY NONE;

ALTER TABLE accounts ALTER COLUMN id DROP DEFAULT;

ALTER TABLE accounts RENAME COLUMN id      TO old_id_ref;
ALTER TABLE accounts RENAME COLUMN new_id  TO id;

ALTER TABLE accounts ADD CONSTRAINT accounts_pkey PRIMARY KEY (society_id, id);

CREATE SEQUENCE IF NOT EXISTS accounts_id_seq;
ALTER TABLE accounts ALTER COLUMN id SET DEFAULT NEXTVAL('accounts_id_seq');

ALTER TABLE accounts DROP COLUMN old_id_ref;

-- ── 7. FIRST: remap accounts.parent_account_id ───────────────────────────
UPDATE accounts c SET parent_account_id = m.new_id
  FROM _coa_id_map m WHERE c.parent_account_id = m.old_id;

-- ── 8. THEN: remap every child-table FK column ───────────────────────────
UPDATE societies s        SET primary_bank_account_id = m.new_id FROM _coa_id_map m WHERE s.primary_bank_account_id = m.old_id;
UPDATE assets a           SET acc_id                  = m.new_id FROM _coa_id_map m WHERE a.acc_id                  = m.old_id;
UPDATE assets a           SET sale_acc_id             = m.new_id FROM _coa_id_map m WHERE a.sale_acc_id             = m.old_id;
UPDATE events e           SET account_id              = m.new_id FROM _coa_id_map m WHERE e.account_id              = m.old_id;
UPDATE receivables r      SET acc_id                  = m.new_id FROM _coa_id_map m WHERE r.acc_id                  = m.old_id;
UPDATE receivables r      SET interest_acc_id         = m.new_id FROM _coa_id_map m WHERE r.interest_acc_id         = m.old_id;
UPDATE payables p         SET acc_id                  = m.new_id FROM _coa_id_map m WHERE p.acc_id                  = m.old_id;
UPDATE expenses e         SET acc_id                  = m.new_id FROM _coa_id_map m WHERE e.acc_id                  = m.old_id;
UPDATE receipts r         SET acc_id                  = m.new_id FROM _coa_id_map m WHERE r.acc_id                  = m.old_id;
UPDATE transactions t     SET acc_id                  = m.new_id FROM _coa_id_map m WHERE t.acc_id                  = m.old_id;
UPDATE brought_forward bf SET acc_id                  = m.new_id FROM _coa_id_map m WHERE bf.acc_id                 = m.old_id;
UPDATE account_statutory_mappings asm SET account_id  = m.new_id FROM _coa_id_map m WHERE asm.account_id            = m.old_id;

-- ════════════════════════════════════════════════════════════════════════════
-- ── 9. Block header rows ─────────────────────────────────────────────────
--    Split into four sub-steps because some block "headers" ids collide
--    with the new ids that renumbered LEAVES now occupy:
--        id 1100 = old Movable Assets (id 6)   → now becomes Fixed Assets
--        id 1200 = old Investments (id 62)     → already Investments
--        id 1300 = old Current Assets (id 63)  → already Current Assets
--        id 1310 = old Bank Accounts (id 631)  → already Bank Accounts
--        id 1400 = old Loans Given (id 7)      → already Loans Given
--        id 1500 = old Sundry Debtors (id 8)   → already Sundry Debtors
--        id 2200 = old Current Liabilities (4) → already Current Liabilities
--        id 3100 = old Capital Account (id 2)  → already Capital Account
--        id 4100 = old Income Other Source(21) → already Income Other Source
--        id 4110 = old Interest Income (211)   → already Interest Income
--        id 4111 = old Bank Interest (2111)    → already Bank Interest
--        id 5100 = old InExp A/c (id 23)       → already InExp A/c
--    Those get UPDATEd in place (9b). Only truly-new headers (9a + 9c)
--    get INSERTed.
-- ════════════════════════════════════════════════════════════════════════════

-- 9a. Top-level block headers (no collision — ids 1000/2000/3000/4000/5000
--     were never used by the old scheme)
INSERT INTO accounts (society_id, id, name, tab_name, header, parent_account_id, drcr_account, has_bf, depreciation_percent, is_depreciable, mutuality_nature, tds_section)
SELECT s.id, 1000, 'Assets',                'As',    'Assets',             1, 'Dr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 2000, 'Liabilities',           'Lb',    'Liabilities',        1, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 3000, 'Equity / Reserves & Funds', 'Eq', 'Equity',           1, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 4000, 'Income',                'Inc',   'Income',             1, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 5000, 'Expenses',              'Exp',   'Expenses',           1, 'Dr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
;

-- 9b. Existing accounts whose new id IS a header — re-purpose them in place
--     (rename, retab, set header text, keep id). Only rename where the
--     name changes.
UPDATE accounts SET name = 'Fixed Assets',     tab_name = 'FA',    header = 'Fixed Assets'    WHERE id = 1100 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Investments',      tab_name = 'Inv',   header = 'Investments'     WHERE id = 1200 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Current Assets',   tab_name = 'CA',    header = 'Current Assets'  WHERE id = 1300 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Bank Accounts',    tab_name = 'BkAc',  header = 'Bank Accounts'   WHERE id = 1310 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Loans & Advances Given', tab_name = 'LAG', header = 'Loans & Advances Given' WHERE id = 1400 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Sundry Debtors',   tab_name = 'SDr',   header = 'Sundry Debtors'  WHERE id = 1500 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Current Liabilities', tab_name = 'CL', header = 'Current Liabilities' WHERE id = 2200 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Capital Account',  tab_name = 'CapAc', header = 'Capital Account' WHERE id = 3100 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Income Other Source', tab_name = 'IncOther', header = 'Income other source' WHERE id = 4100 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Interest Income',  tab_name = 'IncInt', header = 'Interest Income' WHERE id = 4110 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Bank Interest',    tab_name = 'IntBK', header = 'Bank Interest'   WHERE id = 4111 AND society_id IN (SELECT id FROM societies);
UPDATE accounts SET name = 'Income Expenditure A/c', tab_name = 'InExp', header = 'Income Expenditure Account' WHERE id = 5100 AND society_id IN (SELECT id FROM societies);

-- 9c. Truly-new headers whose ids were NOT used by any old account
INSERT INTO accounts (society_id, id, name, tab_name, header, parent_account_id, drcr_account, has_bf, depreciation_percent, is_depreciable, mutuality_nature, tds_section)
SELECT s.id, 2100, 'Non-Current Liabilities', 'NCL',    'Non-Current Liabilities', 2000, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 3200, 'Reserves & Funds',        'Res',    'Reserves & Funds',        3000, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
UNION ALL
SELECT s.id, 4200, 'Member Contributions',    'MemCon', 'Member Contributions',    4000, 'Cr', FALSE, 100.00, FALSE, 'mutual', NULL FROM societies s
;

-- 9d. Re-parent the renumbered leaves under the headers.
UPDATE accounts SET parent_account_id = 1000 WHERE id IN (1100,1110,1120,1130,1140,1150,1160,1180,1200,1300,1400,1500);
UPDATE accounts SET parent_account_id = 1100 WHERE id IN (1110,1120,1130,1140,1150,1160,1180);
UPDATE accounts SET parent_account_id = 1300 WHERE id IN (1310,1320,1330,1340);
UPDATE accounts SET parent_account_id = 1310 WHERE id IN (1311,1312);
UPDATE accounts SET parent_account_id = 2000 WHERE id IN (2100,2200);
UPDATE accounts SET parent_account_id = 2200 WHERE id = 2240;
UPDATE accounts SET parent_account_id = 2100 WHERE id = 2110;
UPDATE accounts SET parent_account_id = 2200 WHERE id IN (2210,2220,2230,2231,2232,2290);
UPDATE accounts SET parent_account_id = 3000 WHERE id IN (3100,3200,3240,3250,3260);
UPDATE accounts SET parent_account_id = 3200 WHERE id IN (3210,3220,3230);
UPDATE accounts SET parent_account_id = 4000 WHERE id IN (4100,4200);
UPDATE accounts SET parent_account_id = 4100 WHERE id IN (4110,4120,4130);
UPDATE accounts SET parent_account_id = 4110 WHERE id IN (4111,4112,4113,4114,4115);
UPDATE accounts SET parent_account_id = 4200 WHERE id IN (4210,4220,4230,4240);
UPDATE accounts SET parent_account_id = 4240 WHERE id IN (4241,4242);
UPDATE accounts SET parent_account_id = 5000 WHERE id IN (5100,5200,5210,5220);
UPDATE accounts SET parent_account_id = 5100 WHERE id IN (
    5110,5120,5130,5140,5150,5160,5170,5180,5190,
    51100,51110,51120,51130,51140,51150,51160,51170,51180,51190
);

-- ── 10. Recreate FKs ─────────────────────────────────────────────────────
ALTER TABLE accounts
    ADD CONSTRAINT fk_account_parent
        FOREIGN KEY (society_id, parent_account_id)
        REFERENCES accounts (society_id, id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE societies
    ADD CONSTRAINT fk_primary_bank_account
        FOREIGN KEY (id, primary_bank_account_id)
        REFERENCES accounts (society_id, id);

ALTER TABLE assets ADD CONSTRAINT assets_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE assets ADD CONSTRAINT assets_society_id_sale_acc_id_fkey
    FOREIGN KEY (society_id, sale_acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE events ADD CONSTRAINT events_society_id_account_id_fkey
    FOREIGN KEY (society_id, account_id) REFERENCES accounts (society_id, id);
ALTER TABLE receivables ADD CONSTRAINT receivables_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE receivables ADD CONSTRAINT receivables_society_id_interest_acc_id_fkey
    FOREIGN KEY (society_id, interest_acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE payables ADD CONSTRAINT payables_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE expenses ADD CONSTRAINT expenses_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE receipts ADD CONSTRAINT receipts_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE transactions ADD CONSTRAINT transactions_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id);
ALTER TABLE brought_forward ADD CONSTRAINT brought_forward_society_id_acc_id_fkey
    FOREIGN KEY (society_id, acc_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE;
ALTER TABLE account_statutory_mappings ADD CONSTRAINT account_statutory_mappings_society_id_account_id_fkey
    FOREIGN KEY (society_id, account_id) REFERENCES accounts (society_id, id) ON DELETE CASCADE;

-- ── 11. Reset sequence ───────────────────────────────────────────────────
SELECT setval(
    'accounts_id_seq',
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM accounts), 1),
    TRUE
);

-- ── 12. Assertions ───────────────────────────────────────────────────────
DO $$
DECLARE
    v_orphan_fks INT := 0;
    v_dup_ids    INT := 0;
    v_bad_parent INT := 0;
BEGIN
    SELECT COUNT(*) INTO v_orphan_fks FROM (
        SELECT 1 FROM assets a WHERE a.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=a.society_id AND x.id=a.acc_id)
        UNION ALL SELECT 1 FROM assets a WHERE a.sale_acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=a.society_id AND x.id=a.sale_acc_id)
        UNION ALL SELECT 1 FROM events e WHERE e.account_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=e.society_id AND x.id=e.account_id)
        UNION ALL SELECT 1 FROM receivables r WHERE r.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=r.society_id AND x.id=r.acc_id)
        UNION ALL SELECT 1 FROM receivables r WHERE r.interest_acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=r.society_id AND x.id=r.interest_acc_id)
        UNION ALL SELECT 1 FROM payables p WHERE p.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=p.society_id AND x.id=p.acc_id)
        UNION ALL SELECT 1 FROM expenses e WHERE e.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=e.society_id AND x.id=e.acc_id)
        UNION ALL SELECT 1 FROM receipts r WHERE r.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=r.society_id AND x.id=r.acc_id)
        UNION ALL SELECT 1 FROM transactions t WHERE t.acc_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.society_id=t.society_id AND x.id=t.acc_id)
        UNION ALL SELECT 1 FROM brought_forward bf WHERE NOT EXISTS
          (SELECT 1 FROM accounts x WHERE x.society_id=bf.society_id AND x.id=bf.acc_id)
        UNION ALL SELECT 1 FROM account_statutory_mappings m WHERE NOT EXISTS
          (SELECT 1 FROM accounts x WHERE x.society_id=m.society_id AND x.id=m.account_id)
    ) t;
    IF v_orphan_fks > 0 THEN RAISE EXCEPTION 'Post-migration: % orphan FK row(s).', v_orphan_fks; END IF;

    SELECT COUNT(*) INTO v_dup_ids FROM (
        SELECT society_id, id, COUNT(*) c FROM accounts GROUP BY society_id, id HAVING COUNT(*) > 1
    ) d;
    IF v_dup_ids > 0 THEN RAISE EXCEPTION 'Post-migration: % duplicate (society_id,id) pairs.', v_dup_ids; END IF;

    SELECT COUNT(*) INTO v_bad_parent FROM accounts a
     WHERE a.parent_account_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM accounts p WHERE p.society_id=a.society_id AND p.id=a.parent_account_id);
    IF v_bad_parent > 0 THEN RAISE EXCEPTION 'Post-migration: % account(s) with unresolvable parent_account_id.', v_bad_parent; END IF;

    RAISE NOTICE 'B1a block COA renumber: OK.';
END $$;

-- ── 13. Re-enable events trigger ─────────────────────────────────────────
ALTER TABLE events ENABLE TRIGGER trg_events_updated;

COMMIT;
