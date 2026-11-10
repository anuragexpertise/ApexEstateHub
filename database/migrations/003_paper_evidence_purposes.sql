-- Extend onboarding_evidence.purpose for reusable paper-sign workflow (onboarding/adoption).
-- Safe to run more than once.
DO $$
DECLARE c RECORD;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
              WHERE conrelid = 'onboarding_evidence'::regclass AND contype = 'c'
                AND pg_get_constraintdef(oid) ILIKE '%purpose%'
    LOOP
        EXECUTE format('ALTER TABLE onboarding_evidence DROP CONSTRAINT %I', c.conname);
    END LOOP;
    ALTER TABLE onboarding_evidence
        ADD CONSTRAINT onboarding_evidence_purpose_check CHECK (purpose IN (
            'bank_statement','cash_count','audited_report','review_letter','paper_signature',
            'pending_receivables','tds_rates','declaration_undivided_interest','brought_forward',
            'account_statement','election_results','apartment_charges','bulk_apartments','bulk_vendors',
            'bulk_security','bulk_supervisor','bulk_staff','adoption_resolution','other_paper_evidence',
            'registration_certificate','ca_rates_letter','adoption_minutes','adviser_appointment_letter'
        ));
END $$;
