# app/dash_apps/__init__.py
import sys
import os

from dash import Dash, html
import dash_bootstrap_components as dbc

def create_dash_app(flask_app):
    """Create and configure the Dash application"""

    print("\n" + "="*60)
    print("🔄 CREATING DASH APP - VERSION 2.0")
    print("="*60)

    dash_app = Dash(
        __name__,
        server=flask_app,
        url_base_pathname='/dashboard/',
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css'
        ],
        suppress_callback_exceptions=True,
        assets_folder='app/static/assets',
        assets_url_path='/static'
    )

    # CRITICAL: Explicitly load the layout
    print("\n📦 Loading layout from app_shell.py...")

    # Direct import with module reload
    import importlib

    # Force reload of app_shell module
    if 'app.dash_apps.app_shell' in sys.modules:
        del sys.modules['app.dash_apps.app_shell']
        print("  → Removed cached app_shell module")

    try:
        from app.dash_apps import app_shell
        importlib.reload(app_shell)
        dash_app.layout = app_shell.shell_layout()
        print("✅ SUCCESS: Full shell layout loaded!")
        print(f"   Layout type: {type(dash_app.layout)}")
        print(f"   Has children: {hasattr(dash_app.layout, 'children')}")
    except Exception as e:
        print(f"❌ ERROR loading layout: {e}")
        import traceback
        traceback.print_exc()
        # Emergency fallback
        dash_app.layout = html.Div(
            [
                html.H1("Layout Error", style={"color": "red", "textAlign": "center"}),
                html.P(str(e)),
                html.Pre(traceback.format_exc())
            ]
        )

    # Register callbacks
    print("\n📞 Registering callbacks...")
    try:
        from app.dash_apps.callbacks import register_all_callbacks
        register_all_callbacks(dash_app)
        print("✅ Callbacks registered")
    except Exception as e:
        print(f"❌ Error registering callbacks: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("✅ DASH APP CREATION COMPLETE")
    print("="*60 + "\n")

    return dash_app
