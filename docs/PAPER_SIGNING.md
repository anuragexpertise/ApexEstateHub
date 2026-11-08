# Paper signing workflow

One reusable flow for every dataset that must be signed on paper and evidenced:

```
fill data (grid / xlsx upload)  ->  make_document(): server-side PDF with signing footer
   ->  download / print / sign / scan  ->  upload signed scan (PDF/PNG/JPG, max 5 MB)
   ->  server SHA-256  ->  onboarding_evidence row, bound to the generated document
```

Code: `app/services/paper_evidence.py` (flow), `onboarding_service.store_evidence_file / record_document / latest_document`
(storage), `xlsx_templates.py` (templates and validators).

## Three hashes tie the paper to the data

| Hash | What | Where |
|---|---|---|
| `snapshot_sha256` | the exact rows, extra sections and meta lines that were printed (no dates, no renderer) | `onboarding_documents`, copied to the evidence row |
| `document_sha256` | the generated, unsigned PDF | `onboarding_documents`, copied to the evidence row |
| `sha256` | the signed scan the user uploaded | `onboarding_evidence` |

Every PDF page carries the **Doc ID** (`EH-<society>-<PURPOSE>-<snapshot8>`), the first 16 hex of the data hash and
"Page x of y". The Doc ID is deterministic: the same data prints with the same ID.

**Stale evidence.** `evidence_status(..., current_snapshot=...)` compares the data as it is now with the snapshot that was
signed. If the entries changed after signing, the screen says so and asks for a new print, signature and scan. Wired for:
pending receivables, election results, bye-laws adoption. The other flows are bound (Doc ID, both hashes) but compare only
when their caller passes `current_snapshot`.

A scan uploaded with no generated document on file is still stored, but marked **not linked**.

## Flows

| Use | purpose | Print / scan wired in |
|---|---|---|
| Election Results (President, Secretary, Treasurer, Grievance officer) | `election_results` | `onboarding_callbacks.py` |
| TDS Rates (CA signs; per-row effective date) | `tds_rates` | `onboarding_wizard_callbacks.py` |
| Declaration of Undivided Interest, Part A (+ apartment-wise table) | `declaration_undivided_interest` | `onboarding_wizard_callbacks.py` |
| Brought Forward (any As-on date) | `brought_forward` | `onboarding_wizard_callbacks.py` |
| Pending receivables (ties to Sundry Debtors) | `pending_receivables` | `onboarding_wizard_callbacks.py` |
| Account statements (bank / deposit / cash, same As-on date) | `account_statement` | `onboarding_wizard_callbacks.py` |
| Bulk enrol: Apartments, Vendors, Security, Supervisor, Staff (others: `other_paper_evidence`) | `bulk_*` | `bulk_enroll_callbacks.py` |
| Adoption of bye-laws 1-58 (`Society_bye_laws.xlsx`) | `adoption_resolution` | `paper_sign_callbacks.py` |

The bulk register prints every column of the upload except `password`, and the SHA-256 of the uploaded xlsx.

## Adding another document

1. Add the purpose to `EVIDENCE_PURPOSES` (onboarding_service.py), to the CHECK list in `estatehub.sql` (inline, no ALTER),
   and to a migration for existing databases.
2. Build `(headers, rows, signers, meta_lines)` in one function and use it for both print and the stale check.
3. Print: `doc = pe.make_document(sid, purpose, uid, title, society_name, subtitle, headers, rows, signers, meta)` then
   `dcc.send_bytes(doc["data"], doc["filename"])`. Pass `sections=[...]` for extra tables and `kind=` when several
   documents share one purpose.
4. Scan: `pe.store_signed_scan(sid, purpose, uid, filename, contents, meta, kind=...)`; show `pe.stored_message(ev)`.
5. Status: `pe.status_line(pe.evidence_status(sid, purpose, current_snapshot=pe.snapshot_hash(...)))`.
6. Classify the new callbacks in `docs/authz_manifest.json` (`scripts/inventory_endpoints.py --check`).

## Fonts

`reportlab` ships Helvetica, which has no rupee sign: with it the PDF prints `Rs.`. If DejaVu Sans is installed
(`/usr/share/fonts/truetype/dejavu/`), or placed in `app/assets/fonts/DejaVuSans.ttf` + `DejaVuSans-Bold.ttf`, or pointed
to by `ESTATEHUB_PDF_FONT` / `ESTATEHUB_PDF_FONT_BOLD`, the PDF uses it and prints the rupee sign and Devanagari. If
`reportlab` is not installed, `make_document` falls back to the printable HTML (`fmt = "html"`).

## Later signing modes

`SIGNING_MODES = ("paper",)`; `make_document(signing_mode=...)` refuses anything else today.

* **password mode**: `document_signing.py` already stores each signer's own-password confirmation with the SHA-256 of the
  exact item text. Use `snapshot_sha256` as that item text hash, so the paper and password routes sign the same thing.
* **eSign mode**: `esign_adapter.py` already has `aadhaar_eSign`, `dsc` and `paper` methods; for `paper` its `evidence_ref`
  is the scan's SHA-256, which is the `sha256` stored here.

## Existing databases

Run `python3 database/apply_migration.py` (003 adds the purposes, 004 adds `onboarding_documents` and the binding columns).
A fresh database gets everything from `estatehub.sql`.
