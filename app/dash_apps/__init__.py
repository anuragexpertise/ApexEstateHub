# app/dash_apps/__init__.py
"""
Dash application factory.
Called from app/__init__.py → create_dash_app(flask_app).
"""

import os
import logging

from dash import Dash, html
import dash_bootstrap_components as dbc

log = logging.getLogger(__name__)


def create_dash_app(flask_app):
    here         = os.path.dirname(os.path.abspath(__file__))
    assets_folder = os.path.join(os.path.dirname(here), "assets")
    os.makedirs(assets_folder, exist_ok=True)
    external_scripts = [
        "https://unpkg.com/dash.nprogress@latest/dist/dash.nprogress.js",
    ]
    external_stylesheets = [
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css",
    ]
    dash_app = Dash(
        __name__,
        server               = flask_app,
        url_base_pathname    = "/dashboard/",
        assets_folder        = assets_folder,
        assets_url_path      = "/dashboard/assets",
        external_scripts     = external_scripts,
        external_stylesheets = external_stylesheets,
        suppress_callback_exceptions = True,
        update_title         = "Loading… | EstateHub",
    )
    dash_app.title = "EstateHub"

    # Layout
    try:
        from app.dash_apps.app_shell import shell_layout
        dash_app.layout = shell_layout()
        log.info("Dash layout loaded ✓")
    except Exception as exc:
        log.exception("Dash layout error")
        dash_app.layout = html.Div([
            html.H3("Layout Error", style={"color": "red", "textAlign": "center", "marginTop": "60px"}),
            html.Pre(str(exc), style={"maxWidth": "700px", "margin": "20px auto",
                                      "background": "#f8f9fa", "padding": "14px",
                                      "borderRadius": "8px", "fontSize": "12px"}),
        ])

    # Callbacks
    try:
        from app.dash_apps.callbacks import register_callbacks
        register_callbacks(dash_app)
        log.info("Dash callbacks registered ✓")
    except Exception as exc:
        log.exception("Callback registration error")

    return dash_app
