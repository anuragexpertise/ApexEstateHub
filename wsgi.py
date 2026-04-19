#!/usr/bin/env python
"""ApexEstateHub - Main Application Entry Point"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, create_dash_app
from dash import html

# Create Flask application
flask_app = create_app('development')

# Create Dash application
dash_app = create_dash_app(flask_app)

if __name__ == '__main__':
    print("=" * 60)
    print("APEXESTATEHUB - STARTING APPLICATION")
    print("=" * 60)
    print("Server: http://127.0.0.1:8050")
    print("Dashboard: http://127.0.0.1:8050/dashboard/")
    print("=" * 60)
    
    dash_app.run(debug=True, host='127.0.0.1', port=8050)