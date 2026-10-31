# APEXESTATEHUB SOCIETY ONBOARDING AGREEMENT (v5)

This Agreement is a two-party contract between:

**1. The Society** — a residential / commercial apartment owners' association (or registered society / co-operative) registered under the applicable law, acting through its Managing Committee. The society is the Data Fiduciary for the personal data of its owners, tenants, vendors and guards.

**2. The Platform Operator** — EsateHub LLP, a limited liability partnership registered in Agra, Uttar Pradesh (the "Operator"), represented for this Agreement by its authorised signatory. The Operator is the Data Processor for the society's books on the ApexEstateHub platform.

Together, the "Parties".

## 1. Authority to contract

The three office-bearers who sign for the society — the President, the Secretary and the Treasurer — are authorised by a resolution of the society's Managing Committee (the "Authorising Resolution"), a copy of which forms part of the onboarding record. The Authorising Resolution names each signer and the office they hold on the signing date.

## 2. Licence and term

Subject to this Agreement, the Operator grants the society a non-exclusive, non-transferable licence to use the ApexEstateHub society-management software for the purpose of managing the society, for the plan and validity recorded in the society's master record, renewable on the terms therein. Fees and renewal are as set out in the master record.

## 3. Society duties

The society is responsible for the accuracy of entries made in its books, for keeping its books, and for the conduct and responsibilities of its advisers (auditor, CA, advocate) appointed under this Agreement.

## 4. Data protection (Digital Personal Data Protection Act, 2023)

The society is the Data Fiduciary and the Operator is the Data Processor for the personal data the society processes on the platform. This data-processing part is a written contract required between fiduciary and processor. It covers:

- the personal data and purposes for which the Operator processes on the society's behalf;
- security safeguards, including encryption at rest on the host and role-based restriction of ID-proof and photo images;
- named sub-processors (any eSign vendor, cloud host, SMS/push provider);
- breach intimation to the society without delay, and to affected people where required;
- return or deletion of the society's data on exit, subject to retention holds for audits and disputes;
- audit rights of the society over the Operator's processing.

Processing logs are kept for at least one year under the DPDP Rules.

The society answers rights requests (access, correction, erasure, grievance, nominee) within the response period recorded in its DPDP legal-review register (default 30 days, marked [Verify] pending legal review). The lawful basis for dues and gate-safety records is legitimate use; announcements are consent-based and can be switched off.

## 5. Key custody

The Operator's platform can use the society's signing keys only for the purposes for which the society authorises them. Whoever controls the host and the database can technically sign as any society; the Operator states this limit and does not claim otherwise. Key rotation requires the Secretary and the Treasurer (two different people).

## 6. eSign and execution formalities

The Operator offers eSign through a vendor-neutral adapter (the reference vendor is Leegality, Basic Plan). Each society sets a per-society "eSign required" toggle (default No). While it is Off, the Agreement is signed by each signer's own login password confirmation (which records who confirmed and when; it is evidence, not a legal electronic signature). While it is On, a password confirmation is refused and the Agreement must be signed through the eSign adapter (Aadhaar eSign primary / DSC fallback for office-bearers; DSC primary / Aadhaar eSign fallback for the Operator's authorised signatory), with the vendor's evidence reference stored alongside the signature.

Stamp duty payable in Uttar Pradesh on this Agreement is a flat Rs 100; the SaaS subscription to the society attracts GST at 18%. Stamping evidence is recorded as part of the sealed Agreement.

Execution requires four signatures, in this order:

1. President — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
2. Secretary — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
3. Treasurer — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
4. Operator's authorised signatory — DSC (fallback: Aadhaar eSign, if accepted for a company)

Each signature records its method (`password`, `aadhaar_eSign`, `dsc`, `paper`) in the signature record. A password confirmation records who acted and when; it is evidence, not the legal signature.

Signing is blocked until `OPERATOR_LEGAL_NAME` and `OPERATOR_ADDRESS` are set in the Operator's environment.

## 7. Liability, indemnity and disputes

The liability, indemnity, governing law and forum clauses agreed between the Parties apply (clauses 2 and 4 of the prior form, revised for this Agreement). Disputes are subject to the governing law and forum stated therein.

## 8. Exit

On exit, the society may export its books. Deletion follows a schedule agreed at exit, with a hold for audits and disputes. Erasure blanks a person's profile (name, photo, ID proof, mobile) and never touches ledger lines, so the hash chain stays valid.

## 9. Annexes (sealed with this Agreement)

Each annex below is rendered into the sealed text of this Agreement and stored with its own SHA-256. Each signature binds the hash of the exact text, annexes included; any change to the text or an annex after a signature voids the signatures already given.

| Annex | Declares |
|-------|----------|
| **A — Regime** | State, constitution, the legal regime that follows (e.g. `UP_AOA_2010`), funds opted into, Model Bye-Law clauses adopted / varied / not adopted (provisional until a General Body resolution passes). |
| **B — Review** | The wizard's Review page as a frozen snapshot: tax rates and TAN, GST, charges, accounts, office-bearers. TDS and GST rates marked pending the CA's confirmation. |
| **C — Opening financial position** | As-at date and financial year; every opening balance; fund-by-fund statement; arrears by flat. Posted as the opening journal when this Agreement seals. Opening arrears are turned into per-flat opening-due receivables at activation, and the society's first ledger anchor is taken at activation. |

## 10. Severability

If any provision of this Agreement is held void, invalid, unenforceable or illegal, the other provisions continue in full force and effect.
