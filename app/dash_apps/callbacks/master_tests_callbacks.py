# app/dash_apps/callbacks/master_tests_callbacks.py
"""
Callbacks for the Master portal Tests tab.

Lists project test files with a Run button per file and streams pytest
output into an output pane, mirroring the KPI / List inspector pattern
used elsewhere in the master portal.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.security.audit_context import get_current_user_role
from app.security.guards import require_session


def _project_root() -> Path:
    # app/dash_apps/callbacks/master_tests_callbacks.py -> project root
    return Path(__file__).resolve().parents[3]


def _allowed_tests() -> list:
    """Server-side allow-list: exactly the files the Tests page discovers.

    Never trust the test name in the callback payload (or tests-list-store):
    Dash ids and Store data come from the client and can be forged.
    """
    from app.dash_apps.pages.portal_pages import _discover_tests  # lazy: avoids import cycle
    return [t["file"] for t in _discover_tests()]


def _run_pytest(test_file: str):
    """Run a single test file with pytest; return (returncode, combined_output)."""
    if test_file not in _allowed_tests():
        return 1, "Refused: not a discovered test file.\n"
    root = _project_root()
    test_path = root / "test" / test_file
    if not test_path.exists():
        return 1, f"Test file not found: {test_path}\n"

    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    cmd = [sys.executable, "-m", "pytest", str(test_path), "-v", "--no-header",
           "-p", "no:cacheprovider", "-q"]
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True,
                              text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + "\n--- TEST RUN TIMED OUT (180s) ---\n" + (exc.stderr or "")
        return 124, out

    combined = (proc.stdout or "")
    if proc.stderr:
        combined += "\n[STDERR]\n" + proc.stderr
    return proc.returncode, combined


_PRE_STYLE = {"fontSize": "11px", "fontFamily": "monospace", "whiteSpace": "pre-wrap",
              "color": "#2c3e50", "margin": 0}
_STATUS_COLORS = {"Queued": "#999999", "Running…": "#c96a19",
                  "Passed": "#10b981", "Failed": "#ef4444"}
_MAX_FAIL_OUTPUT = 20000  # chars of a failing test's output kept in the run queue


def _status_span(text: str):
    return html.Span(text, style={"fontSize": "11px", "fontWeight": "700",
                                  "color": _STATUS_COLORS.get(text, "#999999")})


def _by_row(rows, per_test):
    """Value list for a pattern-matching (ALL) output: one entry per row.

    `rows` is the matching entry of ctx.outputs_list; `per_test(file)` returns
    the new value for that row, or no_update to leave it alone.
    """
    return [per_test((row.get("id") or {}).get("test")) for row in rows]


def _summary_line(output: str) -> str:
    """Last non-empty line of pytest's stdout, e.g. '4 passed in 0.09s'."""
    body = (output or "").split("\n[STDERR]\n")[0]
    lines = [ln.strip("= ").strip() for ln in body.splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _render_run_all(results, total, running=None):
    """Progress pane for Run All: one line per finished file (+ output of failures)."""
    failed = sum(1 for r in results if r.get("rc") != 0)
    lines = [f"Run All — {len(results)}/{total} done · {failed} failed", ""]
    for r in results:
        mark = "PASS" if r.get("rc") == 0 else "FAIL"
        lines.append(f"[{mark}] {r.get('file')}  ({r.get('secs', 0):.1f}s)  {r.get('summary', '')}")
        if r.get("rc") != 0 and r.get("output"):
            lines += ["", r["output"], ""]
    if running:
        lines += ["", f"▶ Running {len(results) + 1}/{total}: {running} …"]
    elif total and len(results) >= total:
        lines += ["", "ALL TESTS PASSED" if not failed else "SOME TESTS FAILED"]
    return html.Pre("\n".join(lines), style=_PRE_STYLE)


def register_master_tests_callbacks(app):
    print("  → Registering master tests callbacks…")

    # ── Run a single test file ──────────────────────────────────────────
    # ALL (not MATCH) wildcards: this callback also writes the plain
    # "tests-output" Output, and dash-renderer rejects any callback whose
    # Outputs carry MATCH wildcards on different keys — and when it finds one
    # invalid callback it discards the WHOLE callback graph in the browser, so
    # nothing else (e.g. the login society dropdown) ever fires.
    @app.callback(
        Output("tests-output", "children", allow_duplicate=True),
        Output({"type": "test-status", "test": ALL}, "children"),
        Input({"type": "run-test-btn", "test": ALL}, "n_clicks"),
        State("tests-list-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def run_single_test(n_clicks_list, tests):
        if get_current_user_role() != "master":
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or "test" not in triggered:
            raise PreventUpdate
        # ALL delivers every button's n_clicks; act only on a real click.
        if not ctx.triggered or not ctx.triggered[0].get("value"):
            raise PreventUpdate
        test_file = triggered["test"]

        rc, output = _run_pytest(test_file)
        status = "Passed" if rc == 0 else "Failed"
        status_color = "#10b981" if rc == 0 else "#ef4444"
        status_el = html.Span(
            status, style={"fontSize": "11px", "fontWeight": "700", "color": status_color}
        )
        output_el = html.Pre(
            output or "(no output)",
            style={"fontSize": "11px", "fontFamily": "monospace", "whiteSpace": "pre-wrap",
                   "color": "#2c3e50", "margin": 0},
        )
        # Update only the clicked row's status; leave the other rows alone.
        statuses = [
            status_el if (o["id"] or {}).get("test") == test_file else no_update
            for o in ctx.outputs_list[1]
        ]
        return output_el, statuses

    # ── Run all test files (progressive) ────────────────────────────────
    # One long callback can't report progress, and a dcc.Interval that keeps
    # ticking while a slow test runs gets its in-flight request superseded by
    # the next tick (dash-renderer drops the older result). So the work is
    # split into short steps and the Interval is PAUSED while a test runs:
    #
    #   start_run_all  Run All click  -> queue, rows "Queued", resume Interval
    #   run_all_tick   Interval tick  -> pick next file, row "Running…",
    #                                    PAUSE Interval  (or finish: unlock UI)
    #   run_all_run_one current file  -> run pytest, row Passed/Failed,
    #                                    RESUME Interval
    #
    # State lives in the browser (tests-run-queue), so this stays correct
    # with several gunicorn workers. Every file is still validated server-side
    # by _run_pytest -> _allowed_tests, whatever the queue says.
    @app.callback(
        Output("tests-run-queue", "data"),
        Output("tests-run-interval", "disabled", allow_duplicate=True),
        Output("tests-output", "children", allow_duplicate=True),
        Output({"type": "test-status", "test": ALL}, "children", allow_duplicate=True),
        Output("run-all-tests-btn", "disabled", allow_duplicate=True),
        Output({"type": "run-test-btn", "test": ALL}, "disabled", allow_duplicate=True),
        Input("run-all-tests-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def start_run_all(n_clicks):
        if get_current_user_role() != "master":
            raise PreventUpdate
        if not n_clicks:
            raise PreventUpdate
        # Rebuild the list server-side; the client-supplied Store is not trusted.
        files = _allowed_tests()
        rows_status, rows_btn = ctx.outputs_list[3], ctx.outputs_list[5]
        if not files:
            return (no_update, no_update,
                    html.Small("No test files to run.", className="text-muted"),
                    _by_row(rows_status, lambda f: no_update), no_update,
                    _by_row(rows_btn, lambda f: no_update))
        queue = {"files": files, "i": 0, "results": []}
        return (
            queue,
            False,                                    # resume Interval -> first tick
            html.Pre(f"Run All — starting {len(files)} test files …", style=_PRE_STYLE),
            _by_row(rows_status, lambda f: _status_span("Queued") if f in files else no_update),
            True,                                     # lock Run All while running
            _by_row(rows_btn, lambda f: True),        # lock the per-row Run buttons
        )

    @app.callback(
        Output("tests-run-current", "data"),
        Output("tests-run-interval", "disabled", allow_duplicate=True),
        Output("tests-output", "children", allow_duplicate=True),
        Output({"type": "test-status", "test": ALL}, "children", allow_duplicate=True),
        Output("run-all-tests-btn", "disabled", allow_duplicate=True),
        Output({"type": "run-test-btn", "test": ALL}, "disabled", allow_duplicate=True),
        Input("tests-run-interval", "n_intervals"),
        State("tests-run-queue", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def run_all_tick(n_intervals, queue):
        if get_current_user_role() != "master":
            raise PreventUpdate
        queue = queue if isinstance(queue, dict) else {}
        files = [f for f in (queue.get("files") or []) if isinstance(f, str)]
        results = queue.get("results") or []
        i = queue.get("i", 0)
        i = i if isinstance(i, int) else 0
        rows_status, rows_btn = ctx.outputs_list[3], ctx.outputs_list[5]

        if i >= len(files):
            # Finished (or no queue): stop ticking and unlock the page.
            return (no_update, True,
                    _render_run_all(results, len(files)) if files else no_update,
                    _by_row(rows_status, lambda f: no_update), False,
                    _by_row(rows_btn, lambda f: False))

        current = files[i]
        return (
            {"file": current, "seq": i},              # triggers run_all_run_one
            True,                                     # PAUSE Interval while it runs
            _render_run_all(results, len(files), running=current),
            _by_row(rows_status, lambda f: _status_span("Running…") if f == current else no_update),
            no_update,
            _by_row(rows_btn, lambda f: no_update),
        )

    @app.callback(
        Output("tests-run-queue", "data", allow_duplicate=True),
        Output("tests-run-interval", "disabled", allow_duplicate=True),
        Output("tests-output", "children", allow_duplicate=True),
        Output({"type": "test-status", "test": ALL}, "children", allow_duplicate=True),
        Input("tests-run-current", "data"),
        State("tests-run-queue", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def run_all_run_one(current, queue):
        if get_current_user_role() != "master":
            raise PreventUpdate
        if not isinstance(current, dict) or not isinstance(queue, dict):
            raise PreventUpdate
        rows_status = ctx.outputs_list[3]
        files = queue.get("files") or []
        i = queue.get("i", 0)
        test_file = current.get("file")
        if not isinstance(i, int) or not (0 <= i < len(files)) or files[i] != test_file:
            # Stale/duplicate trigger: don't run anything, just resume ticking.
            return no_update, False, no_update, _by_row(rows_status, lambda f: no_update)

        started = time.monotonic()
        try:
            rc, output = _run_pytest(test_file)
        except Exception as exc:  # never leave the run paused on an unexpected error
            rc, output = 1, f"Runner error: {exc}\n"
        failed = rc != 0
        result = {
            "file": test_file,
            "rc": rc,
            "secs": round(time.monotonic() - started, 1),
            "summary": _summary_line(output),
            # Keep the client-side queue small: full output only for failures.
            "output": (output or "")[-_MAX_FAIL_OUTPUT:] if failed else "",
        }
        results = list(queue.get("results") or []) + [result]
        new_queue = {"files": files, "i": i + 1, "results": results}
        return (
            new_queue,
            False,                                    # RESUME Interval -> next tick
            _render_run_all(results, len(files)),
            _by_row(rows_status,
                    lambda f: _status_span("Failed" if failed else "Passed") if f == test_file else no_update),
        )
