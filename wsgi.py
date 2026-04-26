# wsgi.py — Gunicorn entry point
import os
import sys

# Ensure project root is on path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Debug: Check if static folder exists
static_path = os.path.join(project_root, 'app', 'assets')
css_path = os.path.join(static_path, 'css', 'style.css')

print(f"Project root: {project_root}")
print(f"Static folder exists: {os.path.exists(static_path)}")
print(f"CSS file exists: {os.path.exists(css_path)}")

if os.path.exists(css_path):
    print(f"✓ CSS file found at: {css_path}")
else:
    print(f"✗ CSS file NOT found at: {css_path}")
    print("  Expected location: /path/to/your/project/static/css/style.css")

from app import create_app, create_dash_app

flask_app = create_app()
dash_app = create_dash_app(flask_app)
server = dash_app.server  # Gunicorn target

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    server.run(host='0.0.0.0', port=port, debug=False)