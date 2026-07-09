# app/dash_apps/callbacks/customize_kpi_callbacks.py
"""
Callbacks for KPI Customization Tab in Admin Portal
FIXED VERSION — duplicate-key-safe KPI_PORTAL_MAP using list-of-tuples.
"""

from __future__ import annotations
import time
import json
from dash import Input, Output, State, html, dcc, ctx, no_update
import dash_bootstrap_components as dbc
from app.dash_apps.pages.card_catalogue import KPI_CARDS
from app.dash_apps.callbacks.drilldown_callbacks import get_entity_meta

# ════════════════════════════════════════════════════════════════
# KPI METADATA — list-of-tuples so duplicate card_ids are preserved
# Each entry: (card_id, portal, tab, group)
# ════════════════════════════════════════════════════════════════

_KPI_PORTAL_ENTRIES: list[tuple[str, str, str, str]] = [
    # ADMIN PORTAL - Dashboard tab
    ("kpi_apartments_total", "admin", "dashboard", "Apartments"),
    ("kpi_apartments_dues", "admin", "dashboard", "Apartments"),
    ("kpi_vendors_total", "admin", "dashboard", "Vendors"),
    ("kpi_security_total", "admin", "dashboard", "Security"),
    ("kpi_security_on_duty", "admin", "dashboard", "Security"),
    ("kpi_gate_logs", "admin", "dashboard", "Gate"),
    ("kpi_receipts_month", "admin", "dashboard", "Cashbook"),
    ("kpi_expenses_month", "admin", "dashboard", "Cashbook"),
    ("kpi_cash_in_hand", "admin", "dashboard", "Cashbook"),
    ("kpi_bank_balance", "admin", "dashboard", "Cashbook"),
    # ADMIN - Enroll tab
    ("kpi_apartments_total", "admin", "enroll", "Entities"),
    ("kpi_vendors_total", "admin", "enroll", "Entities"),
    ("kpi_security_total", "admin", "enroll", "Entities"),
    # ADMIN - Cashbook tab
    ("kpi_receivables_total", "admin", "cashbook", "Cashbook"),
    ("kpi_payables_total", "admin", "cashbook", "Cashbook"),
    ("kpi_receipts_month", "admin", "cashbook", "Cashbook"),
    ("kpi_expenses_month", "admin", "cashbook", "Cashbook"),
    ("kpi_cash_in_hand", "admin", "cashbook", "Cashbook"),
    ("kpi_bank_balance", "admin", "cashbook", "Cashbook"),
    # ADMIN - Receipts tab
    ("kpi_receipts_month", "admin", "receipts", "Cashbook"),
    ("kpi_receivables_total", "admin", "receipts", "Cashbook"),
    ("kpi_maintenance_due", "admin", "receipts", "Cashbook"),
    ("kpi_late_fees_due", "admin", "receipts", "Cashbook"),
    ("kpi_vendor_payables_due", "admin", "receipts", "Cashbook"),
    # ADMIN - Expenses tab
    ("kpi_expenses_month", "admin", "expenses", "Cashbook"),
    ("kpi_payables_total", "admin", "expenses", "Cashbook"),
    ("kpi_security_salaries_due", "admin", "expenses", "Expenses"),
    ("kpi_amc_due", "admin", "expenses", "Expenses"),
    # ADMIN - Events tab
    ("kpi_events_total", "admin", "events", "Events"),
    # ADMIN - Concerns tab
    ("kpi_concerns_open", "admin", "concerns", "Concerns"),
    # ADMIN - Settings tab
    ("kpi_societies_calc_start_date", "admin", "settings", "Settings"),
    ("kpi_plan_validity", "admin", "settings", "Settings"),
    ("kpi_accounts_count", "admin", "settings", "Settings"),
    ("kpi_apt_charges", "admin", "settings", "Settings"),
    ("kpi_ven_charges", "admin", "settings", "Settings"),
    ("kpi_sec_charges", "admin", "settings", "Settings"),
    ("kpi_attendance", "admin", "settings", "Settings"),
    # ADMIN - Financials tab
    ("kpi_cash_in_hand", "admin", "financials", "Cashbook"),
    ("kpi_bank_balance", "admin", "financials", "Cashbook"),
    ("kpi_receivables_total", "admin", "financials", "Receivables"),
    ("kpi_receivables_overdue", "admin", "financials", "Receivables"),
    ("kpi_payables_total", "admin", "financials", "Payables"),
    ("kpi_security_salaries_due", "admin", "financials", "Payables"),
    ("kpi_receipts_month", "admin", "financials", "Receipts"),
    ("kpi_receipts_total", "admin", "financials", "Receipts"),
    ("kpi_expenses_month", "admin", "financials", "Expenses"),
    ("kpi_expenses_total", "admin", "financials", "Expenses"),
    ("kpi_advance_credits", "admin", "financials", "Prepaid"),
    # MASTER PORTAL - Dashboard
    ("kpi_societies_total", "master", "dashboard", "Master"),
    ("kpi_societies_free", "master", "dashboard", "Master"),
    ("kpi_societies_9Apts", "master", "dashboard", "Master"),
    ("kpi_societies_99Apts", "master", "dashboard", "Master"),
    ("kpi_societies_999Apts", "master", "dashboard", "Master"),
    ("kpi_societies_unlimited", "master", "dashboard", "Master"),
    ("kpi_master_apartments_total", "master", "dashboard", "Master"),
    ("kpi_master_vendors_total", "master", "dashboard", "Master"),
    ("kpi_master_security_total", "master", "dashboard", "Master"),
    # APARTMENT PORTAL - Dashboard
    ("kpi_apartments_dues", "apartment", "dashboard", "Account"),
    ("kpi_concerns_open", "apartment", "dashboard", "Concerns"),
    ("kpi_events_total", "apartment", "dashboard", "Events"),
    ("kpi_gate_logs", "apartment", "dashboard", "Gate"),
    ("kpi_receipts_month", "apartment", "dashboard", "Payments"),
    ("kpi_receivables_total", "apartment", "dashboard", "Payments"),
    # APARTMENT - Cashbook
    ("kpi_receipts_month", "apartment", "cashbook", "Cashbook"),
    ("kpi_receivables_total", "apartment", "cashbook", "Cashbook"),
    # APARTMENT - Payments
    ("kpi_receivables_total", "apartment", "payments", "Dues"),
    ("kpi_apartments_dues", "apartment", "payments", "Dues"),
    # APARTMENT - Charges
    ("kpi_maintainence_charges", "apartment", "charges", "Charges"),
    ("kpi_apartment_fines", "apartment", "charges", "Charges"),
    ("kpi_apartment_other_charges", "apartment", "charges", "Charges"),
    # APARTMENT - Events / Concerns / Settings
    ("kpi_events_total", "apartment", "events", "Events"),
    ("kpi_concerns_open", "apartment", "concerns", "Concerns"),
    ("kpi_apartment_date", "apartment", "settings", "Profile"),
    # VENDOR PORTAL - Dashboard
    ("kpi_concerns_open", "vendor", "dashboard", "Jobs"),
    ("kpi_events_total", "vendor", "dashboard", "Events"),
    ("kpi_receivables_total", "vendor", "dashboard", "Payments"),
    ("kpi_receipts_month", "vendor", "dashboard", "Payments"),
    ("kpi_gate_logs", "vendor", "dashboard", "Gate"),
    # VENDOR - Cashbook / Charges / Events / Settings
    ("kpi_receivables_total", "vendor", "cashbook", "Payments"),
    ("kpi_receipts_month", "vendor", "cashbook", "Payments"),
    ("kpi_vendor_fines", "vendor", "charges", "Charges"),
    ("kpi_vendor_other_charges", "vendor", "charges", "Charges"),
    ("kpi_events_total", "vendor", "events", "Events"),
    ("kpi_vendor_date", "vendor", "settings", "Profile"),
    # SECURITY PORTAL - Dashboard
    ("kpi_apartments_total", "security", "dashboard", "Users"),
    ("kpi_vendors_total", "security", "dashboard", "Users"),
    ("kpi_security_total", "security", "dashboard", "Users"),
    ("kpi_security_shift_count", "security", "dashboard", "Users"),
    ("kpi_receivables_total", "security", "dashboard", "Cash"),
    ("kpi_gate_logs", "security", "dashboard", "Gate"),
    # SECURITY - Cashbook / Charges / Payments / Events / Receipt / Settings
    ("kpi_receivables_total", "security", "cashbook", "Payments"),
    ("kpi_payables_total", "security", "cashbook", "Payments"),
    ("kpi_receipts_month", "security", "cashbook", "Payments"),
    ("kpi_expenses_month", "security", "cashbook", "Payments"),
    ("kpi_security_fines", "security", "charges", "Charges"),
    ("kpi_security_other_charges", "security", "charges", "Charges"),
    ("kpi_receipts_in_hand_total", "security", "charges", "Cash"),
    ("kpi_security_salary_due", "security", "payments", "Salary"),
    ("kpi_security_bonus_due", "security", "payments", "Bonus"),
    ("kpi_events_total", "security", "events", "Events"),
    ("kpi_receipts_month", "security", "receipt", "Cash"),
    ("kpi_security_date", "security", "settings", "Profile"),
    ("kpi_security_salary_per_shift", "security", "settings", "Profile"),
    ("kpi_security_shift", "security", "settings", "Profile"),
]

