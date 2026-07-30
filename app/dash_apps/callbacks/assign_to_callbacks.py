# app/dash_apps/callbacks/assign_to_callbacks.py
"""
Assign-To Modal Callbacks
=========================
File-Explorer style modal for assigning concerns to admins / vendors / security.

UI flow:
  1. User clicks "Assign" on concern profile → modal opens
  2. Modal shows 3 cards: ADM, VND, SEC
  3. Clicking a card loads the respective entity list below
  4. User toggles selection on items (checkboxes / card click)
  5. Submit writes to concerns_assigns table
  6. Modal closes, concern list/profile refreshes
"""

from __future__ import annotations

from dash import Input, Output, State, no_update, html, ctx, ALL, MATCH
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.drilldown.loaders import (
    get_concern_assignments,
    list_assignable_admins,
    list_assignable_vendors,
    list_assignable_security,
    humanize_assignment,
)
from app.security.audit_context import get_current_user_id

PORTAL_ROLE_LABEL = {
    "ADM": "Admin",
    "VND": "Vendor",
    "SEC": "Security",
}


def _render_assign_item(row: dict, role: str, selected: bool, view: str = "list") -> html.Div:
    """Render a single assignable entity item."""
    if role == "ADM":
        label = row.get("name") or row.get("email", "Admin")
        sub = row.get("email", "")
        icon = "fas fa-user-shield"
        color = "#1d74d8"
    elif role == "VND":
        label = row.get("business_name") or row.get("name", "Vendor")
        sub = row.get("mobile", "")
        icon = "fas fa-truck"
        color = "#17976e"
    else:
        label = row.get("name", "Security")
        sub = f"{row.get('shift', '')} {row.get('mobile', '')}".strip()
        icon = "fas fa-shield-alt"
        color = "#e59620"

    rid = row.get("id")
    # NOTE: must be the pattern-matching dict id, not a plain string —
    # the toggle_selection callback below listens on
    # Input({"type": "assign-item", "role": ALL, "entity_id": ALL}, "n_clicks")
    # and a plain string id ("assign-item-ADM-3") never matches that pattern,
    # so clicks silently went nowhere and selections never reached the store.
    item_id = {"type": "assign-item", "role": role, "entity_id": rid}

    if view == "grid":
        inner = dbc.Card([
            dbc.CardBody([
                html.Div([
                    html.I(className=f"{icon} fa-2x mb-2", style={"color": color}),
                    html.H6(label, style={"fontWeight": "600", "fontSize": "13px"}),
                    html.Small(sub, style={"color": "#64748b", "fontSize": "11px"}),
                ], className="text-center"),
            ], style={"padding": "12px"}),
        ], style={
            "borderRadius": "10px",
            "border": f"2px solid {color}" if selected else "1px solid #e2e8f0",
            "cursor": "pointer",
            "backgroundColor": f"{color}10" if selected else "#fff",
        }, id=item_id, className="mb-2")
    else:
        inner = dbc.ListGroupItem([
            html.Div([
                dbc.Checkbox(
                    id={"type": "assign-check", "role": role, "entity_id": rid},
                    value=selected,
                    style={"marginRight": "10px", "pointerEvents": "none"},
                ),
                html.I(className=f"{icon} me-2", style={"color": color, "width": "20px", "textAlign": "center"}),
                html.Div([
                    html.Span(label, style={"fontWeight": "600", "fontSize": "13px"}),
                    html.Br(),
                    html.Small(sub, style={"color": "#64748b", "fontSize": "11px"}),
                ]),
            ], className="d-flex align-items-center"),
        ], action=True, id=item_id, style={
            "cursor": "pointer",
            "border": f"2px solid {color}" if selected else None,
            "backgroundColor": f"{color}10" if selected else None,
        })

    return html.Div(inner, className="mb-1")


