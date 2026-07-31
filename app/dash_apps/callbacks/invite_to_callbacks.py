# app/dash_apps/callbacks/invite_to_callbacks.py
"""
Invite-To Modal Callbacks
==========================
Admin/Owner's "Invite" action on a concern profile. Writes into the same
concerns_assigns table as the Assign modal, at the 'invited' stage of the
unified per-assignee lifecycle (invited -> bid_submitted -> assigned ->
resolved -> closed) — concerns_invite has been retired.

UI flow:
  1. Admin/Owner clicks "Invite" on a concern profile -> modal opens
  2. Modal shows 2 cards: VND, SEC (no ADM — admins are auto-assigned)
  3. Clicking a card loads the respective entity list below
  4. User toggles selection on items (checkboxes / card click)
  5. Submit writes to concerns_assigns (status='invited')
  6. Modal closes, concern list/profile refreshes
"""

from __future__ import annotations

from dash import Input, Output, State, no_update, html, ctx, ALL, MATCH
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.drilldown.loaders import (
    get_concern_assignments,
    list_invitable_vendors,
    list_invitable_security,
    humanize_assignment,
)
from app.security.audit_context import get_current_user_id


PORTAL_ROLE_LABEL = {
    "VND": "Vendor",
    "SEC": "Security",
}


def _render_invite_item(row: dict, role: str, selected: bool, view: str = "list") -> html.Div:
    """Render a single inviteable entity item."""
    if role == "VND":
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
    item_id = {"type": "invite-item", "role": role, "entity_id": rid}

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
                    id={"type": "invite-check", "role": role, "entity_id": rid},
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


