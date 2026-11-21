# Corrective Plan for Nemotron: Streamlining_BF (on top of `55667ae`)

## Ground rules

1. Work on top of `55667ae`. Don't revert or rewrite the parts already verified: `seed.py`, `bf_layout.py`, `bf_controls.py`, the statement importer, and the cleanup.
2. Follow the original plan's spec wherever it covers a point. If the spec is silent or ambiguous, don't invent behaviour. List the question in your final report.
3. Every task below needs tests, because none of the screen, roll-up, or arrears code is tested yet. A task isn't done until its tests pass.
4. Make one commit per task, with a message that names the task number.
5. After every task, run the full suite and lint. Lint must stay at or below 30 errors, and the new code must add none.

---

## Task 1: Fix the roll-up contract and callback (bugs 1, 7)

**Files:** `onboarding_wizard_callbacks.py` (`sw_bf_rollup`, ~line 419), the roll-up function in `bf_layout.py`/`bf_controls.py`, and the group rendering in `setup_wizard.py`.

1. Read the roll-up function and write down exactly what it returns. Define that return shape once, as a `TypedDict` or dataclass, with these parts:
   - totals keyed by group id (not by position)
   - the grand totals
   - the Annex C control results
2. Make `sw_bf_rollup` consume only fields that this shape defines. Remove every read of a key that is never returned.
3. Match group totals to rows by **group key**, not by index or position. Put the key on each rendered group heading and total row.
4. Render nested groups as their own headings, each with its own total row. Fixed Assets and Bank A/c must both show group totals.
5. Make the callback tolerate an empty grid, a partially filled grid, and blank or non-numeric cells. It must not raise an error in any of these cases.

**Tests:**
- Unit test of the roll-up output shape.
- Callback test: edit a cell and check that group totals, grand totals, and all three live Annex C controls update.
- Test with nested groups: totals land on the right heading even when the row order changes.
- Test that blank and invalid cells don't crash.

---

## Task 2: Show the controls panel on first load (bug 8)

1. Compute and render the Annex C controls panel when the Brought Forward screen is first built, using saved data or an empty grid, not only after the first edit.
2. Use the same function that `sw_bf_rollup` uses, so initial render and later updates can't disagree.

**Tests:** build the screen with no edits and assert the controls panel is present. Then build it with saved data and assert it shows the correct statuses.

---

## Task 3: Stop wiping filed arrears (bug 2)

**Files:** `setup_wizard.py:2267`, `onboarding_wizard_callbacks.py:264`.

1. Replace `data=[]` with the arrears rows already saved for the society.
2. Make "Next" save the **grid's current contents**. It must never overwrite saved arrears with an empty list just because the grid wasn't touched.
3. After filling arrears from a file, the grid must show those rows and the total must be correct.
4. Make `arrears_tie` fail with a message that names the cause, for example "Apt-Arrears total (X) does not match Brought Forward receivables (Y)". The admin must be able to tell why sealing failed.

**Tests:**
- Fill arrears from a file, click Next, then reload: the rows are still there.
- Next with an untouched grid doesn't erase saved rows.
- `arrears_tie` passes when the totals match.
- `arrears_tie` fails with a readable reason when they differ.

---

## Task 4: Make the arrears grid work (bug 3)

1. Add a callback for "+ Add row" that appends a blank row.
2. Add a callback that recomputes the arrears total on every edit, add, or delete.
3. Make the total feed the `arrears_tie` control live, through the Task 1 roll-up.

**Tests:** add a row, edit amounts, delete a row, and check the total and the control status after each step.

---

## Task 5: Rebuild the Apt-Arrears template to spec (bug 4)

1. Replace the old `Receivables` sheet. Name the sheet for the financial year, the same way the statement template does.
2. Use the column names from the spec. Remove `flat_number` and `overdue_days` unless the spec keeps them.
3. Add the `as_on_date` column.
4. Change the download callback so it passes the financial year and the as-on date to the template builder.
5. Update the arrears importer to read the new sheet name and columns. Give per-row error messages, the same style as the statement importer.

**Tests:**
- Template: sheet name, column names and order, and `as_on_date` present.
- Round trip: generate the template, fill it, import it, and check that the grid rows are correct.
- Importer: rows with errors produce per-row messages.
- The old sheet and column names are rejected with a clear message.

---

## Task 6: Fix screen order and labels (bugs 5, 6)

1. Move the "Funds selected" card up to the position the plan specifies.
2. Move the Apt-Arrears grid directly next to its buttons, not below the balance grid.
3. Change every button label to match the plan's label list. "File statements" must read **"Fill 'Brought Forward' Grid"**. Find all other buttons on this screen and the arrears section and compare each against the plan. If the plan doesn't specify a label, leave it and list it in your report.

**Tests:** render the screen and assert the order of sections and the exact label text of each button.

---

## Task 7: Fix the stale live test (bug 9)

1. In `test_plan_v5_onboarding_live.py`, remove the call to the deleted `save_annex_inputs`.
2. Replace it with the current save path that the Brought Forward flow uses.
3. Check the rest of that file for other references to deleted names such as `bank_agrees` or the reconciliation code.
4. This test is skipped without a live database, so confirm it by reading it carefully and, where possible, running it against a local test database. Say clearly in your report which of these you did.

---

## Final verification (required before reporting)

1. Run the full suite. Everything must pass, with no new skips.
2. Run lint. Errors must be at or below 30, and the new code must add none.
3. Run `grep -rn "save_annex_inputs\|bank_agrees\|flat_number\|overdue_days\|Receivables"` over the app and tests. Every remaining hit must be intentional.
4. Walk the screen by hand, or with an end-to-end test, in this sequence: open it, check the controls panel, fill from a statement file, edit a cell, fill arrears from a file, click Next, reload, then seal. Report what happened at each step.
5. Write a short report with one line per bug (1 to 9) giving the commit and the test that covers it. List any bug you couldn't fix or any spec question you had to leave open.