def register_assign_to_callbacks(app):
    """Register all assign-to modal callbacks."""

    # ── 1. Open modal from concern profile action ────────────────────────────
    @app.callback(
        Output("assign-to-modal", "is_open", allow_duplicate=True),
        Output("assign-to-store", "data", allow_duplicate=True),
        Input("profile-action-trigger", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def open_assign_modal(trigger_data, auth):
        if not trigger_data or not isinstance(trigger_data, dict):
            raise PreventUpdate
        action = trigger_data.get("action")
        if action != "open_assign_modal":
            raise PreventUpdate
        params = trigger_data.get("params") or {}
        concern_id = params.get("concern_id")
        if not concern_id:
            return False, no_update
        society_id = (auth or {}).get("society_id")
        selected = {}
        if society_id and concern_id:
            try:
                assigns = get_concern_assignments(int(concern_id))
                for a in assigns:
                    role = a.get("role")
                    eid = a.get("entity_id")
                    if role and eid:
                        selected[f"{role}-{eid}"] = True
            except Exception:
                pass
        return True, {"concern_id": int(concern_id), "selected": selected, "active_role": None}

    # ── 2. Close modal ────────────────────────────────────────────────────────
    @app.callback(
        Output("assign-to-modal", "is_open", allow_duplicate=True),
        Input("close-assign-to-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_assign_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Entity-type card click OR search change → (re)load list ────────────
    # `assign-search` is a real Input here (not just a State read at click
    # time), and the currently-active role is tracked in assign-to-store, so
    # typing in the search box re-runs the query for whichever role list is
    # currently open. Previously the search box was only a State, and a
    # separate callback zeroed out the cards' n_clicks on every keystroke to
    # "force" a reload — but that zeroing made every n_clicks falsy, so the
    # `if not any(...)` guard here would immediately PreventUpdate and the
    # list never actually refreshed.
    @app.callback(
        Output("assign-list-container", "children"),
        Output({"type": "assign-card", "role": ALL}, "color"),
        Output({"type": "assign-card", "role": ALL}, "outline"),
        Output("assign-to-store", "data", allow_duplicate=True),
        Input({"type": "assign-card", "role": ALL}, "n_clicks"),
        Input("assign-search", "value"),
        State("assign-to-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def load_assign_list(n_clicks_list, search, store, auth):
        store = dict(store or {})
        triggered = ctx.triggered_id

        if triggered == "assign-search":
            # Re-filtering whatever list is already open; if no card has
            # been picked yet there's nothing to filter.
            role = store.get("active_role")
            if role not in ("ADM", "VND", "SEC"):
                raise PreventUpdate
        elif isinstance(triggered, dict) and triggered.get("type") == "assign-card":
            role = triggered.get("role")
            if role not in ("ADM", "VND", "SEC"):
                raise PreventUpdate
            store["active_role"] = role
        else:
            raise PreventUpdate

        selected = store.get("selected", {})

        society_id = (auth or {}).get("society_id")
        if not society_id:
            return html.P("Not authenticated.", style={"color": "#de5c52"}), no_update, no_update, no_update

        s = (search or "").strip() or None
        try:
            if role == "ADM":
                rows = list_assignable_admins(society_id, s)
            elif role == "VND":
                rows = list_assignable_vendors(society_id, s)
            else:
                rows = list_assignable_security(society_id, s)
        except Exception as e:
            return html.P(f"Error loading list: {e}", style={"color": "#de5c52"}), no_update, no_update, no_update

        # Card highlight reflects the active role directly, not accumulated
        # n_clicks — with n_clicks, once two cards had each been clicked at
        # least once in the session, both stayed highlighted forever.
        card_colors = []
        card_outlines = []
        for card_role in ("ADM", "VND", "SEC"):
            if card_role == role:
                card_colors.append("primary" if role == "ADM" else "success" if role == "VND" else "warning")
                card_outlines.append(False)
            else:
                card_colors.append("secondary")
                card_outlines.append(True)

        if not rows:
            empty = html.P(
                f"No {PORTAL_ROLE_LABEL[role].lower()}s found.",
                className="text-muted text-center", style={"padding": "30px"},
            )
            return empty, card_colors, card_outlines, store

        items = [_render_assign_item(r, role, selected.get(f"{role}-{r.get('id')}", False), view="list") for r in rows]
        return html.Div(items, style={"maxHeight": "400px", "overflowY": "auto"}), card_colors, card_outlines, store

    # ── 4. Toggle selection on item click ────────────────────────────────────
    @app.callback(
        Output("assign-to-store", "data", allow_duplicate=True),
        Output("assign-selected-summary", "children"),
        Input({"type": "assign-item", "role": ALL, "entity_id": ALL}, "n_clicks"),
        State("assign-to-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_selection(n_clicks_list, store):
        if not any(n for n in (n_clicks_list or []) if n):
            raise PreventUpdate
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            raise PreventUpdate
        role = triggered.get("role")
        eid = triggered.get("entity_id")
        if not role or eid is None:
            raise PreventUpdate

        store = dict(store or {})
        selected = dict(store.get("selected", {}))
        key = f"{role}-{eid}"
        selected[key] = not selected.get(key, False)
        store["selected"] = selected

        # Build summary
        badges = []
        for k, v in selected.items():
            if not v:
                continue
            parts = k.split("-", 1)
            r = parts[0]
            e = parts[1] if len(parts) > 1 else ""
            label = f"{PORTAL_ROLE_LABEL.get(r, r)} #{e}"
            badges.append(
                dbc.Badge(
                    label,
                    color="primary" if r == "ADM" else "success" if r == "VND" else "warning",
                    className="me-1",
                    style={"fontSize": "11px"},
                )
            )
        summary = html.Div(badges) if badges else html.Small("No assignments selected.", className="text-muted")
        return store, summary

    # ── 5. Clear all selections ──────────────────────────────────────────────
    @app.callback(
        Output("assign-to-store", "data", allow_duplicate=True),
        Output("assign-selected-summary", "children", allow_duplicate=True),
        Input("assign-clear-btn", "n_clicks"),
        State("assign-to-store", "data"),
        prevent_initial_call=True,
    )
    def clear_selections(n_clicks, store):
        if not n_clicks:
            raise PreventUpdate
        store = dict(store or {})
        store["selected"] = {}
        return store, html.Small("No assignments selected.", className="text-muted")

    # ── 6. Submit assignments ────────────────────────────────────────────────
    @app.callback(
        Output("assign-to-modal", "is_open", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Input("assign-submit-btn", "n_clicks"),
        State("assign-to-store", "data"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def submit_assignments(n_clicks, store, auth, drill_store):
        if not n_clicks:
            raise PreventUpdate
        store = store or {}
        concern_id = store.get("concern_id")
        selected = store.get("selected", {})
        if not concern_id:
            return False, {"type": "warning", "message": "No concern selected."}, no_update, no_update, no_update

        society_id = (auth or {}).get("society_id")
        actor_user_id = get_current_user_id()
        if not society_id:
            return False, {"type": "error", "message": "Session expired."}, no_update, no_update, no_update

        try:
            # Fetch prior assignments first so we can tell which of the
            # selected entities are newly assigned (only those get a push —
            # resubmitting an unchanged assignment shouldn't re-notify).
            # This table now also carries invited/bid_submitted/resolved/
            # closed rows (unified 2026-07), so status comes along too.
            prior_rows = db._execute(
                "SELECT role, entity_id, status FROM concerns_assigns WHERE concern_id=%s AND society_id=%s",
                (concern_id, society_id), fetch_all=True,
            ) or []
            prior_by_key = {f"{r['role']}-{r['entity_id']}": r["status"] for r in prior_rows}
            prior_keys = set(prior_by_key.keys())

            selected_keys = {k for k, v in selected.items() if v}
            to_delete = prior_keys - selected_keys
            to_insert = selected_keys - prior_keys

            # Unchecking someone must not silently erase a resolved/closed
            # assignment's history — only rows still in-flight (invited,
            # bid_submitted, assigned) can be removed here.
            for key in to_delete:
                if prior_by_key.get(key) in ("resolved", "closed"):
                    continue
                parts = key.split("-", 1)
                role = parts[0]
                try:
                    entity_id = int(parts[1])
                except (IndexError, ValueError):
                    continue
                db._execute(
                    "DELETE FROM concerns_assigns "
                    "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s "
                    "AND status NOT IN ('resolved', 'closed')",
                    (concern_id, society_id, role, entity_id),
                )

            inserted = 0
            newly_assigned = []
            for key in to_insert:
                parts = key.split("-", 1)
                role = parts[0]
                try:
                    entity_id = int(parts[1])
                except (IndexError, ValueError):
                    continue
                db._execute(
                    "INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id, assigned_by, status) "
                    "VALUES (%s, %s, %s, %s, %s, 'assigned') "
                    "ON CONFLICT (concern_id, role, entity_id) DO UPDATE SET "
                    "  status='assigned', assigned_by=EXCLUDED.assigned_by, updated_at=NOW() "
                    "WHERE concerns_assigns.status NOT IN ('resolved', 'closed')",
                    (concern_id, society_id, role, entity_id, actor_user_id),
                )
                inserted += 1
                newly_assigned.append((role, entity_id))

            # concerns.status is now kept in sync automatically by
            # trg_concerns_assigns_sync_status (see estatehub.sql) whenever
            # concerns_assigns rows are inserted/updated/deleted above — no
            # manual UPDATE concerns SET status=... needed here anymore.

            # Push-notify only the newly-assigned entities.
            if newly_assigned:
                try:
                    from app.services.push_service import notify_concern_assigned
                    concern_row = db._execute(
                        "SELECT concern_type FROM concerns WHERE id=%s AND society_id=%s",
                        (concern_id, society_id), fetch_one=True,
                    )
                    notify_concern_assigned(
                        society_id, concern_id,
                        (concern_row or {}).get("concern_type", "other"),
                        newly_assigned,
                    )
                except Exception as e:
                    print(f"⚠️  notify_concern_assigned failed: {e}")

            # Refresh the concern list/profile
            from app.dash_apps.callbacks.drilldown_callbacks import _render_current
            content, breadcrumb, db_err = _render_current(drill_store or {}, auth or {})
            return (
                False,
                {"type": "success", "message": f"Assignments updated: {inserted} assignee(s)."},
                no_update,
                content,
                breadcrumb,
            )
        except Exception as e:
            return False, {"type": "error", "message": str(e)}, no_update, no_update, no_update

    print("  ✓ Assign-to callbacks registered")
