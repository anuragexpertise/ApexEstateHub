# ESTATEHUB SOCIETY ONBOARDING AGREEMENT (v6)

This Agreement is a contract between:

**1. The Society** — a residential / commercial apartment owners' association, registered society, or co-operative housing society (together, a "housing society") registered under the applicable law (including the Uttar Pradesh Apartment Owners' Act, 2010, the Maharashtra Co-operative Societies Act, 1960, or the Tamil Nadu Apartment Owners' Act, 1994, as applicable), acting through its Managing Committee and the three office-bearers who sign below. The Society is the Data Fiduciary for the personal data of its owners, tenants, occupants, vendors, guards and staff that it causes to be processed on the Platform.

**2. The Platform Operator** — EstateHub LLP, a limited liability partnership registered in Agra, Uttar Pradesh, having its registered office as recorded in the Society's master record, represented for this Agreement by its authorised signatory (the "Operator"). The Operator is the Data Processor for the Society's books and personal data processed on the EstateHub society-management platform (the "Platform").

Together, the "Parties".

## 1. Authority to contract

The three office-bearers who sign for the Society — the President, the Secretary and the Treasurer — are authorised by a resolution of the Society's Managing Committee (the "Authorising Resolution"), a copy of which forms part of the onboarding record. The Authorising Resolution names each signer and the office each holds on the signing date. The Operator's signatory is authorised under a board / designated-partner resolution of EstateHub LLP.

No office-bearer signs in more than one capacity for the same signature line, except that one natural person may hold two offices (e.g. administrator and Secretary) and signs once per office where policy requires.

## 2. Licence and term

### 2.1 SaaS licence
Subject to this Agreement, the Operator grants the Society a non-exclusive, non-transferable, non-sublicensable licence to access and use the EstateHub society-management software, provided as software-as-a-service, solely for the purpose of managing the Society, for the plan and validity recorded in the Society's master record, and renewable on the terms therein. The Society does not acquire ownership of, or possession of a copy capable of independent exploitation of, the underlying software. The licence is a contractual permission, not a proprietary entitlement, and ends on expiry or termination of this Agreement.

### 2.2 Fees
Fees, renewal, taxes (including GST at 18% on the subscription where applicable) and payment terms are as set out in the Society's master record.

### 2.3 Indian law context
The licence is governed by the Indian Contract Act, 1872. Access to and use of the Platform is an electronic contract under the Information Technology Act, 2000. The Operator's rights in the Platform and its content are protected under the Copyright Act, 1957; nothing in this Agreement assigns any intellectual property to the Society.

## 3. Society duties

The Society is responsible for:
- the accuracy of entries made in its books on the Platform;
- keeping its books and appointing its auditors, CA and advocate;
- the conduct of its advisers appointed under this Agreement;
- maintaining accurate flat-owner rosters and role-based access privileges;
- providing accurate resident, tenant, vendor and guard details where required.

## 4. Data protection (Digital Personal Data Protection Act, 2023 and Rules, 2025)

### 4.1 Roles
The Society is the Data Fiduciary and the Operator is the Data Processor for the personal data the Society processes on the Platform. This data-processing section is a written contract between the fiduciary and the processor, as contemplated by the Digital Personal Data Protection Act, 2023 ("DPDP Act") and the Digital Personal Data Protection Rules, 2025 ("DPDP Rules").

### 4.2 Scope of processing
The Operator processes, on the Society's behalf and on its documented instructions: (a) names and contact details of owners, tenants, occupants, vendors, guards and staff; (b) flat and dues records; (c) gate / visitor logs; (d) consent and grievance records; and (e) such other categories of personal data as the Society causes to be entered, for the purposes of providing the Platform services.

### 4.3 Processor obligations
The Operator shall:
- process personal data only for the purposes and in the manner instructed by the Society;
- maintain named sub-processors (including any eSign vendor, cloud host and SMS / push provider) under written data-processing terms no less protective than this Agreement;
- implement reasonable security safeguards, including encryption at rest and role-based restriction of identity-proof and photo images;
- intimate the Society of any personal-data breach without undue delay (and in any event within the period required by applicable law), and to affected data principals where required;
- on exit or termination, return or delete the Society's personal data, subject to retention holds for audits, disputes and statutory requirements;
- allow the Society audit rights over the Operator's processing to the extent set out in the master record.

