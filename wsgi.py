#!/usr/bin/env python3
"""
wsgi.py — PRODUCTION DEPLOYMENT
Uses: gunicorn -w 4 -b 0.0.0.0:8050 wsgi:server
Features: No debug, no reload, gunicorn-safe, production config
"""
import os
import sys
from pathlib import Path

# Add project root to path (for imports)
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# ════════════════════════════════════════════════════════════════
# CREATE APP (Production Config)
# ════════════════════════════════════════════════════════════════

from app import create_app, create_dash_app

# Use production config by default
flask_app = create_app(os.getenv('FLASK_CONFIG', 'production'))
dash_app = create_dash_app(flask_app)
server = dash_app.server  # ← gunicorn will import and use this
# application= server
# ════════════════════════════════════════════════════════════════
# GUNICORN WORKER CONFIGURATION (optional)
# ════════════════════════════════════════════════════════════════

def when_ready(server):
    """Called when gunicorn server starts."""
    print(f"✅ EstateHub production server is ready")

def post_fork(server, worker):
    """Called after a worker is forked."""
    print(f"🔄 Worker {worker.pid} started")

def post_worker_exit(server, worker):
    """Called after a worker exits."""
    print(f"🔄 Worker {worker.pid} exited")

# ════════════════════════════════════════════════════════════════
# LOCAL TESTING ONLY (remove for production)
# ════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # For local testing only - use run.py instead!
    port = int(os.getenv('PORT', 8050))
    print("\n⚠️  WARNING: Using wsgi.py directly")
    print("   For development: python3 run.py")
    print("   For production:  gunicorn -w 4 -b 0.0.0.0:8050 wsgi:server\n")
    
    server.run(
        host='0.0.0.0',
        port=port,
        debug=True,           # ✅ No debug in production
        use_reloader=False,    # ✅ No reload with gunicorn
    )
