-- Minimal seed to exercise fn_verify_receipt (TDS split), fn_verify_expense,
-- fn_cashbook_paired_v2 and fn_account_ledger_fy against the new migration.

INSERT INTO societies (name, calc_start_date) VALUES ('TestSociety', '2025-04-01');
-- id = 1

INSERT INTO accounts (society_id, name, drcr_account, has_bf, drcr_bf, is_cash_or_bank)
VALUES
 (1, 'Cash-in-hand', 'Dr', TRUE, 'Dr', TRUE),        -- 1
 (1, 'ICICI Bank',   'Dr', TRUE, 'Dr', TRUE),         -- 2
 (1, 'Patients',     'Cr', FALSE, 'Cr', FALSE),       -- 3  income, applies_tds
 (1, 'TDStoIT',      'Dr', FALSE, 'Dr', FALSE),       -- 4
 (1, 'Salary',       'Dr', FALSE, 'Dr', FALSE),       -- 5  expense
 (1, 'Misc',         'Dr', FALSE, 'Dr', FALSE);       -- 6  expense (cash)

UPDATE accounts SET applies_tds = TRUE WHERE name = 'Patients';

INSERT INTO brought_forward (society_id, financial_year, acc_id, drcr_bf, bf_amount)
VALUES
 (1, 2025, 1, 'Dr', 100000),   -- Cash-in-hand opening
 (1, 2025, 2, 'Dr', 50000);    -- ICICI opening

-- 1) Cash receipt (no TDS/GST, single side only)
INSERT INTO receipts (society_id, entity_id, role, receipt_date, acc_id, particulars, amount, mode, status)
VALUES (1, NULL, 'other', '2025-04-10', 3, 'Cash fee', 300, 'cash', 'pending');

-- 2) Non-cash receipt on TDS-flagged account (mirrors Patients/TDStoIT example: 7524 gross, 10% TDS = 752.4)
INSERT INTO receipts (society_id, entity_id, role, receipt_date, acc_id, particulars, amount, mode, status)
VALUES (1, NULL, 'other', '2025-04-15', 3, 'UPI fee with TDS', 7524, 'upi', 'pending');

-- 3) Cash expense
INSERT INTO expenses (society_id, entity_id, role, expense_date, acc_id, particulars, amount, mode, status)
VALUES (1, NULL, 'other', '2025-04-12', 6, 'Stationery', 280, 'cash', 'pending');

-- 4) Non-cash expense (Salary paid by bank transfer, no GST)
INSERT INTO expenses (society_id, entity_id, role, expense_date, acc_id, particulars, amount, mode, status)
VALUES (1, NULL, 'other', '2025-04-20', 5, 'Salary transfer', 3000, 'bank', 'pending');

SELECT * FROM fn_verify_receipt(1, NULL, NULL);
SELECT * FROM fn_verify_receipt(2, NULL, NULL);
SELECT * FROM fn_verify_expense(1, NULL, NULL);
SELECT * FROM fn_verify_expense(2, NULL, NULL);

\echo '--- transactions table ---'
SELECT id, trx_date, acc_id, (SELECT name FROM accounts WHERE id=acc_id) AS acc_name,
       amount, mode, entry_side, journal_id, tds, gst, source_table, source_id
FROM transactions ORDER BY id;

\echo '--- fn_cashbook_paired_v2 ---'
SELECT row_date, rc_account_name, rc_cash, rc_chq,
       pc_account_name, pc_cash, pc_chq, running_balance
FROM fn_cashbook_paired_v2(1, NULL, NULL, NULL, '2025-04-01', '2025-04-30');

\echo '--- fn_account_ledger_fy for Patients (acc 3) ---'
SELECT * FROM fn_account_ledger_fy(1, 3, 2025::SMALLINT);

\echo '--- fn_account_ledger_fy for TDStoIT (acc 4) ---'
SELECT * FROM fn_account_ledger_fy(1, 4, 2025::SMALLINT);

\echo '--- receivable/payable staging test ---'
INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount, amount, due_date, status)
VALUES (1, 99, 'apartment', 3, 'Maintenance Apr', 1500, 1500, '2025-04-05', 'pending');

INSERT INTO payables (society_id, entity_id, role, acc_id, description, amount, status, due_date)
VALUES (1, 5, 'security', 5, 'Guard shift Apr', 800, 'pending', '2025-04-06');

SELECT fn_verify_receivable((SELECT id FROM receivables WHERE description='Maintenance Apr'), NULL, 'cash');
SELECT fn_verify_payment((SELECT id FROM payables WHERE description='Guard shift Apr'), NULL, 'cash');

\echo '--- resulting receipts/expenses rows ---'
SELECT id, acc_id, particulars, amount, mode, status FROM receipts ORDER BY id;
SELECT id, acc_id, particulars, amount, mode, status FROM expenses ORDER BY id;

\echo '--- receivables/payables status after verify ---'
SELECT id, status, paid_amount FROM receivables;
SELECT id, status FROM payables;

\echo '--- transactions after receivable/payable verify ---'
SELECT id, acc_id, (SELECT name FROM accounts WHERE id=acc_id) AS acc_name, amount, mode, entry_side, source_table, source_id
FROM transactions WHERE source_id IN (3,4) ORDER BY id;
