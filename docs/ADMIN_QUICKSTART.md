# EstateHub: Society Admin Quick Start

You are completing the one-time **Setup Wizard** for your society. Until you submit it, the dashboard stays locked for **every** role (residents, vendors and guards see "Setup Not Complete").

## Before you begin (keep these ready)

- Registration number, address, official email and phone, and your **State**.
- Logo, login-background picture (optional), Secretary's signature scan, UPI payment QR image.
- A **SIGNING_SECRET** you have chosen and stored in a password manager (see below).
- GST registration (GSTIN) and TDS deduction (TAN) details, if applicable.
- Maintenance basis (fixed amount per flat or rate per sq ft) and the billing due day.
- Last audited balance sheet: closing balances and the financial year.
- Your own login password (asked again on the last step).

The wizard has **no draft save**. Closing it logs you out and discards what is on screen (Bye-Law choices are the only thing saved immediately).

## SIGNING_SECRET

It signs every QR gate pass for your society. It must have **at least 8 characters, an uppercase letter, a lowercase letter, a digit and a special character**. You are asked for it on the last step and later for QR reissue. There is no screen to view or change it afterwards, and changing it would invalidate every printed QR code. Store it safely now.

## Things the wizard checks for you

- Address, Email, Phone and Registration number are **required**; you cannot move on or submit without them.
- Brought Forward must **balance** (total Dr = total Cr), otherwise the submit is rejected and nothing is saved.
- Dates default to the start of the current financial year (1 April). Change them if your books start elsewhere.
- Submit is all-or-nothing: if it fails, nothing is half-saved; fix the message shown and submit again.

## After you submit

1. **Change your password** (avatar menu, Account Settings). You are prompted at login until you do.
2. **Add your real bank account and mark it primary** (Settings, Accounts). It is *not* set for you, and bank receipts cannot be recorded until it is. Your payment QR must belong to this bank.
3. **Enrol people** (Enrolled tab): *New* for one record, or *Bulk Enroll* with the template (max 500 rows). Enrol apartments first, then apartment users. Passwords must be at least 8 characters; people are asked to change them on first login. Both *New* and *Bulk Enroll* stop at your plan's apartment limit.
4. **Governance** (Settings, Society governance): hold the General Body meeting, then record the Meeting and the Resolution. Recording a passed resolution **activates** the matching Bye-Law choice automatically. Save the Bye-Law choice first, then the resolution.

If you forget your password, use *Forgot password*: a reset token is emailed to you. If the server has no email configured, ask Master to relay or reset it.

**Plan validity:** paid plans stop working after the validity date plus a short grace period (7 days by default). Free plans do not expire. Contact EstateHub support to renew.
