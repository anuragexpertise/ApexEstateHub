# app/dash_apps/callbacks/card_catalogue_callbacks.py

import logging
import time
from datetime import date, datetime

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

from app.dash_apps.drilldown.loaders import _is_db_error
from database.db_manager import db
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
)

logger = logging.getLogger(__name__)

# ── KPI Cache ────────────────────────────────────────────────────────────────
# Per-process session cache keyed by "society_id:role:card_id".
# Cuts redundant DB round-trips when switching tabs or re-rendering the same portal.
_KPI_CACHE: dict[str, tuple[str, float]] = {}
# NOTE: this was 180s with NO invalidation call anywhere in the codebase
# (invalidate_kpi_cache() existed but was never imported/used), so any KPI
# could show a stale value for up to 3 minutes after a mutation. Save/
# confirm/delete in drilldown_callbacks.py now call invalidate_kpi_cache()
# explicitly on success, so this TTL is a backstop for the handful of write
# paths that don't route through those handlers (e.g. QR gate-access scans,
# bulk CSV enroll) rather than the primary staleness control.
_CACHE_TTL_SECONDS = 60.0


def _cache_key(society_id, role, card_id, entity_id=None):
    # entity_id scopes the cache to a single apartment/vendor/security
    # record when the KPI is personalised (a scoped override applies).
    # Without this, e.g. "kpi_my_pending_dues" was cached under
    # "{sid}:apartment:kpi_my_pending_dues" — identical for every apartment
    # in the society — so apartment B could be served apartment A's cached
    # dues figure for up to _CACHE_TTL_SECONDS. Only scoped cards get the
    # extra key component so generic (non-personalised) cards still share
    # one cache entry across every user of that role, as before.
    if entity_id is not None:
        return f"{society_id}:{role}:{entity_id}:{card_id}"
    return f"{society_id}:{role}:{card_id}"


def _get_cached(key):
    entry = _KPI_CACHE.get(key)
    if not entry:
        return None
    value, ts = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _KPI_CACHE.pop(key, None)
        return None
    return value


def _set_cached(key, value):
    _KPI_CACHE[key] = (value, time.time())


def invalidate_kpi_cache(card_id=None):
    """Invalidate the entire KPI cache or a single card_id."""
    if card_id is None:
        _KPI_CACHE.clear()
    else:
        for key in list(_KPI_CACHE.keys()):
            if key.endswith(f":{card_id}"):
                _KPI_CACHE.pop(key, None)


def _style_kpi_value(card_id, value, raw):
    """Post-process specific KPI values for conditional styling."""
    if card_id == "kpi_my_pass_expiry" and raw not in (None, "", "—"):
        try:
            if isinstance(raw, str):
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        raw_date = datetime.strptime(raw.strip(), fmt).date()
                        break
                    except ValueError:
                        continue
                else:
                    return value
            elif isinstance(raw, datetime):
                raw_date = raw.date()
            elif isinstance(raw, date):
                raw_date = raw
            else:
                return value
            diff = (raw_date - date.today()).days
            if diff < 0:
                color = "#de5c52"
            elif diff <= 7:
                color = "#e59620"
            else:
                color = "#17976e"
            return html.Span(value, style={"color": color, "fontWeight": "700"})
        except Exception:
            pass
    return value


# Card_ids that _scoped_override() (below) personalises per-entity, grouped by
# role. Mirrors the "overrides" dict keys inside _scoped_override exactly —
# kept in sync manually since that function is a closure defined inside
# refresh_kpi_values() and isn't importable on its own. Used by
# resolve_seed_kpi_value() so portal_pages.py can compute the SAME cache key
# refresh_kpi_values() would use, without duplicating any SQL here.
SCOPED_CARD_IDS = {
    "apartment": {
        "kpi_apartments_dues", "kpi_receivables_total", "kpi_advance_credits",
        "kpi_my_pending_dues", "kpi_my_overdue_dues", "kpi_receipts_month",
        "kpi_concerns_open", "kpi_concerns_not_closed", "kpi_gate_logs", "kpi_owner_member_since",
        "kpi_events_tickets",
    },
    "vendor": {
        "kpi_receipts_month", "kpi_receivables_total", "kpi_my_pass_expiry",
        "kpi_gate_logs", "kpi_concerns_open", "kpi_concerns_assigned",
        "kpi_concerns_invited", "kpi_concerns_resolved",
    },
    "security": {
        "kpi_security_shift_count", "kpi_security_salary_due",
        "kpi_receipts_month", "kpi_gate_logs", "kpi_concerns_open",
        "kpi_concerns_assigned", "kpi_concerns_resolved",
    },
}