def register_invite_to_callbacks(app):
    """Register all invite-to modal callbacks."""

    # ── 1. Open modal from concern profile action ──────────────────────────
    @app.callback(
        Output("invite-to-modal", "is_open", allow_duplicate=True),
        Output("invite-to-store", "data", allow_duplicate=True),
        Input("profile-action-trigger", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def open_invite_modal(trigger_data, auth):
        if not trigger_data or not isinstance(trigger_data, dict):
            raise PreventUpdate
        action = trigger_data.get("action")
        if action != "open_invite_modal":
            raise PreventUpdate
        params = trigger_data.get("params") or {}
        concern_id = params.get("concern_id")
        if not concern_id:
            return False, no_update
        society_id = (auth or {}).get("society_id")
        selected = {}
        if society_id and concern_id:
            try:
                assignments = get_concern_assignments(int(concern_id))
                for a in assignments:
                    role = a.get("role")
                    eid = a.get("entity_id")
                    if role in ("VND", "SEC") and eid:
                        selected[f"{role}-{eid}"] = True
            except Exception:
                pass
        return True, {"concern_id": int(concern_id), "selected": selected, "active_role": None}

    # ── 2. Close modal ──────────────────────────────────────────────────────
    @app.callback(
        Output("invite-to-modal", "is_open", allow_duplicate=True),
        Input("close-invite-to-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_invite_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Entity-type card click OR search change → (re)load list ─────────
    @app.callback(
        Output("invite-list-container", "children"),
        Output({"type": "invite-card", "role": ALL}, "color"),
        Output({"type": "invite-card", "role": ALL}, "outline"),
        Output("invite-to-store", "data", allow_duplicate=True),
        Input({"type": "invite-card", "role": ALL}, "n_clicks"),
        Input("invite-search", "value"),
        State("invite-to-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def load_invite_list(n_clicks_list, search, store, auth):
        store = dict(store or {})
        triggered = ctx.triggered_id

        if triggered == "invite-search":
            role = store.get("active_role")
            if role not in ("VND", "SEC"):
                raise PreventUpdate
        elif isinstance(triggered, dict) and triggered.get("type") == "invite-card":
            role = triggered.get("role")
            if role not in ("VND", "SEC"):
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
            if role == "VND":
                rows = list_invitable_vendors(society_id, s)
            else:
                rows = list_invitable_security(society_id, s)
        except Exception as e:
            return html.P(f"Error loading list: {e}", style={"color": "#de5c52"}), no_update, no_update, no_update

        card_colors = []
        card_outlines = []
        for card_role in ("VND", "SEC"):
            if card_role == role:
                card_colors.append("success" if role == "VND" else "warning")
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

        items = [_render_invite_item(r, role, selected.get(f"{role}-{r.get('id')}", False), view="list") for r in rows]
        return html.Div(items, style={"maxHeight": "400px", "overflowY": "auto"}), card_colors, card_outlines, store

    # ── 4. Toggle selection on item click ────────────────────────────────────
    # NOTE: this used to only write invite-to-store + the summary badges below
    # the list — the store update was correct, but the clicked row itself
    # never got a re-render, so the checkbox stayed visually unchecked and
    # the row never got its selected border/background. From the user's
    # perspective this looked exactly like "can't select" — clicking did
    # something (the badge appeared below), but the row you actually clicked
    # never seemed to respond. Now also re-renders the visible list so the
    # clicked row reflects its new state immediately.
    @app.callback(
        Output("invite-to-store", "data", allow_duplicate=True),
        Output("invite-selected-summary", "children"),
        Output("invite-list-container", "children", allow_duplicate=True),
        Input({"type": "invite-item", "role": ALL, "entity_id": ALL}, "n_clicks"),
        State("invite-to-store", "data"),
        State("invite-search", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_invite_selection(n_clicks_list, store, search, auth):
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
                    color="success" if r == "VND" else "warning",
                    className="me-1",
                    style={"fontSize": "11px"},
                )
            )
        summary = html.Div(badges) if badges else html.Small("No invitations selected.", className="text-muted")

        # Re-render the currently-visible list so the row the user just
        # clicked actually shows its new checked/border state. Re-querying
        # here (rather than patching just the one clicked row) keeps this in
        # lockstep with load_invite_list's own rendering and stays correct
        # even if the same entity got toggled from elsewhere.
        list_children = no_update
        society_id = (auth or {}).get("society_id")
        if role in ("VND", "SEC") and society_id:
            s = (search or "").strip() or None
            try:
                rows = list_invitable_vendors(society_id, s) if role == "VND" else list_invitable_security(society_id, s)
                items = [_render_invite_item(r, role, selected.get(f"{role}-{r.get('id')}", False), view="list") for r in rows]
                list_children = html.Div(items, style={"maxHeight": "400px", "overflowY": "auto"}) if rows else html.P(
                    f"No {PORTAL_ROLE_LABEL[role].lower()}s found.", className="text-muted text-center", style={"padding": "30px"},
                )
            except Exception:
                pass  # keep list_children = no_update rather than blank the list on a transient query error

        return store, summary, list_children

    # ── 5. Clear all selections ──────────────────────────────────────────
    @app.callback(
        Output("invite-to-store", "data", allow_duplicate=True),
        Output("invite-selected-summary", "children", allow_duplicate=True),
        Input("invite-clear-btn", "n_clicks"),
        State("invite-to-store", "data"),
        prevent_initial_call=True,
    )
    def clear_invite_selections(n_clicks, store):
        if not n_clicks:
            raise PreventUpdate
        store = dict(store or {})
        store["selected"] = {}
        return store, html.Small("No invitations selected.", className="text-muted")

    # ── 6. Submit invitations ────────────────────────────────────────────────
    @app.callback(
        Output("invite-to-modal", "is_open", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Input("invite-submit-btn", "n_clicks"),
        State("invite-to-store", "data"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def submit_invitations(n_clicks, store, auth, drill_store):
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
            # Fetch prior VND/SEC assignee rows (any lifecycle stage) so we
            # only touch what actually needs to change.
            prior_rows = db._execute(
                "SELECT role, entity_id, status FROM concerns_assigns "
                "WHERE concern_id=%s AND society_id=%s AND role IN ('VND', 'SEC')",
                (concern_id, society_id), fetch_all=True,
            ) or []
            prior_by_key = {f"{r['role']}-{r['entity_id']}": r["status"] for r in prior_rows}
            prior_keys = set(prior_by_key.keys())

            selected_keys = {k for k, v in selected.items() if v}
            to_delete = prior_keys - selected_keys
            to_insert = selected_keys - prior_keys

            # Only remove rows still sitting at 'invited' — once someone has
            # submitted a bid or been assigned/resolved/closed, unchecking
            # them here must not silently wipe that progress.
            for key in to_delete:
                if prior_by_key.get(key) != "invited":
                    continue
                parts = key.split("-", 1)
                role = parts[0]
                try:
                    entity_id = int(parts[1])
                except (IndexError, ValueError):
                    continue
                db._execute(
                    "DELETE FROM concerns_assigns "
                    "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s AND status='invited'",
                    (concern_id, society_id, role, entity_id),
                )

            inserted = 0
            newly_invited = []
            for key in to_insert:
                parts = key.split("-", 1)
                role = parts[0]
                try:
                    entity_id = int(parts[1])
                except (IndexError, ValueError):
                    continue
                db._execute(
                    "INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id, invited_by, status, bid_amount) "
                    "VALUES (%s, %s, %s, %s, %s, 'invited', NULL) "
                    "ON CONFLICT (concern_id, role, entity_id) DO UPDATE SET "
                    "  status='invited', bid_amount=NULL, invited_by=EXCLUDED.invited_by, updated_at=NOW() "
                    "WHERE concerns_assigns.status NOT IN ('resolved', 'closed') "
                    "RETURNING id",
                    (concern_id, society_id, role, entity_id, actor_user_id), fetch_one=True,
                )
                inserted += 1
                newly_invited.append((role, entity_id))

            # Push-notify only the newly-invited entities.
            if newly_invited:
                try:
                    from app.services.push_service import notify_concern_invited
                    concern_row = db._execute(
                        "SELECT concern_type FROM concerns WHERE id=%s AND society_id=%s",
                        (concern_id, society_id), fetch_one=True,
                    )
                    notify_concern_invited(
                        society_id, concern_id,
                        (concern_row or {}).get("concern_type", "other"),
                        newly_invited,
                    )
                except Exception as e:
                    print(f"⚠️  notify_concern_invited failed: {e}")

            # Refresh the concern list/profile
            from app.dash_apps.callbacks.drilldown_callbacks import _render_current
            content, breadcrumb, db_err = _render_current(drill_store or {}, auth or {})
            return (
                False,
                {"type": "success", "message": f"Invitations sent: {inserted} invitee(s)."},
                no_update,
                content,
                breadcrumb,
            )
        except Exception as e:
            return False, {"type": "error", "message": str(e)}, no_update, no_update, no_update

    print("  ✓ Invite-to callbacks registered")