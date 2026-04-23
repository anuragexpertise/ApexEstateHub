"""
app/dash_apps/pages/master_portal.py
Master Admin portal — create / list / delete societies.
Uses card_catalogue make_form_card() for consistency.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc
from app.dash_apps.pages.card_catalogue import make_form_card, make_kpi_card


def master_portal_layout():
    """Master Admin page content."""

    kpi_row = html.Div([
        make_kpi_card('apts_total'),
        make_kpi_card('vendors_total'),
        make_kpi_card('receipts_month'),
        make_kpi_card('balance'),
    ], className='kpi-row mb-4')

    return html.Div([
        html.Div([
            html.H2([html.I(className='fas fa-crown me-2',
                            style={'color': '#f08843'}),
                     'Master Admin Portal'],
                    className='mb-1'),
            html.Small('Manage all societies on this platform',
                       className='text-muted'),
        ], className='mb-4'),

        # KPI row
        kpi_row,

        # Catalogue cards grid
        html.Div([
            html.Div(make_form_card('society_create'), className='mb-4',
                     style={'gridColumn': 'span 2'}),
            html.Div(make_form_card('society_list'),   className='mb-4',
                     style={'gridColumn': 'span 2'}),
        ], style={
            'display': 'grid',
            'gridTemplateColumns': 'repeat(2, 1fr)',
            'gap': '20px',
        }),
    ], style={'padding': '24px'})
