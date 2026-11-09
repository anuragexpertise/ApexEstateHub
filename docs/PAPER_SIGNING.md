# Paper signing workflow (after onboarding simplification)

After the onboarding simplification, the print-sign-scan loops for generated forms (Election Results data, TDS rates,
Part A declaration, pending receivables, brought forward, bulk enrolment registers, bye-law adoption list) are removed.
The Agreement with its sealed annexes is the only instrument signed. Scanned third-party originals are uploaded directly as
evidence; nothing is printed and signed separately.

Three remaining paths use signed scans:

| Path | What is signed | How |
|---|---|---|
| Agreement paper mode | The Agreement text with annex hashes | `agreement_print_html()` → print, sign, scan → `store_evidence_file(..., "paper_signature")` |
| Builder's Declaration | The builder's Declaration PDF + workbook | `undivided_declaration.apply()` → stores Declaration evidence |
| Plain evidence uploads | Registration certificate, bank statements, cash count, audited report, review letter, election minutes, adoption minutes | `store_evidence_file()` directly (no `make_document`) |

The reusable `paper_evidence.py` flow (`make_document`, `store_signed_scan`, `snapshot_hash`, `record_document`,
`onboarding_documents`) is retained but is no longer used by any onboarding loop. It remains available for any future
paper-signing need.

## Three hashes tie paper to data (retained for reference)

| Hash | What | Where |
|---|---|---|
| `snapshot_sha256` | the exact rows printed | `onboarding_documents`, copied to evidence row |
| `document_sha256` | the generated unsigned PDF | `onboarding_documents`, copied to evidence row |
| `sha256` | the signed scan uploaded | `onboarding_evidence` |

## Evidence purposes (all three allow-lists must stay in sync)

`onboarding_service.EVIDENCE_PURPOSES`, the CHECK constraint in `database/estatehub.sql`, and
`database/migrations/003_paper_evidence_purposes.sql`.

Current values: `bank_statement`, `cash_count`, `audited_report`, `review_letter`, `paper_signature`,
`pending_receivables`, `tds_rates`, `declaration_undivided_interest`, `brought_forward`, `account_statement`,
`election_results`, `apartment_charges`, `bulk_apartments`, `bulk_vendors`, `bulk_security`, `bulk_supervisor`,
`bulk_staff`, `adoption_resolution`, `other_paper_evidence`, `registration_certificate`, `ca_rates_letter`,
`adoption_minutes`.

## File limits

PDF, PNG, JPG, JPEG; max 5 MB; magic-byte check. These limits are unchanged.
