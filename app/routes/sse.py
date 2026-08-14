# app/routes/sse.py
"""
Server-Sent Events endpoint for real-time in-app notifications.

Auth: Flask-Login server-side cookie session. EventSource on the same
origin automatically includes cookies, so no custom headers or query-
string tokens are needed.

Fanatout: Redis pub/sub (app/services/redis_broker.py) relays events
from the publishing worker to every worker that has an open SSE stream
for the target user or society.
"""

from __future__ import annotations

import json
import time
import logging
import threading

from flask import Blueprint, Response, stream_with_context
from flask_login import current_user

from app.services.redis_broker import broker

logger = logging.getLogger(__name__)
sse_bp = Blueprint('sse', __name__)

HEARTBEAT_INTERVAL = 15  # seconds


@sse_bp.route('/api/sse/events')
def events():
    if not current_user.is_authenticated:
        return Response("Unauthorized", status=401, mimetype="text/plain")

    user_id = int(current_user.get_id())

    def _stream():
        queue = []
        lock = threading.Lock()

        def _local_push(payload):
            with lock:
                queue.append(payload)

        broker.register(user_id, _local_push)

        try:
            yield f": connected user={user_id}\n\n"
            last_heartbeat = time.monotonic()
            while True:
                with lock:
                    while queue:
                        payload = queue.pop(0)
                        yield f"data: {json.dumps(payload)}\n\n"
                now = time.monotonic()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now
                time.sleep(0.5)
        except GeneratorExit:
            pass
        finally:
            broker.unregister(user_id, _local_push)

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
