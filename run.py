#!/usr/bin/env python3
"""
run.py — LOCAL DEVELOPMENT SERVER
Uses: python3 run.py
Features: Debug mode, auto-reload, detailed error pages
"""
import os
from app import create_app, create_dash_app

# Configuration
FLASK_CONFIG = os.getenv('FLASK_CONFIG', 'development')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
PORT = int(os.getenv('PORT', 8050))
HOST = os.getenv('HOST', '0.0.0.0')

# Create Flask app
flask_app = create_app(FLASK_CONFIG)

# Create Dash app
dash_app = create_dash_app(flask_app)
server = dash_app.server

if __name__ == '__main__':
    print(f"\n{'='*70}")
    print(f"🚀 EstateHub - Development Server")
    print(f"{'='*70}")
    print(f"Config: {FLASK_CONFIG}")
    print(f"Debug: {FLASK_DEBUG}")
    print(f"URL: http://{HOST}:{PORT}")
    print(f"{'='*70}\n")
    
    # Development server with auto-reload disabled
    server.run(
        host=HOST,
        port=PORT,
        debug=FLASK_DEBUG,
        use_reloader=False,      # ✅ Auto-reload on code changes
        use_debugger=False,       # ✅ Debugger enabled
    )
