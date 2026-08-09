#!/usr/bin/env python3
"""
CI check: every Dash callback in app/dash_apps/callbacks/ must be wrapped
in @require_session, except an explicit, reviewed allowlist of callbacks
that legitimately run before a session exists (login/reset/logout) or
that must handle both authenticated and unauthenticated requests by
design (the page router).

Run:  python3 scripts/check_callback_guards.py
Exits 1 (and prints every offending file:function) if anything outside
the allowlist is missing the guard.

Why this script exists: app/security/guards.py's require_session is a
coarse, cheap backstop against calling a Dash callback with no server
session at all (see its docstring). It only works if it's actually
applied everywhere — this is what stops that from silently regressing as
new callbacks get added, since it's not realistic to expect every future
PR to remember to check this by hand.

This is a static/structural check only — it verifies the decorator is
present, not that the callback's internal role/society_id/linked_id
logic is also migrated off auth-store. That's a separate, per-callback
review (see the auth-store migration plan).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

CALLBACKS_DIR = Path(__file__).resolve().parent.parent / "app" / "dash_apps" / "callbacks"

# Callbacks that must run WITHOUT a session, by design. Keep this list
# short and reviewed — every entry here does NOT get the require_session
# backstop, so its own body needs to stay safe standing alone (e.g. the
# login callbacks only ever read the login form and call
# authenticate_user(); they never touch tenant-scoped data).
PUBLIC_CALLBACKS: dict[str, set[str]] = {
    "login_callbacks.py": {
        "handle_password_login",
        "handle_pin_login",
        "handle_pattern_login",
        "handle_master_login",
        "toggle_forgot_modal",
        "handle_reset_flow",
    },
    "shell_callbacks.py": {
        # Society-picker / two-stage login UI mechanics — dropdown
        # population, stage-1<->stage-2 transitions, "remember this
        # society" cookie restore, modal open/close. Pure client-side UI
        # state ahead of authentication; touch no tenant data.
        "load_societies",
        "guard_modal",
        "transition_to_stage2",
        "back_to_stage1",
        "restore_from_cookie",
        "inject_stage2",
        "toggle_master",
        # Must route BOTH logged-out visitors (-> login) and logged-in
        # users (-> their portal) by design, so it can't require a
        # session up front. Its internal role-based routing decision
        # still needs its own get_current_user_role() migration — that's
        # a separate, tracked follow-up, NOT satisfied by being on this
        # allowlist.
        "route_page",
        # Best-effort: should no-op gracefully with no/expired session
        # (nothing left to log out of), not get blocked by one.
        "logout",
    },
}


def _decorator_target_name(dec: ast.expr) -> str | None:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _is_dash_callback(node: ast.FunctionDef) -> bool:
    return any(_decorator_target_name(d) == "callback" for d in node.decorator_list)


def _has_require_session(node: ast.FunctionDef) -> bool:
    return any(_decorator_target_name(d) == "require_session" for d in node.decorator_list)


def check_file(path: Path) -> list[str]:
    violations: list[str] = []
    allowlisted = PUBLIC_CALLBACKS.get(path.name, set())
    tree = ast.parse(path.read_text(), filename=str(path))

    def walk(nodes) -> None:
        for node in nodes:
            if isinstance(node, ast.FunctionDef) and _is_dash_callback(node):
                if not _has_require_session(node) and node.name not in allowlisted:
                    violations.append(f"{path.name}:{node.lineno}  {node.name}()")
            walk(ast.iter_child_nodes(node))

    walk(ast.iter_child_nodes(tree))
    return violations


def main() -> int:
    all_violations: list[str] = []
    total_files = 0

    for path in sorted(CALLBACKS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        total_files += 1
        all_violations.extend(check_file(path))

    if all_violations:
        print(f"❌ {len(all_violations)} Dash callback(s) missing @require_session "
              f"(across {total_files} files checked):\n")
        for v in all_violations:
            print(f"   {v}")
        print(
            "\nEvery @app.callback must be wrapped in @require_session "
            "(from app.security.guards) unless it's added to the reviewed "
            "PUBLIC_CALLBACKS allowlist at the top of this script, with a "
            "comment explaining why it's safe to run with no session."
        )
        return 1

    print(f"✓ All Dash callbacks guarded or explicitly allowlisted ({total_files} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