### 4.4 Society obligations
The Society shall respond to data-principal rights requests (access, correction, erasure, grievance, nomination) within the period recorded in its DPDP register (default 30 days, marked pending legal review). The lawful basis for dues and gate-safety records is legitimate use; announcements and marketing are consent-based and may be switched off.

Processing logs are retained for at least one year under the DPDP Rules, subject to any applicable hold.

## 5. Key custody

The Platform holds signing keys for each Society (per-purpose wrapped keys for NOC, agreement, adviser appointment and ledger anchoring). The Platform can use a Society's signing keys only for the purposes the Society authorises. Whoever controls the host and the database can technically sign as any Society; the Operator states this limitation and does not claim otherwise. Key rotation requires two different office-bearers (the Secretary and the Treasurer).

## 6. eSign and execution formalities

### 6.1 eSign
The Operator offers electronic signing through a vendor-neutral adapter (the reference vendor is Leegality, Basic Plan). Each Society sets a per-Society "eSign required" toggle (default No). While it is Off, a document is signed by each signer's own login-password confirmation (which records who confirmed and when; it is evidence of the act, not a legal electronic signature). While it is On, a password confirmation is refused and the document must be signed through the eSign adapter (Aadhaar eSign primary / DSC fallback for office-bearers; DSC primary / Aadhaar eSign fallback for the Operator's authorised signatory), with the vendor's evidence reference stored alongside the signature.

### 6.2 Stamp duty
Stamp duty payable in Uttar Pradesh on this Agreement is a flat Rs 100; the SaaS subscription to the Society attracts GST at 18%. Stamping evidence is recorded as part of the sealed Agreement.

### 6.3 Execution order
Execution requires four signatures, in this order:

1. President — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
2. Secretary — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
3. Treasurer — Aadhaar eSign (fallback: DSC, then signed paper whose scan's SHA-256 is recorded)
4. Operator's authorised signatory — DSC (fallback: Aadhaar eSign, if accepted for a company)

Each signature records its method (`password`, `aadhaar_eSign`, `dsc`, `paper`) in the signature record. Signing is blocked until `OPERATOR_LEGAL_NAME` and `OPERATOR_ADDRESS` are set in the Operator's environment.

## 7. Liability, indemnity and disputes

The Parties' liability, indemnity, governing-law and forum clauses apply as agreed in the master record (or the prior form, revised for this Agreement). Disputes are subject to the governing law and forum stated therein, with the Parties first attempting conciliation.

## 8. Exit

On exit, the Society may export its books. Deletion follows a schedule agreed at exit, with a hold for audits and disputes. Erasure blanks a person's profile (name, photo, ID proof, mobile) and never touches ledger lines, so the signed hash chain stays valid. The Society's data is returned or deleted subject to applicable retention holds.

## 9. Annexes (sealed with this Agreement)

Each annex below is rendered into the sealed text of this Agreement and stored with its own SHA-256. Each signature binds the hash of the exact text, annexes included; any change to the text or an annex after a signature voids the signatures already given.

| Annex | Declares |
|-------|----------|
| **A — Legal regime** | State, constitution, the legal regime that follows (e.g. `UP_AOA_2010`), funds opted into, Model Bye-Law clauses adopted / varied / not adopted (provisional until a General Body resolution passes). |
| **B — Review** | The society-setup Review page as a frozen snapshot: tax rates and TAN, GST, charges, accounts and office-bearers. TDS and GST rates marked pending the CA's confirmation. |
| **C — Opening financial position** | As-at date and financial year; every opening balance; fund-by-fund statement; arrears by flat. Posted as the opening journal when this Agreement seals. Opening arrears are turned into per-flat opening-due receivables at activation, and the Society's first ledger anchor is taken at activation. |

## 10. Miscellaneous

### 10.1 Entire agreement
This Agreement, together with the Annexes and the Society's master record, constitutes the entire agreement between the Parties on its subject matter and supersedes all prior discussions or understandings.

### 10.2 Amendment
No amendment or variation is effective unless in writing and signed by both Parties.

### 10.3 Severability
If any provision is held void, invalid, unenforceable or illegal, the remaining provisions continue in full force and effect.

### 10.4 Waiver
No waiver of any breach or default operates as a waiver of any other breach or default.

### 10.5 Notices
Notices are given as set out in the master record, or as otherwise agreed in writing between the Parties.