def resolve_seed_kpi_value(sid, role, card_id, entity_id=None):
    """
    Look up a KPI's cached value (never hits the DB) so the server can render
    the real number on first paint instead of a hardcoded "—" placeholder.

    This is what the "blank on cache hit" bug needed: kpi-value elements were
    always created with children="—" (see portal_pages.py's _kpi()), and on a
    tab switch that lands on a cache hit, refresh_kpi_values() runs so fast
    there's effectively no visible gap between the placeholder mounting and
    the real value landing — but relying on that round trip at all was the
    fragile part. Seeding the real value here means a cache-hit tab never
    shows "—" in the first place; the callback becomes a pure top-up for
    genuine cache misses, same as before.

    entity_id should be the apartment/vendor/security id when known (needed
    to look up personalised cards correctly) — pass None if not applicable
    or not yet available; personalised cards will just seed as unresolved
    (None) and fall back to "—" until refresh_kpi_values fills them in, same
    as previously for every card.
    """
    if not sid:
        return None
    is_scoped = card_id in SCOPED_CARD_IDS.get(role, ())
    key = _cache_key(sid, role, card_id, entity_id if is_scoped else None)
    return _get_cached(key)


# ── Helpers ─────────────────────────────────────────────────────────────────
def format_kpi_value(value, fmt: str) -> str:
    if value is None or value == "":
        if fmt == "number":
            return "0"
        if fmt == "currency":
            return "₹0"
        if fmt == "percent":
            return "0.0%"
        # date / time / text genuinely have no zero-equivalent — "—" means
        # "no value" here, not a network error (see refresh_kpi_values error path).
        return "—"
    try:
        if fmt == "number":
            return f"{int(float(value)):,}"
        if fmt == "currency":
            v = float(value)
            neg = v < 0
            v = abs(v)
            if v >= 10_000_000: s = f"₹{v/10_000_000:.2f}Cr"
            elif v >= 100_000:  s = f"₹{v/100_000:.2f}L"
            elif v >= 1_000:    s = f"₹{v/1_000:.1f}K"
            else:               s = f"₹{int(v):,}"
            return f"-{s}" if neg else s
        if fmt == "percent":
            return f"{float(value):.1f}%"
        if fmt == "date":
            if isinstance(value, str):
                for f in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        value = datetime.strptime(value, f).date(); break
                    except ValueError:
                        pass
            if isinstance(value, datetime):
                value = value.date()
            if isinstance(value, date):
                today = date.today()
                diff  = (value - today).days
                if diff == 0:  return "Today"
                if diff == 1:  return "Tomorrow"
                if diff == -1: return "Yesterday"
                if diff > 0:   return f"in {diff}d" if diff < 30 else value.strftime("%d %b %Y")
                return f"{abs(diff)}d ago" if abs(diff) < 30 else value.strftime("%d %b %Y")
            return str(value)
        if fmt == "text":
            return str(value).strip().title() or "—"
        return str(value)
    except (TypeError, ValueError) as exc:
        print(f"⚠️  format_kpi_value({value!r}, {fmt!r}): {exc}")
        return "—"


def _err_toast(msg: str) -> dict:
    return {"type": "error", "message": str(msg)[:200]}


