# wsgi.py
import sys
if not hasattr(sys, 'warnoptions'):
    sys.warnoptions = []

from app import create_app, create_dash_app

flask_app = create_app()
dash_app = create_dash_app(flask_app)
server = flask_app

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8050))
    server.run(host='0.0.0.0', port=port, debug=True)