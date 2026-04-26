# run.py
import os
from app import create_app, create_dash_app

flask_app = create_app(os.getenv('FLASK_CONFIG', 'development'))
dash_app  = create_dash_app(flask_app)
server    = dash_app.server   # gunicorn target

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    server.run(host='0.0.0.0', port=port, debug=debug)

#!/usr/bin/env python3
"""
ApexEstateHub - Application Entry Point
"""

from app import create_app
from app import create_dash_app

# Create Flask application
flask_app = create_app()

# Create Dash application mounted on Flask
dash_app = create_dash_app(flask_app)

if __name__ == '__main__':
    flask_app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )