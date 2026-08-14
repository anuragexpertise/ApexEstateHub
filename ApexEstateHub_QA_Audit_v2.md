# ApexEstateHub — Functional Audit v2 (re-pull + new checks)
Repo re-cloned fresh: commit `257158e` (2026-08-14 01:33:52 +0530) — confirmed newer than the v1 audit.
This is a delta on top of `ApexEstateHub_QA_Audit.md`: (1) re-verifies every v1 finding against the new commit, then (2) covers the four new checks you asked for — vendor Passes "buy" KPI, profile-form prefill, and form banners on Concern/Poll (and the adjacent New-Channel form).

---

## 1. Re-verification of v1 findings — all P0/P1 button issues are now fixed

| Finding (v1) | Status now | Where it's wired |
|---|---|---|
| `master-create-society-btn` dead | ✅ Fixed | `admin_callbacks.py:41` |
| `master-clear-btn` dead | ✅ Fixed | `admin_callbacks.py:91` |
| `poll-clear-btn` dead | ✅ Fixed | `poll_callbacks.py:162` |
| `drill-back-btn` dead | ✅ Fixed | `shell_callbacks.py:927,941` |
| `close-forgot-modal` dead | ✅ Fixed | `login_callbacks.py:285` |
| `close-reset-modal` dead | ✅ Fixed | `login_callbacks.py:296` |
| `channel-create-btn` + form dead | ✅ Fixed (rebuilt) | Channel creation was restructured to use the same generic drilldown "New" pattern as every other entity (`registry.py` now lists `channel` in `_NO_AUTO_ACTIONS`; `renderers.render_form_channel_new()` → generic `form-submit` button → `drilldown_callbacks.py:2424 → _save_channel()`). The old standalone `channel-create-btn` no longer exists in the layout at all — it was replaced, not patched. |
| Push notification gap on channel events | ✅ Fixed | `_save_channel()` now calls `PushService.notify_channel_created(...)`, and the channel-approval callback in `channel_callbacks.py` sends a push to every subscriber on approval. |
| Owner/Vendor `cashbook` tabs — 0 KPIs | ❌ Still open | `card_catalogue.py` — `owner.cashbook` and `vendor.cashbook` are still `[]`. Not touched by this commit. Recommend the same fix as v1 (mirror `security.cashbook`'s `kpi_receipts_month`/`kpi_expenses_month`, scoped to the logged-in owner/vendor). |

**Net result: everything flagged P0 in v1 is resolved.** Only the empty-KPI cashbook tabs remain open from the original pass.

---

## 2. Vendor Passes tab — "Buy Pass" KPI check

**Current state:** `vendor.vendor_passes` tab has exactly one KPI, `kpi_my_pass_expiry` ("Pass Expiry" — shows the latest `valid_until` date from the vendor's own active pass). It is **read-only**, not a call-to-action.

**Does buying a pass actually work?** Yes, but indirectly:
1. Vendor clicks the `kpi_my_pass_expiry` card on the Passes tab.
2. It drills into `list_vendors` (correctly scoped to the vendor's own record only).
3. On their own profile card, a **"Buy Pass"** button is present (`profile_actions.py`, `action_id: buy_vendor_pass`, `roles: ["vendor"]`) → opens `form_vendor_pass_new` → `fn_sell_vendor_pass(...)`. This is fully wired end-to-end.

**The gap:** the path works, but it's a 2-hop journey (KPI → own profile → find the Buy Pass button among other profile actions) rather than a direct call-to-action from the Passes tab itself. A vendor with an expired pass has no visual cue on the Passes tab telling them to act — the KPI just shows a date, and if it's in the past there's no color/urgency change to prompt the "Buy Pass" click.

**Recommendation:** either
- (a) add a second, dedicated KPI card to `vendor.vendor_passes` (e.g. `kpi_buy_pass` styled as an action card) that routes straight to `form_vendor_pass_new`, or
- (b) at minimum, make `kpi_my_pass_expiry` visually flag "Expired" (red) vs. "Expires in N days" (amber under some threshold) vs. green, since the underlying date data already supports it — this at least tells the vendor *why* they need the 2-hop path.

---

## 3. Profile form prefill — verified working

Traced the actual data path rather than assuming:

- Every entity's **Edit** action goes through one shared branch in `drilldown_callbacks.py` (`trig_type == "list-edit"`): it calls `loaders.load_profile(singular, pk, sid)` to pull the **real current row** from the DB, then `nav_state.navigate_to(..., prefill=record, ...)`.
- `renderers.render_form_card()` receives that `prefill` dict and populates every field with `prefill.get(fid)` — so whatever the DB has is what shows in the input.
- New-entry forms (no `prefill["id"]`) instead layer in `schema_introspect.py`'s `_NEW_FORM_DEFAULTS` (e.g. `events.open_to` defaulting to `"all"`) without clobbering anything the caller explicitly set — so New and Edit share one code path without New accidentally showing stale data.
- Self-service profile editing is explicitly permitted per role (`_PORTAL_PERMS`): `("apartment","apartments"): {"view","edit"}`, `("vendor","vendors"): {"view","edit"}`, `("security","security"): {"view","edit"}` — all route through the same prefill mechanism above, so an owner/vendor/security user editing their own profile gets the same guaranteed-fresh prefill as an admin editing anyone else's.

**No prefill bugs found in the generic path.** One thing worth a live click-test rather than static review: the **Poll** edit form is hand-built (`poll_page.py`, bypasses the generic form builder because of its variable 2–5 choice count) — I confirmed its `prefill.get(...)` calls cover every field (title, description, ends_at, choice_count, choice_1–5), so it *should* prefill correctly, but since it's bespoke code rather than the shared path, it's the one form worth manually re-verifying against a real edit.

---

## 4. Form banners — Concern and Poll (and New Channel, checked for consistency)

| Form | Banner present? | What it says |
|---|---|---|
| **New Concern** (Owner self-service + Admin's flat-picker version, both `form_concern_new`) | ✅ Yes — two banners | 1) If raised by an owner: a locked-flat notice — *"This concern will be raised for your own flat."* (shown only when creating, hidden on edit). 2) An expectation-setting wait banner — *"Submitted — please wait for bids from vendors/security. Once bids arrive, the Invite and Assign buttons below will let you pick a candidate."* |
| **Concern profile** (existing concern) | ✅ Yes | Status banner (color-coded by lifecycle stage) +, for the viewer's own assignment, a second banner showing their bid/stage. |
| **New Poll** | ⚠️ Partial | Only a plain grey `<small>` caption under the title — *"Admin-only: create a new poll for your society"* (or, on edit, *"choices can't be changed once someone has voted"*). This is real guidance text, not missing entirely, but it's styled as a low-contrast caption rather than the colored `dbc.Alert` banner used everywhere else in the app, so it's easy to miss and doesn't match the app's own visual language for "important thing to read before you submit." |
| **Poll profile** (existing poll) | ✅ Yes | Color-coded status banner — 🏆 *"Results Declared"* or *"Voting Closed — results not yet declared"*. |
| **New Channel** | ❌ None | No banner at all on the creation form — just field labels/placeholders. Given a channel requires the admin to later mark it active/approve subscribers, a one-line banner (*"New channels start inactive until approved"* or similar, if that's how it actually behaves — worth confirming against `_save_channel()`'s default `active` value) would match the pattern set by Concern/Receipt forms. |
| **New Receipt / New Event** | ✅ Yes | Payment QR banner (`_payment_qr_banner`) so the payer can scan-and-pay directly from the form. |

**Recommendation:** for consistency, upgrade the New Poll caption to a `dbc.Alert` (reuse the same light/colored style already used for concern/channel/poll-profile banners), and add a one-line creation-context banner to New Channel — both are cosmetic/UX, not functional bugs, but every other "New X" form in the app now has one and these two are the odd ones out.

---

## 5. Updated priority list

1. **P1** — Owner/Vendor `cashbook` empty-KPI tabs (only unresolved item carried over from v1).
2. **P2** — Vendor Passes tab: add urgency styling or a direct "Buy Pass" KPI so the existing 2-hop flow isn't the only signal.
3. **P3** — New Poll banner upgrade (caption → `dbc.Alert`) for visual consistency.
4. **P3** — New Channel: add a short banner explaining post-creation state (pending approval / active immediately — confirm actual behavior first).
5. **Manual re-check recommended** — Poll Edit form (bespoke code path, not the generic prefill mechanism) against a real edit in a running instance.

Everything else from the original seven test scenarios (A–G) in `ApexEstateHub_QA_Audit.md` still applies — Scenario A (society onboarding) and Scenario E (channels) should now both run cleanly end-to-end given the button fixes above.
