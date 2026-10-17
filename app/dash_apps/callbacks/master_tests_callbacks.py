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
from pathlib import Path

from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.security.guards import require_session


def _project_root() -> Path:
    # app/dash_apps/callbacks/master_tests_callbacks.py -> project root
    return Path(__file__).resolve().parents[3]


def _run_pytest(test_file: str):
    """Run a single test file with pytest; return (returncode, combined_output)."""
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

    # ── Run all test files ──────────────────────────────────────────────
    @app.callback(
        Output("tests-output", "children", allow_duplicate=True),
        Input("run-all-tests-btn", "n_clicks"),
        State("tests-list-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def run_all_tests(n_clicks, tests):
        if not n_clicks:
            raise PreventUpdate
        if not tests:
            return html.Small("No test files to run.", className="text-muted")

        parts = []
        any_failed = False
        for t in tests:
            test_file = t["file"]
            parts.append(f"===== {test_file} =====")
            rc, output = _run_pytest(test_file)
            parts.append(output or "(no output)")
            parts.append(f"===== {test_file} — exit code {rc} =====\n")
            if rc != 0:
                any_failed = True

        summary = ("\nALL TESTS PASSED" if not any_failed else "\nSOME TESTS FAILED")
        parts.append(summary)
        output_el = html.Pre(
            "\n".join(parts),
            style={"fontSize": "11px", "fontFamily": "monospace", "whiteSpace": "pre-wrap",
                   "color": "#2c3e50", "margin": 0},
        )
        return output_el
