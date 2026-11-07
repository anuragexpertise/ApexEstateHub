# app/dash_apps/pages/attendance_panel.py
"""
Clock in / clock out panel for the four employee portals (security, accountant, supervisor, staff).

Reads and writes through app/services/employee_attendance.py. The gate pass itself (status Active AND duty OnDuty) is
decided in SQL by fn_evaluate_gate_pass; this page only makes someone go on and off duty, and shows their own record.
Component ids are fixed (attendance-status, clock-in-btn, clock-out-btn) because one callback serves every portal;
only one portal is on screen at a time.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app.services import employee_attendance as ea


def _fmt(dt) -> str:
    return dt.strftime("%d %b %Y, %I:%M %p") if dt else "-"


def _span(t_in, t_out) -> str:
    if not t_out:
        return "on duty"
    mins = int((t_out - t_in).total_seconds() // 60)
    return f"{mins // 60}h {mins % 60:02d}m"


def attendance_status_block(society_id, user_id) -> html.Div:
    """Current duty plus the person's latest shifts. Re-rendered after every clock in/out."""
    info = ea.my_attendance(society_id, user_id) if society_id and user_id else None
    if info is None:
        return html.Div("Attendance is kept for the society's employees only.", className="text-muted text-center")
    if info["on_duty_since"]:
        head = [html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#2ecc71"}),
                html.H5("On duty", id="attendance-state"),
                html.Small(f"since {_fmt(info['on_duty_since'])}", className="text-muted")]
    else:
        head = [html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#95a5a6"}),
                html.H5("Off duty", id="attendance-state"),
                html.Small("This account is inactive" if not info["active"] else "Clock in to start your shift",
                           className="text-muted")]
    history = html.Div()
    if info["shifts"]:
        history = html.Div([
            html.Hr(),
            html.Small("Recent shifts", className="text-muted"),
            dbc.Table([
                html.Thead(html.Tr([html.Th("In"), html.Th("Out"), html.Th("Time")])),
                html.Tbody([html.Tr([html.Td(_fmt(r["time_in"])), html.Td(_fmt(r["time_out"])),
                                     html.Td(_span(r["time_in"], r["time_out"]))]) for r in info["shifts"]]),
            ], size="sm", className="mb-0", style={"fontSize": "12px"}),
        ])
    return html.Div([html.Div(head, style={"textAlign": "center"}), history])


def attendance_panel(color: str, society_id, user_id) -> dbc.Card:
    return dbc.Card(
        dbc.CardBody([
            html.Div(id="attendance-status", children=attendance_status_block(society_id, user_id),
                     style={"marginBottom": "16px"}),
            html.Div([dbc.Button("Clock In", id="clock-in-btn", n_clicks=0, color="success", className="me-2"),
                      dbc.Button("Clock Out", id="clock-out-btn", n_clicks=0, color="danger")],
                     style={"textAlign": "center"}),
        ]),
        style={"maxWidth": "420px", "margin": "0 auto", "borderTop": f"3px solid {color}"},
    )
