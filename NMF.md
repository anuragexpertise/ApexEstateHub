# NMF: Follow-up Plan for Nemotron (on top of `1384ffe`)

## Ground rules

1. Work on top of `1384ffe`. Don't touch what is already working: the roll-up contract, the screen layout and labels, `seed.py`, `bf_controls.py`, and the statement importer.
2. One commit per task, with the task number in the message.
3. After every task, run the full suite and lint. Lint must stay at or below 30 errors, and the new code must add none.
4. If the original plan is silent on a point, don't invent behaviour. List the question in your report.

---

## Task A: Fix the as-on date and year in the template download

**File:** `onboarding_wizard_callbacks.py` (~lines 462-463).

1. `ob.load_draft(sid)` already returns the draft. Remove the second `.get("draft")`, so the code reads `bf = draft.get("brought_forward") or {}`.
2. Check every other use of `load_draft` in the app for the same double unwrap, and fix any you find.

**Tests:** save a draft with a financial year and an as-on date, call the download callback, open the returned workbook, and assert that the sheet name is that year and the `as_on_date` column holds that date. Add a second case with no saved draft that asserts the fallback year.

---

## Task B: Make the Apt-Arrears importer strict (`pending_receivables.py`)

1. **Reject the old format.** When a financial year is given, a file with the old `Receivables` sheet or the old `flat_number` / `overdue_days` headers must fail with a clear message. Say what is wrong and tell the user to download a fresh template.
2. **Reject the wrong sheet.** If no sheet is named for the financial year, fail and name the expected sheet. Don't fall back to the first sheet.
3. **Fix date cells.** Accept `as_on_date` as text, `date`, or `datetime`. Normalise it to an ISO date (`YYYY-MM-DD`) before comparing it with the wizard's as-on date. A real Excel date cell must not cause a false error.
4. **Keep per-row error messages** in the same style as the statement importer.

**Tests:**
- Round trip: build the template, fill it, import it, and check the rows.
- A date cell, a text date, and a `datetime` cell all pass when they match.
- A wrong date fails with the row number.
- The old format fails with the clear message.
- A wrong-year sheet fails with the clear message.

---

## Task C: Remove leftover legacy code

1. Remove the legacy mode of `build_template` (`fy=None`, the `Receivables` sheet, the old columns), since nothing calls it. Make `fy` required.
2. Fix the Instructions sheet. Use the real column names: `flat_no`, `amount`, `due_days`, `remarks`, `as_on_date`.
3. Make the grid header and the template header use the same name, `due_days`. Keep the internal field name `overdue_days` only if the saved data needs it, and say so in a code comment.
4. Run `grep -rn "Receivables\|flat_number\|overdue_days"` over `app/services` and the wizard files. Every hit must be intentional.

**Tests:** the template has no sheet named `Receivables`, and the Instructions text matches the header row.

---

## Task D: Add the missing tests

Use Dash callback context tests or direct function calls. Don't use a live database unless the test is marked as live.

1. **Roll-up callback (`sw_bf_rollup`):**
   - Edit a cell and check the group totals, the two side totals, and all three Annex C controls.
   - Nested groups: totals land on the right heading when the row order changes.
   - Blank and non-numeric cells don't crash it.
2. **Controls panel on first load:** build the Brought Forward screen with no saved data, and assert the panel is present. Build it again with saved data, and assert the statuses are correct.
3. **Next keeps arrears:** fill arrears from a file, click Next, reload, and assert the rows are still there. Click Next with an untouched grid and assert saved rows aren't erased.
4. **Add row and total:** add a row, edit amounts, delete a row, and check the total after each step. Include a blank new row where the amount is `""`, and make sure the total callback doesn't crash on it.
5. **Arrears control:** `arrears_tie` passes when the totals match, and fails with the "does not match" message when they differ.
6. **Screen order and labels:** render the screen and assert the order of its sections and the exact text of each button.

---

## Final verification

1. Run the full suite. Everything must pass, with no new skips.
2. Run lint. Errors must be at or below 30, and the new code must add none.
3. Report one line per task (A to D) with the commit and the tests that cover it.
4. List any spec question you had to leave open, and any test you couldn't write.
