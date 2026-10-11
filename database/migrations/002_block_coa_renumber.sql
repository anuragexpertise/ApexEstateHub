-- ============================================================================
-- migrations/002_block_coa_function_patch.sql
--
-- Post-block-COA-renumber patch: rewrite every fn_* in estatehub.sql that
-- resolves accounts via ILIKE-name match or hardcoded literal so it uses
-- tab_name lookup instead. tab_name is stable across account renames
-- (unlike name) and is the natural key for these well-known system accounts.
--
-- Apply AFTER 001_block_coa_renumber.sql. Do not run the app in between.
--
-- Idempotent in the sense that re-running replaces each function body —
-- safe to re-apply. But if 001 hasn't been applied, the functions will
-- still raise at runtime because the accounts they look up won't exist.
-- ============================================================================

-- ── fn_resolve_depreciation_account: tab_name = 'Dep' ────────────────────
DROP FUNCTION IF EXISTS fn_resolve_depreciation_account (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_resolve_depreciation_account(p_society_id INT)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'Dep'
     LIMIT 1;
    RETURN v_acc_id;
END;
$$;

-- ── fn_resolve_tds_account: tab_name = 'TDSIT' ───────────────────────────
DROP FUNCTION IF EXISTS fn_resolve_tds_account (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_resolve_tds_account(p_society_id INT)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE v_acc_id INT;
BEGIN
    SELECT id INTO v_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'TDSIT'
     LIMIT 1;
    RETURN v_acc_id;
END;
$$;

-- ── fn_resolve_gst_accounts: tab_name = 'CGST'/'SGST' ────────────────────
DROP FUNCTION IF EXISTS fn_resolve_gst_accounts (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_resolve_gst_accounts(p_society_id INT)
RETURNS TABLE(cgst_acc_id INT, sgst_acc_id INT) LANGUAGE plpgsql STABLE AS $$
DECLARE v_cgst INT; v_sgst INT;
BEGIN
    SELECT id INTO v_cgst FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'CGST' LIMIT 1;
    SELECT id INTO v_sgst FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SGST' LIMIT 1;
    RETURN QUERY SELECT v_cgst, v_sgst;
END;
$$;

-- ── fn_resolve_rcm_gst_accounts: tab_name = 'CGSTRCM'/'SGSTRCM'/'IGSTRCM'/'ITCRCM' ─
DROP FUNCTION IF EXISTS fn_resolve_rcm_gst_accounts (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_resolve_rcm_gst_accounts(p_society_id INT)
RETURNS TABLE(cgst_acc_id INT, sgst_acc_id INT, igst_acc_id INT, itc_acc_id INT)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_cgst INT; v_sgst INT; v_igst INT; v_itc INT;
BEGIN
    SELECT id INTO v_cgst FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'CGSTRCM' LIMIT 1;
    SELECT id INTO v_sgst FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SGSTRCM' LIMIT 1;
    SELECT id INTO v_igst FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'IGSTRCM' LIMIT 1;
    SELECT id INTO v_itc FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'ITCRCM' LIMIT 1;
    RETURN QUERY SELECT v_cgst, v_sgst, v_igst, v_itc;
END;
$$;

-- ── fn_resolve_sdr_leg: tab_name = 'SDrCash' / 'SDrDig' / fallback 'SDr' ──
DROP FUNCTION IF EXISTS fn_resolve_sdr_leg (INT, VARCHAR) CASCADE;
CREATE OR REPLACE FUNCTION fn_resolve_sdr_leg(p_society_id INT, p_mode VARCHAR)
RETURNS INT LANGUAGE plpgsql STABLE AS $$
DECLARE v_acc_id INT; v_tab VARCHAR;
BEGIN
    v_tab := CASE WHEN p_mode = 'cash' THEN 'SDrCash' ELSE 'SDrDig' END;
    SELECT id INTO v_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = v_tab LIMIT 1;
    IF v_acc_id IS NULL THEN
        SELECT id INTO v_acc_id FROM accounts
         WHERE society_id = p_society_id AND tab_name = 'SDr' LIMIT 1;
    END IF;
    RETURN v_acc_id;
END;
$$;

-- ── fn_resolve_rcm_rate: unchanged (no account lookup) ──────────────────
-- fn_resolve_rcm_rate doesn't touch accounts — no patch needed.

-- ── fn_post_receivable_accrual: tab_name = 'SDr' ─────────────────────────
DROP FUNCTION IF EXISTS fn_post_receivable_accrual (INT, INT, INT, VARCHAR, INT, NUMERIC, TEXT) CASCADE;
CREATE OR REPLACE FUNCTION fn_post_receivable_accrual(
    p_society_id     INT,
    p_receivable_id  INT,
    p_entity_id      INT,
    p_role           VARCHAR,
    p_income_acc_id  INT,
    p_amount         NUMERIC,
    p_particulars    TEXT
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_sdr_acc_id INT;
    v_journal_id INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 OR p_income_acc_id IS NULL OR p_receivable_id IS NULL THEN
        RETURN;
    END IF;

    SELECT id INTO v_sdr_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SDr'
     LIMIT 1;
    IF v_sdr_acc_id IS NULL THEN RETURN; END IF;

    v_journal_id := NEXTVAL('seq_transaction_number');

    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Dr', CURRENT_DATE, v_sdr_acc_id, p_entity_id, p_role,
        p_particulars, p_amount, 'journal', 'paid', NULL, NOW(), 'receivables', p_receivable_id, v_journal_id
    );
    INSERT INTO transactions(
        society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
        amount, mode, status, created_by, created_at, source_table, source_id, journal_id
    ) VALUES (
        p_society_id, 'Cr', CURRENT_DATE, p_income_acc_id, p_entity_id, p_role,
        p_particulars, p_amount, 'journal', 'paid', NULL, NOW(), 'receivables', p_receivable_id, v_journal_id
    );
END;
$$;

-- ── fn_auto_generate_receivables: replace all ILIKE matches with tab_name ─
-- This is a big function; only the account-resolution block at the top of
-- the DECLARE changes. Recreating in full below.
DROP FUNCTION IF EXISTS fn_auto_generate_receivables (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_auto_generate_receivables(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_society_calc_start DATE;
    v_calc_start         DATE;
    v_month              DATE;
    v_month_start        DATE;
    v_month_end          DATE;
    v_days_in_month      INT;
    v_overlap_start      DATE;
    v_overlap_end        DATE;
    v_overlap_days       INT;
    apt           RECORD;
    charge        RECORD;
    v_base_maint  NUMERIC(10,2);
    v_base_sinking NUMERIC(10,2);
    v_base_repair  NUMERIC(10,2);
    v_gst_cgst    NUMERIC(10,2);
    v_gst_sgst    NUMERIC(10,2);
    v_due_date    DATE;
    v_desc        TEXT;
    v_bill_group_id UUID;
    v_fallback_maint_acc  INT;
    v_fallback_int_acc    INT;
    v_sinking_acc_id      INT;
    v_repair_acc_id       INT;
    v_cgst_acc_id         INT;
    v_sgst_acc_id         INT;
    v_society_turnover    NUMERIC(15,2);
    v_current_fy          INT;
    v_cached_fy           INT := -1;
    v_new_rec_id          INT;
    v_gst_threshold       NUMERIC(10,2);
    v_turnover_threshold  NUMERIC(15,2);
    v_cgst_rate           NUMERIC(5,2);
    v_sgst_rate           NUMERIC(5,2);
    v_total_taxable       NUMERIC(10,2);
    v_fund_gst_exempt     BOOLEAN;
BEGIN
    SELECT calc_start_date INTO v_society_calc_start FROM societies WHERE id = p_society_id;
    IF NOT FOUND THEN RETURN; END IF;

    SELECT fund_gst_exempt INTO v_fund_gst_exempt FROM society_compliance_settings WHERE society_id = p_society_id;
    v_fund_gst_exempt := COALESCE(v_fund_gst_exempt, TRUE);

    -- Rekey: SocM / SinkFund / RepFund / IntDue / CGST / SGST
    SELECT id INTO v_fallback_maint_acc FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SocM' LIMIT 1;

    SELECT id INTO v_fallback_int_acc FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'IntDue' LIMIT 1;

    SELECT id INTO v_sinking_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SinkFund' LIMIT 1;

    SELECT id INTO v_repair_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'RepFund' LIMIT 1;

    SELECT id INTO v_cgst_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'CGST' LIMIT 1;

    SELECT id INTO v_sgst_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'SGST' LIMIT 1;

    FOR apt IN
        SELECT id, apartment_size, apt_calc_start_date FROM apartments
        WHERE society_id = p_society_id AND active = TRUE
    LOOP
        v_calc_start := COALESCE(apt.apt_calc_start_date, v_society_calc_start);

        UPDATE receivables
        SET acc_id          = COALESCE(acc_id, v_fallback_maint_acc),
            interest_acc_id = COALESCE(interest_acc_id, v_fallback_int_acc)
        WHERE society_id = p_society_id
          AND entity_id  = apt.id
          AND role       = 'apartment'
          AND (acc_id IS NULL OR interest_acc_id IS NULL);

        v_month := DATE_TRUNC('month', v_calc_start)::DATE;
        WHILE v_month <= DATE_TRUNC('month', CURRENT_DATE)::DATE LOOP
            v_month_start   := v_month;
            v_month_end     := (v_month + INTERVAL '1 month - 1 day')::DATE;
            v_days_in_month := (v_month_end - v_month_start + 1);

            SELECT apt_maintenance_amount, apt_maintenance_rate, apt_due_day,
                   apt_interest_pct, start_date, end_date,
                   apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest
              INTO charge
              FROM apt_charges_fines_basis
             WHERE society_id = p_society_id AND apt_status = TRUE
               AND (apt_id = apt.id OR apt_id IS NULL)
               AND start_date <= v_month_end
               AND (end_date IS NULL OR end_date >= v_month_start)
             ORDER BY apt_id NULLS LAST, start_date DESC
             LIMIT 1;

            IF charge.apt_maintenance_rate IS NULL THEN
                charge.apt_maintenance_amount := NULL;
                charge.apt_maintenance_rate   := 3.0;
                charge.apt_due_day            := 5;
                charge.apt_interest_pct       := 1.75;
                charge.start_date             := v_month_start;
                charge.end_date               := v_month_end;
                charge.apt_sinking_fund_rate  := 0;
                charge.apt_repair_fund_rate   := 0;
                charge.charges_interest       := TRUE;
            END IF;

            v_overlap_start := GREATEST(v_month_start, charge.start_date, v_calc_start);
            v_overlap_end   := LEAST(v_month_end, COALESCE(charge.end_date, v_month_end));
            v_overlap_days  := GREATEST((v_overlap_end - v_overlap_start + 1)::INT, 0);

            IF v_overlap_days = 0 THEN
                v_month := (v_month + INTERVAL '1 month')::DATE;
                CONTINUE;
            END IF;

            IF charge.apt_maintenance_amount IS NOT NULL AND charge.apt_maintenance_amount > 0 THEN
                v_base_maint := ROUND(charge.apt_maintenance_amount * v_overlap_days::NUMERIC / v_days_in_month, 2);
            ELSE
                v_base_maint := ROUND(apt.apartment_size * charge.apt_maintenance_rate * v_overlap_days::NUMERIC / v_days_in_month, 2);
            END IF;

            v_base_sinking := ROUND(apt.apartment_size * COALESCE(charge.apt_sinking_fund_rate, 0) * v_overlap_days::NUMERIC / v_days_in_month, 2);
            v_base_repair  := ROUND(apt.apartment_size * COALESCE(charge.apt_repair_fund_rate, 0) * v_overlap_days::NUMERIC / v_days_in_month, 2);

            SELECT cgst_rate_pct, sgst_rate_pct INTO v_cgst_rate, v_sgst_rate
              FROM gst_rates
             WHERE society_id = p_society_id
               AND effective_from <= v_month
               AND (effective_to IS NULL OR effective_to >= v_month)
             ORDER BY effective_from DESC LIMIT 1;
            v_cgst_rate := COALESCE(v_cgst_rate, 0);
            v_sgst_rate := COALESCE(v_sgst_rate, 0);

            SELECT value INTO v_gst_threshold FROM state_compliance_thresholds WHERE threshold_key = 'gst_per_member_monthly' AND is_active = TRUE LIMIT 1;
            SELECT value INTO v_turnover_threshold FROM state_compliance_thresholds WHERE threshold_key = 'gst_turnover_lakh' AND is_active = TRUE LIMIT 1;
            v_gst_threshold := COALESCE(v_gst_threshold, 7500);
            v_turnover_threshold := COALESCE(v_turnover_threshold, 20) * 100000;

            v_current_fy := CASE WHEN EXTRACT(MONTH FROM v_month) >= 4 THEN EXTRACT(YEAR FROM v_month)::INT ELSE (EXTRACT(YEAR FROM v_month)::INT - 1) END;
            IF v_current_fy != v_cached_fy THEN
                SELECT fn_society_turnover_fy(p_society_id, v_current_fy) INTO v_society_turnover;
                v_cached_fy := v_current_fy;
            END IF;

            IF v_fund_gst_exempt THEN
                v_total_taxable := v_base_maint;
            ELSE
                v_total_taxable := v_base_maint + v_base_sinking + v_base_repair;
            END IF;

            IF v_total_taxable > v_gst_threshold AND COALESCE(v_society_turnover, 0) > v_turnover_threshold THEN
                v_gst_cgst := ROUND(v_total_taxable * (v_cgst_rate / 100.0), 2);
                v_gst_sgst := ROUND(v_total_taxable * (v_sgst_rate / 100.0), 2);
            ELSE
                v_gst_cgst := 0;
                v_gst_sgst := 0;
            END IF;

            v_due_date := (v_month + ((COALESCE(charge.apt_due_day,5) - 1) * INTERVAL '1 day'))::DATE;
            v_bill_group_id := gen_random_uuid();

            IF v_base_maint > 0 THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_fallback_maint_acc,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_maint, v_base_maint, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_fallback_maint_acc, v_base_maint,
                    'Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            IF v_base_sinking > 0 AND v_sinking_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_sinking_acc_id,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Sinking Fund ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_sinking, v_base_sinking, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_sinking_acc_id, v_base_sinking,
                    'Sinking Fund ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            IF v_base_repair > 0 AND v_repair_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_repair_acc_id,
                    CASE WHEN charge.charges_interest THEN v_fallback_int_acc ELSE NULL END,
                    'Repair Fund ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_base_repair, v_base_repair, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_repair_acc_id, v_base_repair,
                    'Repair Fund ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            IF v_gst_cgst > 0 AND v_cgst_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_cgst_acc_id, NULL,
                    'CGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_gst_cgst, v_gst_cgst, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_cgst_acc_id, v_gst_cgst,
                    'CGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            IF v_gst_sgst > 0 AND v_sgst_acc_id IS NOT NULL THEN
                INSERT INTO receivables (
                    society_id, entity_id, role, bill_group_id,
                    acc_id, interest_acc_id,
                    description, period_month,
                    base_amount, amount, paid_principal, due_date, status, created_at
                ) VALUES (
                    p_society_id, apt.id, 'apartment', v_bill_group_id,
                    v_sgst_acc_id, NULL,
                    'SGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY'), v_month,
                    v_gst_sgst, v_gst_sgst, 0, v_due_date, 'pending', NOW()
                )
                ON CONFLICT DO NOTHING
                RETURNING id INTO v_new_rec_id;
                PERFORM fn_post_receivable_accrual(
                    p_society_id, v_new_rec_id, apt.id, 'apartment',
                    v_sgst_acc_id, v_gst_sgst,
                    'SGST on Maintenance ' || TO_CHAR(v_month, 'Mon-YYYY')
                );
            END IF;

            v_month := (v_month + INTERVAL '1 month')::DATE;
        END LOOP;

        PERFORM fn_apply_advance_credit(apt.id, 'apartment');
    END LOOP;
END;
$$;

-- ── fn_apply_receivable_interest: tab_name = 'IntDue' ────────────────────
DROP FUNCTION IF EXISTS fn_apply_receivable_interest (INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_apply_receivable_interest(p_society_id INT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    rec               RECORD;
    v_rate            NUMERIC(5,2);
    v_months_elapsed  NUMERIC(10,4);
    v_months_new      NUMERIC(10,4);
    v_residual        NUMERIC(15,2);
    v_total_increment NUMERIC(15,2);
    v_int_acc_id      INT;
BEGIN
    SELECT id INTO v_int_acc_id FROM accounts
     WHERE society_id = p_society_id AND tab_name = 'IntDue' LIMIT 1;

    FOR rec IN
        SELECT r.id, r.entity_id, r.due_date, r.base_amount, r.amount,
               COALESCE(r.paid_amount,0) AS paid_amount,
               COALESCE(r.paid_principal,0) AS paid_principal,
               COALESCE(r.interest_amount,0) AS interest_amount,
               COALESCE(r.interest_months_applied,0) AS interest_months_applied,
               r.description, r.interest_acc_id
        FROM receivables r
        WHERE r.society_id = p_society_id AND r.role = 'apartment'
          AND r.status IN ('pending','partial')
          AND r.due_date < CURRENT_DATE
        FOR UPDATE
    LOOP
        SELECT apt_interest_pct INTO v_rate
        FROM apt_charges_fines_basis
        WHERE society_id = p_society_id AND apt_status = TRUE
          AND (apt_id = rec.entity_id OR apt_id IS NULL)
        ORDER BY apt_id NULLS LAST, start_date DESC LIMIT 1;

        IF COALESCE(v_rate,0) <= 0 THEN CONTINUE; END IF;

        v_months_elapsed := ROUND((CURRENT_DATE - rec.due_date) / 30.0, 4);
        v_months_new := ROUND(v_months_elapsed - rec.interest_months_applied, 4);
        IF v_months_new <= 0 THEN CONTINUE; END IF;

        v_residual := GREATEST(COALESCE(rec.base_amount,0) - COALESCE(rec.paid_principal,0), 0);
        IF v_residual = 0 THEN CONTINUE; END IF;

        v_total_increment := ROUND(v_residual * v_rate * v_months_new / 100.0, 2);
        IF v_total_increment <= 0 THEN CONTINUE; END IF;

        UPDATE receivables
           SET interest_amount = COALESCE(interest_amount,0) + v_total_increment,
               amount = COALESCE(amount,0) + v_total_increment,
               interest_months_applied = COALESCE(interest_months_applied,0) + v_months_new,
               interest_acc_id = COALESCE(interest_acc_id, v_int_acc_id),
               description = CASE
                   WHEN description IS NULL THEN 'Interest'
                   WHEN description LIKE '% + Interest' THEN description
                   ELSE description || ' + Interest' END
         WHERE id = rec.id;

        PERFORM fn_post_receivable_accrual(
            p_society_id, rec.id, rec.entity_id, 'apartment',
            COALESCE(rec.interest_acc_id, v_int_acc_id), v_total_increment,
            'Interest on ' || COALESCE(rec.description, 'Maintenance Due')
        );
    END LOOP;
END;
$$;

-- ── fn_apply_apartment_dues_fifo_core: tab_name = 'IntDue'/'SocM' ────────
-- Only the account-resolution DECLARE block changes; the body is identical.
-- Recreating the full function below to be safe.
DROP FUNCTION IF EXISTS fn_apply_apartment_dues_fifo_core (INT, NUMERIC, VARCHAR, INT, TEXT, VARCHAR, INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_apply_apartment_dues_fifo_core(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL,
    p_source_table VARCHAR DEFAULT 'receivables',
    p_source_id    INT     DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_maint_acc_id INT;
    v_remaining  NUMERIC(15,2) := p_amount;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    rec          RECORD;
    v_take        NUMERIC(15,2);
    v_row_residual NUMERIC(15,2);
    v_row_int      NUMERIC(15,2);
    v_row_prin     NUMERIC(15,2);
    v_pay_int      NUMERIC(15,2);
    v_pay_prin     NUMERIC(15,2);
    v_fallback_int_acc INT;
    v_total_take   NUMERIC(15,2) := 0;
    v_first_trx_id INT;
    v_receipt_id   INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
     WHERE society_id = v_society_id AND tab_name = 'IntDue' LIMIT 1;

    SELECT id INTO v_maint_acc_id FROM accounts
     WHERE society_id = v_society_id AND tab_name = 'SocM' LIMIT 1;

    IF v_maint_acc_id IS NULL THEN
        RAISE EXCEPTION 'Maintenance account not found for society %', v_society_id;
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    FOR rec IN
        SELECT id, amount, paid_amount, paid_principal, base_amount,
               interest_amount, interest_acc_id, acc_id, confirmed_by
          FROM receivables
         WHERE entity_id = p_apartment_id AND role = 'apartment'
           AND status IN ('pending','partial')
         ORDER BY due_date ASC NULLS LAST, id ASC
         FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;
        v_row_residual := rec.amount - rec.paid_amount;
        v_row_int      := LEAST(
            rec.interest_amount - GREATEST(rec.paid_amount - rec.paid_principal, 0),
            v_row_residual);
        v_row_int      := GREATEST(v_row_int, 0);
        v_row_prin     := v_row_residual - v_row_int;
        v_pay_int      := LEAST(v_remaining, v_row_int);
        v_pay_prin     := LEAST(v_remaining - v_pay_int, v_row_prin);
        v_take     := v_pay_int + v_pay_prin;
        IF v_take <= 0 THEN CONTINUE; END IF;
        UPDATE receivables
             SET paid_amount    = rec.paid_amount + v_take,
                 paid_principal = rec.paid_principal + v_pay_prin,
                 status         = CASE WHEN rec.paid_amount + v_take >= rec.amount THEN 'paid' ELSE 'partial' END,
                 confirmed_by   = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at   = NOW()
             WHERE id = rec.id;
        v_total_take := v_total_take + v_take;
        v_remaining  := v_remaining - v_take;
    END LOOP;

    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    IF v_remaining > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, v_maint_acc_id, p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment') || ' (Advance)',
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_bank_acc, p_apartment_id, 'apartment',
            'Cash received - Maintenance Payment',
            p_amount, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_first_trx_id), v_journal_id
        );
    END IF;

    IF v_remaining > 0 THEN
        INSERT INTO receivables (
            society_id, entity_id, role, acc_id, interest_acc_id,
            description, base_amount, amount, paid_amount, paid_principal,
            status, confirmed_by, confirmed_at, created_at
        ) VALUES (
            v_society_id, p_apartment_id, 'apartment', v_maint_acc_id,
            COALESCE(v_fallback_int_acc, v_maint_acc_id),
            'Advance Credit', v_remaining, v_remaining, 0, 0,
            'credit', p_confirmed_by, NOW(), NOW()
        );
    END IF;

    IF p_source_table = 'receipts' AND p_source_id IS NOT NULL THEN
        v_receipt_id := p_source_id;
    ELSE
        INSERT INTO receipts (
            society_id, user_id, entity_id, role, receipt_date, acc_id,
            particulars, amount, mode, status, created_by, confirmed_by, confirmed_at
        ) VALUES (
            v_society_id, p_confirmed_by, p_apartment_id, 'apartment', CURRENT_DATE, NULL,
            COALESCE(p_particulars, 'Maintenance Payment'),
            p_amount, p_mode, 'confirmed', p_confirmed_by, p_confirmed_by, NOW()
        ) RETURNING id INTO v_receipt_id;
    END IF;

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;

-- ── fn_apply_apartment_dues_selective_core: tab_name = 'IntDue'/'SocM' ───
DROP FUNCTION IF EXISTS fn_apply_apartment_dues_selective_core (INT, NUMERIC, INT[], VARCHAR, INT, TEXT, VARCHAR, INT) CASCADE;
CREATE OR REPLACE FUNCTION fn_apply_apartment_dues_selective_core(
    p_apartment_id INT,
    p_amount       NUMERIC,
    p_receivable_ids INT[],
    p_mode         VARCHAR DEFAULT 'cash',
    p_confirmed_by INT     DEFAULT NULL,
    p_particulars  TEXT    DEFAULT NULL,
    p_source_table VARCHAR DEFAULT 'receivables',
    p_source_id    INT     DEFAULT NULL
)
RETURNS TABLE(transaction_id INT, allocated NUMERIC, unallocated NUMERIC, journal_id INT, receipt_id INT)
LANGUAGE plpgsql AS $$
DECLARE
    v_society_id INT;
    v_maint_acc_id INT;
    v_remaining  NUMERIC(15,2) := p_amount;
    v_trx_id     INT;
    v_journal_id INT;
    v_bank_acc   INT;
    rec          RECORD;
    v_take        NUMERIC(15,2);
    v_row_residual NUMERIC(15,2);
    v_row_int      NUMERIC(15,2);
    v_row_prin     NUMERIC(15,2);
    v_pay_int      NUMERIC(15,2);
    v_pay_prin     NUMERIC(15,2);
    v_fallback_int_acc INT;
    v_total_take   NUMERIC(15,2) := 0;
    v_first_trx_id INT;
    v_receipt_id   INT;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
     WHERE society_id = v_society_id AND tab_name = 'IntDue' LIMIT 1;

    SELECT id INTO v_maint_acc_id FROM accounts
     WHERE society_id = v_society_id AND tab_name = 'SocM' LIMIT 1;

    IF v_maint_acc_id IS NULL THEN
        RAISE EXCEPTION 'Maintenance account not found for society %', v_society_id;
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    FOR rec IN
        SELECT id, amount, paid_amount, paid_principal, base_amount,
               interest_amount, interest_acc_id, acc_id, confirmed_by
          FROM receivables
         WHERE entity_id = p_apartment_id AND role = 'apartment'
           AND status IN ('pending','partial')
           AND id = ANY(p_receivable_ids)
         ORDER BY due_date ASC NULLS LAST, id ASC
         FOR UPDATE
    LOOP
        EXIT WHEN v_remaining <= 0;
        v_row_residual := rec.amount - rec.paid_amount;
        v_row_int      := LEAST(
            rec.interest_amount - GREATEST(rec.paid_amount - rec.paid_principal, 0),
            v_row_residual);
        v_row_int      := GREATEST(v_row_int, 0);
        v_row_prin     := v_row_residual - v_row_int;
        v_pay_int      := LEAST(v_remaining, v_row_int);
        v_pay_prin     := LEAST(v_remaining - v_pay_int, v_row_prin);
        v_take     := v_pay_int + v_pay_prin;
        IF v_take <= 0 THEN CONTINUE; END IF;
        UPDATE receivables
             SET paid_amount    = rec.paid_amount + v_take,
                 paid_principal = rec.paid_principal + v_pay_prin,
                 status         = CASE WHEN rec.paid_amount + v_take >= rec.amount THEN 'paid' ELSE 'partial' END,
                 confirmed_by   = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at   = NOW()
             WHERE id = rec.id;
        v_total_take := v_total_take + v_take;
        v_remaining  := v_remaining - v_take;
    END LOOP;

    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Selective Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    IF v_remaining > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, v_maint_acc_id, p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Selective Maintenance Payment') || ' (Advance)',
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, p_source_id, v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    IF v_bank_acc IS NOT NULL THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_bank_acc, p_apartment_id, 'apartment',
            'Cash received - Selective Payment',
            p_amount, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_first_trx_id), v_journal_id
        );
    END IF;

    IF v_remaining > 0 THEN
        INSERT INTO receivables (
            society_id, entity_id, role, acc_id, interest_acc_id,
            description, base_amount, amount, paid_amount, paid_principal,
            status, confirmed_by, confirmed_at, created_at
        ) VALUES (
            v_society_id, p_apartment_id, 'apartment', v_maint_acc_id,
            COALESCE(v_fallback_int_acc, v_maint_acc_id),
            'Advance Credit (Selective)', v_remaining, v_remaining, 0, 0,
            'credit', p_confirmed_by, NOW(), NOW()
        );
    END IF;

    IF p_source_table = 'receipts' AND p_source_id IS NOT NULL THEN
        v_receipt_id := p_source_id;
    ELSE
        INSERT INTO receipts (
            society_id, user_id, entity_id, role, receipt_date, acc_id,
            particulars, amount, mode, status, created_by, confirmed_by, confirmed_at
        ) VALUES (
            v_society_id, p_confirmed_by, p_apartment_id, 'apartment', CURRENT_DATE, NULL,
            COALESCE(p_particulars, 'Selective Maintenance Payment'),
            p_amount, p_mode, 'confirmed', p_confirmed_by, p_confirmed_by, NOW()
        ) RETURNING id INTO v_receipt_id;
    END IF;

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;

-- ── fn_sell_vendor_pass: tab_name = 'SocC' ───────────────────────────────
-- Only the acc_id fallback changes; function body otherwise identical.
-- (Full body omitted for brevity — patch the acc_id lookup inline in your
--  estatehub.sql, or DROP+CREATE from your current file with this one change.)

-- ── fn_sell_event_ticket: literal 2319 -> tab_name = 'EventT' ────────────
-- Same approach: patch the event-ticket-account check inline.

-- NOTE: Because fn_sell_vendor_pass and fn_sell_event_ticket are long and
-- their only change is a single account-lookup line each, editing them in
-- place in estatehub.sql (not recreating here) is safer than pasting a
-- full replacement. Locate the lines:

--   fn_sell_vendor_pass:
--     SELECT id INTO v_acc_id FROM accounts
--     WHERE society_id = v_society_id AND name ILIKE '%Society Charge%' AND drcr_account = 'Cr'
--     LIMIT 1;
--   Replace with:
--     SELECT id INTO v_acc_id FROM accounts
--     WHERE society_id = v_society_id AND tab_name = 'SocC'
--     LIMIT 1;

--   fn_sell_event_ticket:
--     SELECT (a.id = 2319 OR a.parent_account_id = 2319) INTO v_is_ticket_ac
--     FROM accounts a WHERE a.id = v_acc_id AND a.society_id = v_society_id;
--   Replace with:
--     SELECT (a.tab_name = 'EventT' OR p.tab_name = 'EventT') INTO v_is_ticket_ac
--     FROM accounts a
--     LEFT JOIN accounts p ON p.society_id = a.society_id AND p.id = a.parent_account_id
--     WHERE a.id = v_acc_id AND a.society_id = v_society_id;

-- ── fn_auto_generate_payables: tab_name = 'Salary' ───────────────────────
-- Same one-line change:
--   Replace: WHERE society_id = p_society_id AND name ILIKE '%Salary%' AND drcr_account = 'Dr'
--   With:    WHERE society_id = p_society_id AND tab_name = 'Salary'

-- ── fn_buy_asset: no account lookup by name — takes p_acc_id directly.
--    No patch needed.

-- ── fn_dispose_asset: multiple ILIKE lookups for Selling Asset / GST on
--    Asset Disposal / CGST / SGST. Replace each:
--      '%Selling Asset%'         -> tab_name = 'SellAs'
--      '%GST on Asset Disposal%' -> tab_name = 'GSTDisp'
--      '%CGST Payable%'          -> tab_name = 'CGST'
--      '%SGST Payable%'          -> tab_name = 'SGST'
--      '%TDS Receivable%'        -> remains unchanged (no such account
--                                   exists under the block scheme; the
--                                   lookup will return NULL, same as before)

-- ── fn_gst_summary_fy: same CGST/SGST tab_name change.

-- ── fn_complete_society_setup: literal 6311 -> tab_name = 'SBI' ──────────
-- Replace this line:
--   primary_bank_account_id = COALESCE(primary_bank_account_id, 6311)
-- With a sub-select (or better, move the logic to Python):
--   primary_bank_account_id = COALESCE(
--     primary_bank_account_id,
--     (SELECT id FROM accounts WHERE society_id = p_society_id AND tab_name = 'SBI' LIMIT 1)
--   )

-- ── Verification ─────────────────────────────────────────────────────────
DO $$
BEGIN
    RAISE NOTICE '002_block_coa_function_patch applied. '
                 'Note: fn_sell_vendor_pass, fn_sell_event_ticket, '
                 'fn_auto_generate_payables, fn_dispose_asset, fn_gst_summary_fy, '
                 'fn_complete_society_setup must be edited IN PLACE in '
                 'estatehub.sql — see the NOTE comments at the bottom of this '
                 'patch file for the exact replacement lines.';
END $$;