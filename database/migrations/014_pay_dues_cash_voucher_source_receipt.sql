-- 014: Pay Dues (FIFO and selective) cash vouchers must cite the receipt, not one bill.
--
-- Symptom: "Double-entry violated: cash voucher journal N moves 25200.00 of cash but its
-- source document is for 3600.00" when an admin pays several bills in cash.
-- Cause: an all-cash voucher has no Cash-in-Hand leg, so the ledger check compares the cash
-- moved with the document the legs cite. The two cores below cited the OLDEST bill settled
-- while posting the whole payment under it. They now create the receipt first and every leg
-- cites it (owner self-pay confirm already passed its pending receipt, unchanged).
--
-- Existing databases only get function changes through this folder (estatehub.sql is for fresh
-- installs). Idempotent: CREATE OR REPLACE with the same signatures; no data is touched.
--   python3 database/apply_migration.py 014

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
    v_maint_acc_id INT;  -- explicit maintenance account for advance-credit fallback
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
    v_total_take   NUMERIC(15,2) := 0;  -- running total actually applied to open dues this call — one Cr leg to the SDr leaf covers all of it (accrual basis, 2026-08)
    v_first_trx_id INT;
    v_src          INT;  -- source document of the Cr legs when no originating record was given: the first bill settled (Plan v3 3.8)
    v_receipt_id   INT;  -- new (2026-08): the receipt this payment is recorded against — either newly
                          -- created here (admin-direct path) or the pre-existing self-reported receipt
                          -- being confirmed (p_source_id, when p_source_table='receipts')
    -- Per-bank-account split of the incoming money (2026-09). A split bill
    -- settles rows carrying DIFFERENT acc_ids — a Sinking Fund line (3210),
    -- a Repair Fund line (3220), a Maintenance line (4210) — and those can
    -- be mapped to different physical bank accounts via
    -- fund_bank_account_map. Posting one lump Dr to the single primary bank
    -- account is what made the mapping silently inconsistent: verifying
    -- dues one flat at a time banked into the mapped account, while paying
    -- through the FIFO path (the common case) did not. Accumulated here as
    -- {bank_acc_id: amount} and emitted as one Dr leg per distinct account
    -- after the loop, so the journal still balances (the legs sum to
    -- v_total_take + v_remaining = p_amount, exactly as the old single leg
    -- did).
    v_legs      JSONB := '{}'::JSONB;
    v_leg_bank  INT;
    v_leg       RECORD;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Amount must be > 0';
    END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
    WHERE society_id = v_society_id
      AND name ILIKE '%Due Interest%' AND drcr_account = 'Cr'
    LIMIT 1;

    -- Resolve maintenance account explicitly — used for advance-credit
    -- fallback (overpayment is a maintenance credit, not a fund contribution)
    -- and as the home for any overpaid amount when no open dues exist.
    SELECT id INTO v_maint_acc_id FROM accounts
    WHERE society_id = v_society_id
      AND name ILIKE '%Society Maintenance Charge%'
      AND drcr_account = 'Cr'
    LIMIT 1;

    IF v_maint_acc_id IS NULL THEN
        RAISE EXCEPTION 'Maintenance account not found for society %', v_society_id;
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- The receipt is the voucher's source document, so it has to exist BEFORE
    -- any leg is posted. An all-cash voucher has no Cash-in-Hand leg, so the
    -- ledger trigger (fn_journal_balance_problem) checks the cash that moved
    -- against the amount on the document the legs cite. This function used to
    -- cite the OLDEST bill settled (receivables.id) while posting the whole
    -- payment under it: paying 8 bills of 3,600 in cash moved 28,800 against a
    -- 3,600 document and the commit was refused. One receipt for the full
    -- amount received is the document that actually matches the cash.
    -- (Self-pay confirm passes the owner's pending receipt in as p_source_id.)
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
        p_source_table := 'receipts';   -- every leg below cites the receipt, not a bill
        p_source_id    := v_receipt_id;
    END IF;

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

        v_pay_int  := LEAST(v_remaining, v_row_int);
        v_pay_prin := LEAST(v_remaining - v_pay_int, v_row_prin);
        v_take     := v_pay_int + v_pay_prin;
        IF v_take <= 0 THEN CONTINUE; END IF;

        UPDATE receivables
             SET paid_amount    = rec.paid_amount + v_take,
                 paid_principal = rec.paid_principal + v_pay_prin,
                 status         = CASE WHEN rec.paid_amount + v_take >= rec.amount
                                        THEN 'paid' ELSE 'partial' END,
                 confirmed_by   = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at   = NOW()
             WHERE id = rec.id;

        v_total_take := v_total_take + v_take;
        IF v_src IS NULL THEN v_src := rec.id; END IF;
        v_remaining  := v_remaining - v_take;

        -- Attribute this row's money to whatever bank account its own
        -- acc_id maps to (NULL for cash mode, and NULL for any account
        -- without a mapping — both fall through to the society's primary
        -- account below via v_bank_acc).
        v_leg_bank := COALESCE(fn_resolve_bank_leg(v_society_id, p_mode, rec.acc_id), v_bank_acc);
        IF v_leg_bank IS NOT NULL THEN
            v_legs := v_legs || jsonb_build_object(
                v_leg_bank::TEXT,
                COALESCE((v_legs ->> v_leg_bank::TEXT)::NUMERIC, 0) + v_take
            );
        END IF;
    END LOOP;

    -- Cr: Sundry Debtors (Digital/Cash leaf, by p_mode) — ONE combined
    -- leg for every row actually settled this call, sharing one
    -- journal_id. Income/GST-payable was already recognized at BILL
    -- time by fn_post_receivable_accrual (accrual basis, 2026-08);
    -- collection just relieves the debtor now, so there's no longer a
    -- need to route per-row by acc_id — every row clears against the
    -- same leaf account regardless of which income category it billed
    -- under (base_maint / sinking / repair / GST / interest all land
    -- on the same "amount this member owed" balance).
    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src), v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Overpayment (or a payment with no open dues at all) is banked as a
    -- maintenance Cr leg so the journal stays balanced, then recorded as an
    -- advance-credit receivable. Routed to maintenance explicitly, not to
    -- whichever row happened to be oldest.
    IF v_remaining > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, v_maint_acc_id, p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Maintenance Payment') || ' (Advance)',
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src), v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Any overpayment is a maintenance receipt, so it belongs on the
    -- primary account (maintenance is not a fund) — attribute it before
    -- the Dr legs are emitted, so it lands in the same accumulator as the
    -- rest of the payment.
    IF v_remaining > 0 AND v_bank_acc IS NOT NULL THEN
        v_legs := v_legs || jsonb_build_object(
            v_bank_acc::TEXT,
            COALESCE((v_legs ->> v_bank_acc::TEXT)::NUMERIC, 0) + v_remaining
        );
    END IF;

    -- Dr: cash / bank paired side (actual amount received), split across
    -- the distinct bank accounts the settled rows map to. References the
    -- originating record (p_source_id, e.g. a confirmed self-pay receipt)
    -- when given, else the first Cr leg posted this call, so the journal is
    -- traceable as one event either way. When nothing maps anywhere
    -- (cash mode, or no fund has a mapping) this is the single primary
    -- leg exactly as before.
    FOR v_leg IN
        SELECT e.key::INT AS bank_acc, e.value::NUMERIC(15,2) AS amt
          FROM jsonb_each_text(v_legs) e
         WHERE e.value::NUMERIC > 0
         ORDER BY e.key::INT
    LOOP
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_leg.bank_acc, p_apartment_id, 'apartment',
            'Cash received - Maintenance Payment',
            v_leg.amt, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src, v_first_trx_id), v_journal_id
        );
    END LOOP;

    -- Advance-credit receivable marker (status='credit') for any excess beyond
    -- every currently-open due. Not a separate ledger entry — the overpayment
    -- Cr leg above already recognizes the cash as maintenance income.
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

    -- (The receipt of record was created before the legs, above: it is the voucher's source document.)

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;

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
    v_src          INT;  -- source document of the Cr legs when no originating record was given: the first bill settled (Plan v3 3.8)
    v_receipt_id   INT;
    -- Per-bank-account split of the incoming money — see the identical
    -- accumulator in fn_apply_apartment_dues_fifo_core. Both "Pay Dues"
    -- engines have to agree here, or a society that maps its Sinking Fund
    -- to a separate account would see the same payment banked into that
    -- account when taken FIFO and into the primary account when the very
    -- same dues were selected by hand.
    v_legs      JSONB := '{}'::JSONB;
    v_leg_bank  INT;
    v_leg       RECORD;
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN RAISE EXCEPTION 'Amount must be > 0'; END IF;

    SELECT society_id INTO v_society_id FROM apartments WHERE id = p_apartment_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Apartment not found'; END IF;

    SELECT id INTO v_fallback_int_acc FROM accounts
    WHERE society_id = v_society_id AND name ILIKE '%Due Interest%' AND drcr_account = 'Cr' LIMIT 1;

    SELECT id INTO v_maint_acc_id FROM accounts
    WHERE society_id = v_society_id AND name ILIKE '%Society Maintenance Charge%' AND drcr_account = 'Cr' LIMIT 1;

    IF v_maint_acc_id IS NULL THEN
        RAISE EXCEPTION 'Maintenance account not found for society %', v_society_id;
    END IF;

    v_bank_acc := fn_resolve_bank_leg(v_society_id, p_mode);
    v_journal_id := NEXTVAL('seq_transaction_number');

    -- Receipt first, as the voucher's source document — see the note in
    -- fn_apply_apartment_dues_fifo_core. Citing the first selected bill made
    -- any all-cash selective payment spanning more than one bill (or paying
    -- more than the first bill) fail the cash-vs-document check at commit.
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
        p_source_table := 'receipts';   -- every leg below cites the receipt, not a bill
        p_source_id    := v_receipt_id;
    END IF;

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

        v_pay_int  := LEAST(v_remaining, v_row_int);
        v_pay_prin := LEAST(v_remaining - v_pay_int, v_row_prin);
        v_take     := v_pay_int + v_pay_prin;
        IF v_take <= 0 THEN CONTINUE; END IF;

        UPDATE receivables
             SET paid_amount    = rec.paid_amount + v_take,
                 paid_principal = rec.paid_principal + v_pay_prin,
                 status         = CASE WHEN rec.paid_amount + v_take >= rec.amount
                                        THEN 'paid' ELSE 'partial' END,
                 confirmed_by   = COALESCE(p_confirmed_by, rec.confirmed_by),
                 confirmed_at   = NOW()
             WHERE id = rec.id;

        v_total_take := v_total_take + v_take;
        IF v_src IS NULL THEN v_src := rec.id; END IF;
        v_remaining  := v_remaining - v_take;

        -- Attribute this row's money to whatever bank account its own
        -- acc_id maps to (falls through to the society's primary account
        -- via v_bank_acc when the account has no mapping, and to no leg at
        -- all in cash mode).
        v_leg_bank := COALESCE(fn_resolve_bank_leg(v_society_id, p_mode, rec.acc_id), v_bank_acc);
        IF v_leg_bank IS NOT NULL THEN
            v_legs := v_legs || jsonb_build_object(
                v_leg_bank::TEXT,
                COALESCE((v_legs ->> v_leg_bank::TEXT)::NUMERIC, 0) + v_take
            );
        END IF;
    END LOOP;

    IF v_total_take > 0 THEN
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Cr', CURRENT_DATE, fn_resolve_sdr_leg(v_society_id, p_mode), p_apartment_id, 'apartment',
            COALESCE(p_particulars, 'Selective Maintenance Payment'),
            v_total_take, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src), v_journal_id
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
            v_remaining, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src), v_journal_id
        ) RETURNING id INTO v_trx_id;
        IF v_first_trx_id IS NULL THEN v_first_trx_id := v_trx_id; END IF;
    END IF;

    -- Overpayment is a maintenance receipt, so it belongs on the primary
    -- account (maintenance is not a mapped fund).
    IF v_remaining > 0 AND v_bank_acc IS NOT NULL THEN
        v_legs := v_legs || jsonb_build_object(
            v_bank_acc::TEXT,
            COALESCE((v_legs ->> v_bank_acc::TEXT)::NUMERIC, 0) + v_remaining
        );
    END IF;

    -- Dr: cash / bank paired side, one leg per distinct mapped account.
    -- Identical total to the single-leg version it replaces.
    FOR v_leg IN
        SELECT e.key::INT AS bank_acc, e.value::NUMERIC(15,2) AS amt
          FROM jsonb_each_text(v_legs) e
         WHERE e.value::NUMERIC > 0
         ORDER BY e.key::INT
    LOOP
        INSERT INTO transactions(
            society_id, entry_side, trx_date, acc_id, entity_id, role, acc_particulars,
            amount, mode, status, created_by, created_at, source_table, source_id, journal_id
        ) VALUES (
            v_society_id, 'Dr', CURRENT_DATE, v_leg.bank_acc, p_apartment_id, 'apartment',
            'Cash received - Selective Payment',
            v_leg.amt, p_mode, 'paid', p_confirmed_by, NOW(), p_source_table, COALESCE(p_source_id, v_src, v_first_trx_id), v_journal_id
        );
    END LOOP;

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

    RETURN QUERY SELECT v_first_trx_id,
        (p_amount - v_remaining)::NUMERIC(15,2),
        v_remaining::NUMERIC(15,2),
        v_journal_id,
        v_receipt_id;
END;
$$;