# Legacy dict — last-assignment-wins per key (acceptable for single-portal lookups)
KPI_PORTAL_MAP: dict[str, dict] = {}
for _cid, _portal, _tab, _group in _KPI_PORTAL_ENTRIES:
    KPI_PORTAL_MAP[_cid] = {"portal": _portal, "tab": _tab, "group": _group}


def get_portals() -> list[str]:
    return sorted({p for _, p, _, _ in _KPI_PORTAL_ENTRIES})


def get_tabs_for_portal(portal: str) -> list[str]:
    return sorted({t for _, p, t, _ in _KPI_PORTAL_ENTRIES if p == portal})


def get_kpi_ids_for_portal_tab(portal: str, tab: str) -> list[str]:
    """Return deduplicated card_ids for the given portal+tab."""
    seen: set[str] = set()
    result: list[str] = []
    for cid, p, t, _ in _KPI_PORTAL_ENTRIES:
        if p == portal and t == tab and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result


# ════════════════════════════════════════════════════════════════
# REGISTERED CALLBACKS
# ════════════════════════════════════════════════════════════════


def register_customize_kpi_callbacks(app):
    print("  → Registering customize KPI callbacks...")

    @app.callback(
        Output("customize-tab-select", "options"),
        Input("customize-portal-select", "value"),
        prevent_initial_call=False,
    )
    def update_tab_options(selected_portal):
        if not selected_portal:
            selected_portal = "admin"
        return [
            {"label": t.replace("_", " ").title(), "value": t}
            for t in get_tabs_for_portal(selected_portal)
        ]

    @app.callback(
        Output("customize-kpi-select", "options"),
        Input("customize-portal-select", "value"),
        Input("customize-tab-select", "value"),
        prevent_initial_call=False,
    )
    def update_kpi_options(selected_portal, selected_tab):
        if not selected_portal:
            selected_portal = "admin"
        if not selected_tab:
            return []
        ids = get_kpi_ids_for_portal_tab(selected_portal, selected_tab)
        return [
            {"label": KPI_CARDS.get(cid, {}).get("title", cid), "value": cid}
            for cid in ids
            if cid in KPI_CARDS
        ]

    @app.callback(
        Output("customize-kpi-sql", "value"),
        Output("customize-kpi-metadata", "children"),
        Input("customize-kpi-select", "value"),
        prevent_initial_call=False,
    )
    def update_kpi_details(selected_kpi_id):
        if not selected_kpi_id or selected_kpi_id not in KPI_CARDS:
            return "-- No KPI selected", html.Div(
                "Select a KPI to view details", className="text-muted"
            )
        cfg = KPI_CARDS[selected_kpi_id]
        query = (cfg.get("query") or "").strip()
        params = cfg.get("params", 0)
        fmt = cfg.get("format", "number")
        icon = cfg.get("icon", "fa-chart-bar")
        color = cfg.get("color", "#3498db")
        title = cfg.get("title", selected_kpi_id)
        group = cfg.get("group", "")
        portal_meta = KPI_PORTAL_MAP.get(selected_kpi_id, {})

        metadata_card = dbc.Card(
            [
                dbc.CardBody(
                    [
                        html.Div(
                            [
                                html.I(
                                    className=f"fas {icon}",
                                    style={
                                        "color": color,
                                        "fontSize": "22px",
                                        "marginRight": "8px",
                                    },
                                ),
                                html.Span(
                                    title,
                                    style={
                                        "fontWeight": "700",
                                        "fontSize": "14px",
                                        "color": "#15304f",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "marginBottom": "10px",
                            },
                        ),
                        html.Hr(style={"margin": "8px 0"}),
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        _meta_row("Parameters", str(params)),
                                        _meta_row("Format", fmt),
                                        _meta_row("Group", group or "—"),
                                    ],
                                    width=6,
                                ),
                                dbc.Col(
                                    [
                                        _meta_row(
                                            "Portal",
                                            portal_meta.get("portal", "—").title(),
                                        ),
                                        _meta_row(
                                            "Tab",
                                            portal_meta.get("tab", "—")
                                            .replace("_", " ")
                                            .title(),
                                        ),
                                        dbc.Badge(
                                            [
                                                html.I(
                                                    className="fas fa-database me-1"
                                                ),
                                                "DB Query",
                                            ],
                                            color="info",
                                            style={
                                                "fontSize": "10px",
                                                "marginTop": "8px",
                                            },
                                        ),
                                    ],
                                    width=6,
                                ),
                            ]
                        ),
                    ],
                    style={"padding": "12px"},
                ),
            ],
            style={"borderRadius": "10px", "border": f"1px solid {color}33"},
        )
        return query, metadata_card

    # ── Test SQL ─────────────────────────────────────────────────
    @app.callback(
        Output("kpi-test-result", "children"),
        Input("kpi-test-sql-btn", "n_clicks"),
        State("customize-kpi-sql", "value"),
        State("customize-kpi-select", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def test_kpi_sql(n_clicks, sql_text, kpi_id, auth_data):
        if not n_clicks or not sql_text:
            return no_update
        from database.db_manager import db
        from app.dash_apps.callbacks.card_catalogue_callbacks import format_kpi_value

        sid = (auth_data or {}).get("society_id")
        cfg = KPI_CARDS.get(kpi_id or "", {})
        n_params = cfg.get("params", sql_text.count("%s"))
        fmt = cfg.get("format", "number")

        if n_params == 0:
            params: tuple = ()
        elif sid:
            params = tuple(sid for _ in range(n_params))
        else:
            return dbc.Alert(
                "No society_id in session — cannot bind params.",
                color="warning",
                className="mt-2",
                style={"fontSize": "12px"},
            )

        t0 = time.perf_counter()
        try:
            row = db._execute(sql_text.strip(), params, fetch_one=True)
            elapsed = (time.perf_counter() - t0) * 1000
            raw = (row or {}).get("v") if row else None
            fmt_val = format_kpi_value(raw, fmt) if raw is not None else "NULL"
            color = "success" if raw is not None else "warning"
            return dbc.Alert(
                [
                    html.Strong("Raw: "),
                    html.Code(
                        str(raw), style={"fontSize": "13px", "marginRight": "12px"}
                    ),
                    html.Strong("Formatted: "),
                    html.Span(
                        fmt_val,
                        style={
                            "fontSize": "14px",
                            "fontWeight": "700",
                            "marginRight": "12px",
                        },
                    ),
                    html.Small(f"({elapsed:.1f} ms)", style={"color": "#888"}),
                ],
                color=color,
                className="mt-2 py-2",
                style={"fontSize": "12px"},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return dbc.Alert(
                [
                    html.Strong("ERROR: "),
                    html.Code(
                        str(e), style={"fontSize": "11px", "whiteSpace": "pre-wrap"}
                    ),
                    html.Br(),
                    html.Small(f"({elapsed:.1f} ms)", style={"color": "#888"}),
                ],
                color="danger",
                className="mt-2 py-2",
                style={"fontSize": "12px"},
            )

    # ── Export SQL ───────────────────────────────────────────────
    @app.callback(
        Output("kpi-export-result", "children"),
        Output("kpi-export-download", "data"),
        Input("kpi-export-sql-btn", "n_clicks"),
        State("customize-kpi-sql", "value"),
        State("customize-kpi-select", "value"),
        prevent_initial_call=True,
    )
    def export_kpi_sql(n_clicks, sql_text, kpi_id):
        if not n_clicks or not sql_text:
            return no_update, no_update
        cfg = KPI_CARDS.get(kpi_id or "", {})
        title = cfg.get("title", kpi_id or "unknown")
        block = (
            f"\n-- ── KPI: {kpi_id}  ({title}) ─────────────────────────\n"
            f"-- Format: {cfg.get('format','?')}  |  Params: {cfg.get('params',0)}\n"
            + sql_text.strip()
            + ";\n"
        )
        msg = dbc.Alert(
            [
                html.I(className="fas fa-check-circle me-2"),
                f"SQL block for '{title}' ready.",
            ],
            color="success",
            className="mt-2 py-2",
            style={"fontSize": "12px"},
        )
        return msg, dcc.send_string(block, filename=f"kpi_{kpi_id}.sql")

    # ── Entity reference ─────────────────────────────────────────
    @app.callback(
        Output("customize-entity-reference", "children"),
        Input("customize-kpi-select", "value"),
        prevent_initial_call=False,
    )
    def load_entity_reference(selected_kpi_id):
        if not selected_kpi_id:
            return html.Div(
                "Select a KPI to view entity details", className="text-muted"
            )
        entity = None
        for key in get_entity_meta():
            if key in selected_kpi_id:
                entity = key
                break
        if not entity:
            return html.Div("No entity metadata available", className="text-muted")
        meta = get_entity_meta()[entity]
        return dbc.Card(
            [
                dbc.CardHeader(
                    html.Div(
                        [
                            html.I(
                                className=f"fas {meta.get('list_icon','fa-list')} me-2",
                                style={"color": meta.get("profile_color", "#1d74d8")},
                            ),
                            html.Strong(f"{entity.title()} Entity"),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    style={"padding": "10px 14px"},
                ),
                dbc.CardBody(
                    [
                        _ref_row(
                            "List Columns",
                            ", ".join(
                                c.get("name", c.get("field", "")).title()
                                for c in meta.get("list_columns", [])
                            ),
                        ),
                        html.Hr(style={"margin": "6px 0"}),
                        _ref_row(
                            "Profile Fields",
                            ", ".join(
                                f.get("label", f.get("field", "")).title()
                                for f in meta.get("profile_fields", [])
                            ),
                        ),
                        html.Hr(style={"margin": "6px 0"}),
                        _ref_row(
                            "Profile Actions",
                            ", ".join(
                                a.get("label", a.get("action_id", ""))
                                for a in meta.get("profile_actions", [])
                            ),
                        ),
                    ],
                    style={"padding": "12px"},
                ),
            ],
            style={"borderRadius": "10px", "marginTop": "10px"},
        )

    print("  ✓ Customize KPI callbacks registered")


def _meta_row(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Small(
                label,
                style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"},
            ),
            html.Div(
                value,
                style={
                    "fontSize": "13px",
                    "color": "#15304f",
                    "fontWeight": "500",
                    "marginBottom": "8px",
                },
            ),
        ]
    )


def _ref_row(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Small(
                label,
                style={"fontWeight": "600", "color": "#15304f", "fontSize": "11px"},
            ),
            html.Div(
                value,
                style={
                    "fontSize": "11px",
                    "color": "#666",
                    "fontFamily": "monospace",
                    "marginBottom": "8px",
                },
            ),
        ]
    )
