# Edits to "ApexEstateHub Gold-Standard Plan v5 Society Onboarding.md"

Four edits. Apply them in order. Nothing else in the plan changes.

---

## Edit 1: new section, insert immediately before `## Founding committee, enrollment and adoption`

## eSign vendor and signing methods

**Reference vendor: Leegality, Basic Plan, subject to the checks below.** This rests on the vendor's published pricing page and search snippets. No contract, sandbox or account has been opened, so every figure needs reconfirming. Leegality is the reference for the design, not a lock-in: the code talks to an adapter with one interface (create request, check status, fetch signed document), so another vendor can replace it.

| Item | What the vendor's pages say | Cost for one society |
| --- | --- | --- |
| Licence | Zero licence fee on the Basic Plan, which includes Aadhaar eSign, digital stamping and API access | 0 |
| Aadhaar eSign | INR 25 per signatory; minimum purchase INR 100 of credits; pay only for successful eSigns | About INR 100 for the four signatures |
| Non-Aadhaar eSign | INR 15 per signatory | n/a |
| Digital stamping | INR 45 per stamp paper, plus stamp duty, plus INR 500 per stamp order; Uttar Pradesh appears in its state list **\[Verify\]** | INR 545 plus duty, if the advocate says the Agreement needs stamping |

**Signing methods by signer**

| Signer | Primary | Fallback |
| --- | --- | --- |
| President, Secretary, Treasurer | Aadhaar eSign | Digital signature certificate (DSC), then signed paper with the scan's SHA-256 |
| Operator's authorised signatory | DSC | Aadhaar eSign, if the advocate accepts it for a company |

The password confirmation stays in every case as evidence of who acted and when. It is not the legal signature.

**Where the vendor is used in v5**

| Record | Method | Why |
| --- | --- | --- |
| Agreement | eSign (Aadhaar or DSC) | The licence, the data-protection terms and the society's declared position |
| Adviser appointment | eSign (Aadhaar or DSC) | A contract carrying a confidentiality undertaking |
| Legacy resolution import, resolutions, minutes, polls | Password confirmation, as today | Signed paper minutes remain the legal record; eSign on every resolution adds cost and friction |
| Expenses, fund withdrawals | Password confirmation | Routine approvals; an Aadhaar OTP for each is not proportionate |
| NOC | Password confirmation in v5 | An NOC a bank or registrar relies on could move to eSign later, as a separate decision |

Each signature records its method in `document_signatures.method` (`password`, `aadhaar_eSign`, `dsc`, `paper`), so the sealed Agreement shows how each person signed.

**Questions to put to the vendor before signing up**

1. Is there a free sandbox, and does it cover sequential multi-signer on one document?
2. Does the callback return the Aadhaar-verified name, so it can be matched to the office-bearer on record?
3. Is Uttar Pradesh stamping available on the Basic Plan, and which network serves it?
4. Does the vendor receive the PDF, and where is it stored? If yes it is a sub-processor, named in the Agreement's data-protection part.
5. Can the operator's signatory sign as an organisation with a DSC through the vendor?
6. Is the Verifier API usable for the public verification page?

---

## Edit 2: build plan, insert this row after the V5.6 row

| V5.6b | eSign adapter (reference vendor Leegality): `esign_requests` table, `signer_policy.signature_method`, `document_signatures.method` and `evidence_ref`, a deterministic PDF of the text and annexes with the item hash embedded, an authenticated and idempotent callback, an expiry job, and the DSC and paper fallbacks | The Agreement cannot seal until each of the three office-bearers has signed by the method the policy requires; a callback with a wrong hash or signer is refused; the signed PDF re-verifies | L | V5.6, decision 3 |

## Edit 3: build plan, three small changes

- The sentence "Thirteen tasks" becomes "Fourteen tasks".
- In the V5.7 row, the Depends-on cell becomes: `V5.1, V5.5, V5.6, V5.6b`.
- In the V5.9 row, add to the end of the Task cell: `; the appointment is signed by the method set in V5.6b`.

---

## Edit 4: Decisions table, replace row 3

| 3 | Is Aadhaar eSign by the three office-bearers (through Leegality or a similar vendor), plus a DSC for the operator's signatory, enough for the Agreement, or must signed paper counterparts or stamping be added | The code records who confirmed by password; that is not a legal e-signature | V5.6b | Advocate |