def register_card_catalogue_callbacks(app):
    print("  → Registering card catalogue callbacks…")

    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("⚠️  Cannot import KPI_CARDS — KPI refresh skipped")
        KPI_CARDS = {}

    # Spin the header's refresh icon the instant the button is clicked
    # (client-side, so it's instantaneous rather than waiting on the
    # server round trip below). The server-side callback clears the
    # spin class once refresh_kpi_values() actually finishes.
    app.clientside_callback(
        "function(n){ return (n && n > 0) ? 'fas fa-rotate kpi-refresh-spin' : 'fas fa-rotate'; }",
        Output("hdr-refresh-kpi-icon", "className", allow_duplicate=True),
        Input("hdr-refresh-kpi-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── Debounce: stop rapid repeat clicks on the refresh button ──────────
    # Pure client-side, time-based (1s, set by kpi-refresh-debounce's
    # `interval` in app_shell.py) — deliberately NOT tied to how long the
    # server-side KPI fetch takes, so it debounces the *click*, not the
    # network round trip. Two halves:
    #   1) on click: disable the button immediately and (re)arm the
    #      one-shot Interval (reset n_intervals to 0, un-disable it so it
    #      starts counting down again from this click).
    #   2) when the Interval fires once: re-enable the button and disable
    #      the Interval again so it sits idle until the next click.
    app.clientside_callback(
        "function(n){ return n ? [true, 0, false] : [window.dash_clientside.no_update, "
        "window.dash_clientside.no_update, window.dash_clientside.no_update]; }",
        Output("hdr-refresh-kpi-btn", "disabled", allow_duplicate=True),
        Output("kpi-refresh-debounce", "n_intervals", allow_duplicate=True),
        Output("kpi-refresh-debounce", "disabled", allow_duplicate=True),
        Input("hdr-refresh-kpi-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        "function(n){ return n ? [false, true] : [window.dash_clientside.no_update, "
        "window.dash_clientside.no_update]; }",
        Output("hdr-refresh-kpi-btn", "disabled", allow_duplicate=True),
        Output("kpi-refresh-debounce", "disabled", allow_duplicate=True),
        Input("kpi-refresh-debounce", "n_intervals"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output({"type": "kpi-value", "card_id": ALL}, "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Output("hdr-refresh-kpi-icon", "className", allow_duplicate=True),
        # Manual refresh: the "Refresh KPI" button in the header
        # (app_shell.py's _header()). Only refetches the KPI row already
        # on screen — same cards, same portal/tab — it doesn't navigate or
        # rebuild anything, it just forces the values below to be
        # refetched from the DB instead of served from the KPI cache.
        Input("hdr-refresh-kpi-btn", "n_clicks"),
        # BUG FIX: this used to listen on Input("url", "pathname") — the same
        # raw Input that shell_callbacks.py's route_page() ALSO listens on,
        # and route_page() is what actually rebuilds portal-content (and
        # therefore recreates every kpi-value element) for the new tab.
        # Neither callback declared a dependency on the other, so on a tab
        # click Dash had no guarantee refresh_kpi_values ran AFTER
        # route_page finished rebuilding the DOM — it could fire against
        # the old (about-to-be-replaced) or not-yet-existing kpi-value
        # elements, so its Output writes were silently dropped and every
        # KPI on the new tab was left at its "—" placeholder. Worked on
        # first page load only because Dash's initial-render sequencing is
        # more deterministic than a click-triggered race.
        #
        # Fix: depend on "portal-content-store" instead — route_page()
        # writes to it AFTER portal-content's children (and the new
        # kpi-value elements) are in place, which forces Dash to run this
        # callback strictly after that rebuild. (poll_callbacks.py's
        # load_polls_list already uses this exact pattern for the same
        # reason.) IMPORTANT: this alone wasn't sufficient — route_page()
        # was writing the literal same {"rendered": True} dict on every
        # navigation, which Dash's client treated as "unchanged" and simply
        # never re-fired this Input past the very first page load. Fixed in
        # shell_callbacks.py by stamping that store with a changing
        # timestamp on every call.
        Input("portal-content-store", "data"),
        Input("auth-store", "data"),
        State({"type": "kpi-value", "card_id": ALL}, "id"),
        State("kpi-row", "style"),
        State("url", "pathname"),
        prevent_initial_call="initial_duplicate",
    )
    @require_session
    def refresh_kpi_values(_refresh_clicks, _content_store, auth_data, kpi_ids, kpi_row_style, pathname):
        manual_refresh = ctx.triggered_id == "hdr-refresh-kpi-btn"
        icon_class = "fas fa-rotate"  # always reset the spin once we're done

        if not kpi_ids:
            raise PreventUpdate

        # Skip refresh entirely when KPIs are hidden (e.g. in drill-down mode).
        kpi_row_style = kpi_row_style or {}
        if kpi_row_style.get("display") == "none":
            raise PreventUpdate

        if not auth_data or not auth_data.get("authenticated"):
            return ["—"] * len(kpi_ids), no_update, icon_class

        sid       = auth_data.get("society_id")
        role      = auth_data.get("role", "admin")
        apt_id    = auth_data.get("apartment_id")   # set for 'apartment' portal
        vendor_id = auth_data.get("vendor_id")       # set for 'vendor' portal
        sec_id    = auth_data.get("security_id") or (
            auth_data.get("linked_id") if role == "security" else None
        )
        # gate_access.entity_id is always users.id (see qr_callbacks.py's
        # role_code_map insert), never a linked_id like apartments.id/
        # vendors.id — apt_id/vendor_id above are linked_id (see
        # login_callbacks.py's _build_auth_store). Use this for any
        # gate_access-scoped KPI instead.
        own_user_id = auth_data.get("user_id")
        is_master = role == "master"

        # ── Build portal-specific param resolver ──────────────────────────────
        # KPI queries always bind (society_id,) * n_params.
        # For scoped portals we need to substitute with the entity's own filtered
        # count/sum — but most KPI SQL only accepts society_id.
        # Strategy: for apartment/vendor/security portals, replace multi-param
        # KPIs with entity-scoped SQL where it makes sense; skip irrelevant KPIs.
        #
        # Scoped KPI overrides: return (override_sql, params) or None to use default.
        def _scoped_override(card_id: str):
            """Return (sql, params) scoped to the portal entity, or None for default."""
            if role == "apartment" and apt_id:
                overrides = {
                    # dues / receivables scoped to this apartment
                    "kpi_apartments_dues": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial')",
                        (apt_id,),
                    ),
                    "kpi_receivables_total": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial')",
                        (apt_id,),
                    ),
                    "kpi_advance_credits": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status='credit'",
                        (apt_id,),
                    ),
                    "kpi_my_pending_dues": (
                        "SELECT COALESCE(SUM(amount - paid_amount), 0) AS v "
                        "FROM receivables "
                        "WHERE society_id=%s AND entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial')",
                        (sid, apt_id),
                    ),
                    "kpi_my_overdue_dues": (
                        "SELECT COALESCE(SUM(amount - paid_amount), 0) AS v "
                        "FROM receivables "
                        "WHERE society_id=%s AND entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial') AND due_date<CURRENT_DATE",
                        (sid, apt_id),
                    ),
                    "kpi_receipts_month": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE entity_id=%s AND role='apartment' AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (apt_id,),
                    ),
                    "kpi_concerns_open": (
                        "SELECT COUNT(*)::INT AS v FROM concerns "
                        "WHERE society_id=%s AND created_by=%s AND status='open'",
                        (sid, own_user_id),
                    ),
        "kpi_concerns_not_closed": (
            "SELECT COUNT(*)::INT AS v FROM concerns "
            "WHERE society_id=%s AND created_by=%s AND status != 'closed'",
            (sid, own_user_id),
        ),
        # Owner's bought event tickets for upcoming events — scoped to the
        # apartment owner's user_id (event_tickets.user_id = users.id).
        "kpi_events_tickets": (
            "SELECT COUNT(*)::INT AS v FROM event_ticket_items eti "
            "JOIN event_tickets et ON et.id = eti.event_ticket_id "
            "JOIN events e ON e.id = et.event_id "
            "WHERE et.user_id=%s AND e.event_date>=CURRENT_DATE",
            (own_user_id,),
        ),
                    # kpi_concerns_total is deliberately NOT overridden here —
                    # per the Concerns workflow spec it stays society-wide
                    # even on the Owner portal (see card_catalogue.py).
                    "kpi_gate_logs": (
                        # FIX: gate_access rows for apartment owners are
                        # inserted by qr_callbacks.py's validate_qr_scanned
                        # with entity_id=users.id and role='APT' (see
                        # role_code_map = {"apartment": "APT", ...}). The
                        # previous version filtered entity_id=apt_id
                        # (apartments.id, a linked_id) and role='ADM' (admin's
                        # code) — neither ever matches a real row, so this
                        # KPI always showed 0.
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE entity_id=%s AND role='APT' AND time_in::DATE=CURRENT_DATE",
                        (own_user_id,),
                    ),
                    "kpi_owner_member_since": (
                        "SELECT created_at::DATE AS v FROM apartments WHERE id=%s",
                        (apt_id,),
                    ),
                }
                return overrides.get(card_id)

            if role == "vendor" and vendor_id:
                # NOTE: this branch previously ran an extra
                # "SELECT business_name, name FROM vendors …" round trip on
                # *every* KPI card for the vendor portal (this closure runs
                # once per card_id), into an unused `vendor_assigned_name`
                # local that nothing downstream ever read. That was N wasted
                # DB calls per refresh for no effect — removed.
                overrides = {
                    "kpi_receipts_month": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE entity_id=%s AND role='vendor' AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (vendor_id,),
                    ),
                    "kpi_receipts_total": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE entity_id=%s AND role='vendor' AND status='confirmed'",
                        (vendor_id,),
                    ),
                    "kpi_receivables_total": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='vendor' "
                        "AND status IN ('pending','partial')",
                        (vendor_id,),
                    ),
                    "kpi_my_pass_expiry": (
                        # Mirror fn_vendors_list's pass_expiry calc exactly:
                        # MAX(valid_until) keyed on vendor_passes.user_id (= users.id),
                        # not via a users JOIN on linked_id (which returned NULL
                        # whenever the linkage didn't line up, leaving the card "—").
                        "SELECT MAX(vp.valid_until)::DATE AS v "
                        "FROM vendor_passes vp "
                        "WHERE vp.user_id=%s AND vp.status='active'",
                        (own_user_id,),
                    ),
                    "kpi_gate_logs": (
                        # Same fix as the apartment override above: vendor_id
                        # is linked_id (vendors.id), but gate_access.entity_id
                        # is always users.id.
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE entity_id=%s AND role='VND' AND time_in::DATE=CURRENT_DATE",
                        (own_user_id,),
                    ),
                    "kpi_concerns_open": (
                        "SELECT COUNT(*)::INT AS v FROM concerns c "
                        "WHERE c.society_id=%s AND c.status='open' "
                        "AND EXISTS (SELECT 1 FROM concerns_assigns ca "
                        "WHERE ca.concern_id=c.id AND ca.role='VND' AND ca.entity_id=%s)",
                        (sid, vendor_id),
                    ) if vendor_id else None,
                    "kpi_concerns_assigned": (
                        "SELECT COUNT(*)::INT AS v FROM concerns_assigns "
                        "WHERE society_id=%s AND role='VND' AND entity_id=%s AND status='assigned'",
                        (sid, vendor_id),
                    ) if vendor_id else None,
                    "kpi_concerns_invited": (
                        "SELECT COUNT(*)::INT AS v FROM concerns_assigns "
                        "WHERE society_id=%s AND role='VND' AND entity_id=%s AND status='invited'",
                        (sid, vendor_id),
                    ) if vendor_id else None,
                    "kpi_concerns_resolved": (
                        "SELECT COUNT(*)::INT AS v FROM concerns_assigns "
                        "WHERE society_id=%s AND role='VND' AND entity_id=%s AND status='resolved'",
                        (sid, vendor_id),
                    ) if vendor_id else None,
                }
                return overrides.get(card_id)

            if role == "security" and sec_id:
                # Same dead-code removal as the vendor branch above —
                # `security_assigned_name` was never used.
                overrides = {
                    "kpi_security_shift_count": (
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE entity_id=%s AND role='SEC' AND time_out IS NOT NULL",
                        (own_user_id,),
                    ),
                    "kpi_security_salary_due": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM payables "
                        "WHERE entity_id=%s AND role='security' AND status='pending'",
                        (sec_id,),
                    ),
                    "kpi_receipts_month": (
                        # Security sees society-wide receipts for this month (they collect cash)
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE society_id=%s AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (sid,),
                    ),
                    "kpi_gate_logs": (
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE society_id=%s AND time_in::DATE=CURRENT_DATE",
                        (sid,),
                    ),
                    "kpi_concerns_open": (
                        "SELECT COUNT(*)::INT AS v FROM concerns c "
                        "WHERE c.society_id=%s AND c.status='open' "
                        "AND EXISTS (SELECT 1 FROM concerns_assigns ca "
                        "WHERE ca.concern_id=c.id AND ca.role='SEC' AND ca.entity_id=%s)",
                        (sid, sec_id),
                    ) if sec_id else None,
                    "kpi_concerns_assigned": (
                        "SELECT COUNT(*)::INT AS v FROM concerns_assigns "
                        "WHERE society_id=%s AND role='SEC' AND entity_id=%s AND status='assigned'",
                        (sid, sec_id),
                    ) if sec_id else None,
                    "kpi_concerns_resolved": (
                        "SELECT COUNT(*)::INT AS v FROM concerns_assigns "
                        "WHERE society_id=%s AND role='SEC' AND entity_id=%s AND status='resolved'",
                        (sid, sec_id),
                    ) if sec_id else None,
                }
                return overrides.get(card_id)

            return None

        # entity_id used to scope the cache key for personalised cards —
        # see _cache_key() docstring-comment above.
        scope_entity_id = (
            apt_id if role == "apartment"
            else vendor_id if role == "vendor"
            else sec_id if role == "security"
            else None
        )

        results   = [None] * len(kpi_ids)
        first_err = None
        cache_hits = 0
        active_groups = set()

        # ── Pass 1: resolve cache hits + collect misses to batch ─────────────
        # pending entries: (index, card_id, sql, params, fmt, ckey, is_scoped)
        pending: list[tuple] = []

        for idx, id_dict in enumerate(kpi_ids):
            card_id = id_dict.get("card_id")
            cfg     = KPI_CARDS.get(card_id)

            if not cfg:
                results[idx] = "—"
                continue

            fmt   = cfg.get("format", "number")
            query = cfg.get("query", "")
            group = cfg.get("group", "")
            if group:
                active_groups.add(group)

            override = _scoped_override(card_id)
            entity_for_key = scope_entity_id if override else None
            ckey = _cache_key(sid, role, card_id, entity_for_key)

            # Manual "Refresh KPI" click: force a live DB fetch for every
            # card on the current tab instead of serving whatever's still
            # sitting in the cache (which is exactly what a tab-switch/
            # portal-content re-render — the other Input on this callback —
            # would otherwise happily do within the TTL window).
            cached = None if manual_refresh else _get_cached(ckey)
            if cached is not None:
                results[idx] = cached
                cache_hits += 1
                continue

            if override:
                ov_query, ov_params = override
                pending.append((idx, card_id, ov_query, ov_params, fmt, ckey, True))
                continue

            # Default: use the KPI's own SQL with society_id params
            n_params = cfg.get("params", 0)
            if n_params == 0 or is_master:
                params = ()
            else:
                if not sid:
                    results[idx] = "—"
                    continue
                params = tuple(sid for _ in range(n_params))

            pending.append((idx, card_id, query, params, fmt, ckey, False))

        # ── Pass 2: run every cache miss in ONE round trip via UNION ALL ─────
        # Each pending card's query is a single "SELECT ... AS v" statement,
        # so it can be embedded as a scalar subquery and unioned with the
        # rest, cutting what used to be up to len(pending) separate
        # pool checkouts + network round trips down to exactly one.
        #
        # IMPORTANT: cards return different underlying types — mostly
        # NUMERIC/INT, but e.g. kpi_plan_validity returns a DATE. Postgres
        # requires every branch of a UNION to resolve to one common column
        # type, so mixing a NUMERIC card and a DATE card in the same batch
        # raises "UNION types numeric and date cannot be matched" and the
        # whole batch fails over to the slower per-card fallback path.
        # Casting every branch to ::text sidesteps that: format_kpi_value()
        # already parses date/number/currency/percent values out of plain
        # strings, so nothing downstream needs to change.
        if pending:
            select_parts = []
            batch_params: list = []
            for slot, (idx, card_id, q, params, fmt, ckey, is_scoped) in enumerate(pending):
                select_parts.append(f"SELECT {slot} AS slot, ({q})::text AS v")
                batch_params.extend(params)

            batch_sql = " UNION ALL ".join(select_parts)
            batch_ok = False
            batch_net_error = False
            try:
                rows = db._execute(batch_sql, tuple(batch_params), fetch_all=True)
                value_by_slot = {r["slot"]: r.get("v") for r in (rows or [])}
                batch_ok = True
            except Exception as exc:
                batch_net_error = _is_db_error(exc)
                err_msg = f"KPI batch query failed: {str(exc)[:160]}"
                print(f"⚠️  {err_msg}")

            if batch_ok:
                for slot, (idx, card_id, q, params, fmt, ckey, is_scoped) in enumerate(pending):
                    raw = value_by_slot.get(slot)
                    value = format_kpi_value(raw, fmt)
                    value = _style_kpi_value(card_id, value, raw)
                    _set_cached(ckey, value)
                    results[idx] = value
            else:
                # Fallback: original one-query-per-card behaviour, so a
                # single bad/custom KPI SQL statement can't take the whole
                # row down — each card gets its own isolated try/except.
                for idx, card_id, q, params, fmt, ckey, is_scoped in pending:
                    # If the batch failed due to a network/DB error, individual
                    # queries will also fail identically — skip the DB retry and
                    # check cache directly (check cache → "Network unreachable").
                    if batch_net_error:
                        cached = _get_cached(ckey)
                        if cached is not None:
                            results[idx] = cached
                        else:
                            results[idx] = "Network unreachable"
                    else:
                        try:
                            row = db._execute(q, params, fetch_one=True)
                            raw = (row or {}).get("v")
                            value = format_kpi_value(raw, fmt)
                            value = _style_kpi_value(card_id, value, raw)
                            _set_cached(ckey, value)
                            results[idx] = value
                        except Exception as exc:
                            if _is_db_error(exc):
                                cached = _get_cached(ckey)
                                if cached is not None:
                                    results[idx] = cached
                                else:
                                    results[idx] = "Network unreachable"
                            else:
                                tag = "scoped" if is_scoped else "default"
                                err_msg = f"KPI [{card_id}] {tag}: {str(exc)[:120]}"
                                print(f"  ❌ {err_msg}")
                                results[idx] = "ERR"
                                if first_err is None:
                                    first_err = err_msg

        results = [r if r is not None else "Network unreachable" for r in results]

        if cache_hits and not pending:
            print(
                f"  ✓ KPI cache hits {cache_hits}/{len(results)} (groups: {', '.join(sorted(active_groups)) or '-'}) portal={pathname}"
            )
        elif pending:
            print(
                f"  ⟳ KPI refresh: {cache_hits} cache hit(s), {len(pending)} card(s) fetched in "
                f"{'1 batched query' if len(pending) > 1 else '1 query'} "
                f"(groups: {', '.join(sorted(active_groups)) or '-'}) portal={pathname}"
            )

        if first_err:
            toast = _err_toast(first_err)
        elif manual_refresh:
            toast = {"type": "success", "message": "KPIs refreshed."}
        else:
            toast = no_update

        return results, toast, icon_class