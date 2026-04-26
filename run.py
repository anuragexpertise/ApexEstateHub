# run.py — REPLACE ENTIRE FILE
import os
from app import create_app, create_dash_app

flask_app = create_app(os.getenv('FLASK_CONFIG', 'development'))
dash_app  = create_dash_app(flask_app)
server    = dash_app.server

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    server.run(host='0.0.0.0', port=port, debug=debug)