# wsgi.py — REPLACE ENTIRE FILE
import os, sys
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app import create_app, create_dash_app

flask_app = create_app(os.getenv('FLASK_CONFIG', 'production'))
dash_app  = create_dash_app(flask_app)
server    = dash_app.server   # gunicorn target

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 8050))
    server.run(host='0.0.0.0', port=port, debug=False)