 
#!/usr/bin/env python
"""
wsgi.py — Gunicorn / ApexWeave entry point
Usage:  gunicorn wsgi:server --workers 2 --threads 4 --timeout 120
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, create_dash_app

flask_app = create_app(os.getenv('FLASK_CONFIG', 'production'))
dash_app  = create_dash_app(flask_app)

# Gunicorn expects `server`
server = flask_app

if __name__ == '__main__':
    print('=' * 60)
    print('SocietyOS — ApexEstateHub')
    print('http://127.0.0.1:8050/dashboard/')
    print('=' * 60)
    dash_app.run(debug=True, host='0.0.0.0', port=8050)
