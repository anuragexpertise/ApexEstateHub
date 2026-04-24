# wsgi.py  — Gunicorn entry point
import os, sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, create_dash_app

flask_app  = create_app()
dash_app   = create_dash_app(flask_app)
server     = flask_app          # gunicorn targets `server`

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    server.run(host='0.0.0.0', port=port, debug=debug)