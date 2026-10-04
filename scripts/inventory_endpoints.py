#!/usr/bin/env python3
"""
Endpoint inventory + authorization manifest check (RWA3.md WP1).

Statically inventories every server-side callable surface:
  * Flask routes   - app/routes/*.py (@bp.route)
  * Dash callbacks - app/dash_apps/callbacks/*.py (@app.callback; clientside
                     callbacks run in the browser and are not server surfaces)

and compares it with the reviewed manifest `docs/authz_manifest.json`.

    python scripts/inventory_endpoints.py --write   regenerate docs/endpoint_inventory.{json,md}
                                                    and ADD new endpoints to the manifest as
                                                    "unclassified" so a human must classify them
    python scripts/inventory_endpoints.py --check   CI gate (exit 1 on any finding)

--check fails when:
  1. an endpoint exists in code but has no manifest entry (new endpoint not reviewed);
  2. a manifest entry claims classification "action" but the code has no
     matching ensure()/check()/authorize_resource()/@require_action reference
     for that action (the manifest would be lying);
  3. an entry is classified "exempt" without a reason;
  4. a manifest entry refers to an endpoint that no longer exists (stale);
  5. the number of "unclassified" entries GROWS above the recorded baseline
     (a ratchet: legacy debt may only shrink).

Classifications: action | legacy-gated | exempt | unclassified
  action        enforced by authorize() via a named capability
  legacy-gated  authenticated + coarse role/ownership check, awaiting migration
  exempt        public or system endpoint, with a written reason
  unclassified  not yet reviewed (bootstrap state only)

This is a structural check. It proves a policy reference exists, not that the
policy is right - that is what the role x capability and negative-access tests
are for.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ROUTES_DIR = ROOT / "app" / "routes"
CALLBACKS_DIR = ROOT / "app" / "dash_apps" / "callbacks"
DOCS = ROOT / "docs"
MANIFEST = DOCS / "authz_manifest.json"
INVENTORY_JSON = DOCS / "endpoint_inventory.json"
INVENTORY_MD = DOCS / "endpoint_inventory.md"

AUTHZ_CALLS = {"ensure", "check", "authorize_resource", "require_action", "_authz_res"}
LEGACY_GUARDS = {"require_session", "login_required", "token_required", "role_required"}


def _cap_values() -> dict[str, str]:
    from app.security.authorization import Cap
    return {k: v for k, v in vars(Cap).items() if not k.startswith("_") and isinstance(v, str)}


def _public_callbacks() -> dict[str, set[str]]:
    spec = importlib.util.spec_from_file_location("ccg", ROOT / "scripts" / "check_callback_guards.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.PUBLIC_CALLBACKS


def _dec_name(dec: ast.expr) -> str | None:
    node = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _cap_arg(call: ast.Call, caps: dict[str, str]) -> str | None:
    """Resolve `Cap.X` / `_Cap.X` (first positional arg) to its action string."""
    if call.args and isinstance(call.args[0], ast.Attribute) and call.args[0].attr in caps:
        return caps[call.args[0].attr]
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _direct_actions(fn: ast.AST, caps: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            name = _dec_name(node)
            if name in AUTHZ_CALLS:
                a = _cap_arg(node, caps)
                if a:
                    out.add(a)
    return out


def _helper_actions(tree: ast.Module, caps: dict[str, str]) -> dict[str, set[str]]:
    """Module-level helpers that perform an authorization check themselves
    (e.g. drillin_callbacks.resolve_dues_scope). A callback that calls such a
    helper by name is credited with the helper's actions - ONE level only, so
    the manifest cannot be satisfied by a long indirect chain nobody reviews.
    Callbacks themselves are never treated as helpers."""
    out: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                   and d.func.attr == "callback" for d in node.decorator_list):
                continue
            acts = _direct_actions(node, caps)
            if acts:
                out[node.name] = acts
    return out


def _authz_actions(fn: ast.AST, caps: dict[str, str],
                   helpers: dict[str, set[str]] | None = None) -> set[str]:
    out = _direct_actions(fn, caps)
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and helpers:
            name = _dec_name(node)
            if name in helpers:
                out |= helpers[name]
    return out


INLINE_AUTH_NAMES = {"_bearer_user_id", "authenticate_bearer", "is_authenticated"}


def _has_inline_auth(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id in INLINE_AUTH_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in INLINE_AUTH_NAMES:
            return True
    return False


def _blueprint_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and _dec_name(node.value) == "Blueprint" and node.targets
                and isinstance(node.targets[0], ast.Name)):
            prefix = ""
            for kw in node.value.keywords:
                if kw.arg == "url_prefix" and isinstance(kw.value, ast.Constant):
                    prefix = kw.value.value
            prefixes[node.targets[0].id] = prefix
    return prefixes


def _route_info(dec: ast.expr, prefixes: dict[str, str]):
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "route" and dec.args
            and isinstance(dec.args[0], ast.Constant)):
        return None
    base = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
    methods = ["GET"]
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
            methods = [e.value for e in kw.value.elts if isinstance(e, ast.Constant)]
    return prefixes.get(base, "") + dec.args[0].value, methods


def collect() -> list[dict]:
    caps = _cap_values()
    public = _public_callbacks()
    rows: list[dict] = []

    for path in sorted(ROUTES_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefixes = _blueprint_prefixes(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in fn.decorator_list:
                info = _route_info(dec, prefixes)
                if info:
                    guards = sorted({n for d in fn.decorator_list if (n := _dec_name(d)) in LEGACY_GUARDS}
                                    | ({"inline-auth"} if _has_inline_auth(fn) else set()))
                    rows.append({
                        "id": f"route:{path.name}::{fn.name}", "kind": "flask-route",
                        "file": f"app/routes/{path.name}", "function": fn.name, "line": fn.lineno,
                        "route": info[0], "methods": info[1], "guards": guards,
                        "actions": sorted(_authz_actions(fn, caps)), "public": False,
                    })

    for path in sorted(CALLBACKS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helpers = _helper_actions(tree, caps)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decs = fn.decorator_list
            cb = next((d for d in decs if isinstance(d, ast.Call)
                       and isinstance(d.func, ast.Attribute) and d.func.attr == "callback"), None)
            if cb is None:
                continue
            outputs = [a.args[0].value for a in cb.args
                       if isinstance(a, ast.Call) and _dec_name(a) == "Output" and a.args
                       and isinstance(a.args[0], ast.Constant)]
            guards = sorted({n for d in decs if (n := _dec_name(d)) in LEGACY_GUARDS | {"require_action"}})
            rows.append({
                "id": f"callback:{path.name}::{fn.name}", "kind": "dash-callback",
                "file": f"app/dash_apps/callbacks/{path.name}", "function": fn.name,
                "line": fn.lineno, "route": "/dashboard/_dash-update-component",
                "methods": ["POST"], "outputs": outputs[:3], "guards": guards,
                "actions": sorted(_authz_actions(fn, caps, helpers)),
                "public": fn.name in public.get(path.name, set()),
            })
    rows.sort(key=lambda r: r["id"])
    return rows


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"version": 1, "unclassified_baseline": 0, "endpoints": {}}


def _bootstrap_entry(row: dict) -> dict:
    if row["public"]:
        return {"classification": "exempt",
                "reason": "pre-session UI/login mechanics (check_callback_guards.PUBLIC_CALLBACKS)"}
    if row["actions"]:
        return {"classification": "action", "actions": row["actions"]}
    if row["guards"]:
        return {"classification": "unclassified"}
    return {"classification": "unclassified"}


def write() -> int:
    rows = collect()
    manifest = _load_manifest()
    ep = manifest["endpoints"]
    for row in rows:
        entry = ep.get(row["id"])
        if entry is None:
            ep[row["id"]] = _bootstrap_entry(row)
        elif entry["classification"] != "action" and row["actions"] and not entry.get("keep"):
            # code gained a policy reference: promote the reviewed entry.
            ep[row["id"]] = {"classification": "action", "actions": row["actions"]}
    live = {r["id"] for r in rows}
    for stale in [k for k in ep if k not in live]:
        del ep[stale]
    manifest["unclassified_baseline"] = sum(
        1 for e in ep.values() if e["classification"] == "unclassified")
    manifest["endpoints"] = dict(sorted(ep.items()))
    DOCS.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    INVENTORY_JSON.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    by_class: dict[str, int] = {}
    for e in ep.values():
        by_class[e["classification"]] = by_class.get(e["classification"], 0) + 1
    lines = ["# Endpoint inventory", "",
             "Generated by `scripts/inventory_endpoints.py --write`. Do not edit by hand; "
             "classify endpoints in `docs/authz_manifest.json`.", "",
             "| classification | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(by_class.items())]
    lines += ["", "| endpoint | kind | guards | actions | classification |", "|---|---|---|---|---|"]
    for r in rows:
        e = ep[r["id"]]
        lines.append(f"| `{r['id']}` | {r['kind']} | {', '.join(r['guards']) or '-'} | "
                     f"{', '.join(r['actions']) or '-'} | {e['classification']} |")
    INVENTORY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"inventory: {len(rows)} endpoints; " + ", ".join(f"{k}={v}" for k, v in sorted(by_class.items())))
    return 0


def check() -> int:
    rows = {r["id"]: r for r in collect()}
    manifest = _load_manifest()
    ep = manifest["endpoints"]
    problems: list[str] = []
    for rid, row in rows.items():
        entry = ep.get(rid)
        if entry is None:
            problems.append(f"NEW endpoint not in manifest (classify it): {rid}")
            continue
        cls = entry.get("classification")
        if cls not in {"action", "legacy-gated", "exempt", "unclassified"}:
            problems.append(f"{rid}: invalid classification {cls!r}")
        if cls == "action":
            missing = set(entry.get("actions", [])) - set(row["actions"])
            if not entry.get("actions") or missing:
                problems.append(f"{rid}: classified 'action' but code has no policy reference for "
                                f"{sorted(missing) or 'any action'}")
        if cls == "exempt" and not entry.get("reason"):
            problems.append(f"{rid}: 'exempt' requires a written reason")
        if cls == "legacy-gated" and not row["guards"] and not row["actions"]:
            problems.append(f"{rid}: 'legacy-gated' but the endpoint has no guard at all")
    for rid in ep:
        if rid not in rows:
            problems.append(f"STALE manifest entry (endpoint removed): {rid}")
    unclassified = sum(1 for e in ep.values() if e.get("classification") == "unclassified")
    if unclassified > manifest.get("unclassified_baseline", 0):
        problems.append(f"unclassified endpoints grew: {unclassified} > baseline "
                        f"{manifest.get('unclassified_baseline', 0)}")
    if problems:
        print("authorization manifest check FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"authorization manifest OK ({len(rows)} endpoints, {unclassified} unclassified legacy)")
    return 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        sys.exit(write())
    sys.exit(check())
