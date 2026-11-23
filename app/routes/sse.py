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
import logging
import os
import threading
import time

from flask import Blueprint, Response, stream_with_context
from flask_login import current_user

from app.services.redis_broker import broker

logger = logging.getLogger(__name__)
sse_bp = Blueprint('sse', __name__)

HEARTBEAT_INTERVAL = 15  # seconds

# Every open stream pins one gunicorn thread for its whole lifetime. With the
# Procfile's 2 workers x 8 threads, unbounded streams starve normal requests.
# Caps are per worker process; tune with the env vars below.
SSE_MAX_PER_USER = int(os.getenv('SSE_MAX_PER_USER', '2'))
SSE_MAX_PER_WORKER = int(os.getenv('SSE_MAX_PER_WORKER', '5'))
_sse_lock = threading.Lock()
_sse_per_user: dict[int, int] = {}
_sse_total = 0


def _sse_acquire(user_id: int) -> bool:
    global _sse_total
    with _sse_lock:
        if _sse_total >= SSE_MAX_PER_WORKER or _sse_per_user.get(user_id, 0) >= SSE_MAX_PER_USER:
            return False
        _sse_per_user[user_id] = _sse_per_user.get(user_id, 0) + 1
        _sse_total += 1
        return True


def _sse_release(user_id: int) -> None:
    global _sse_total
    with _sse_lock:
        n = _sse_per_user.get(user_id, 0) - 1
        if n > 0:
            _sse_per_user[user_id] = n
        else:
            _sse_per_user.pop(user_id, None)
        _sse_total = max(0, _sse_total - 1)


@sse_bp.route('/api/sse/events')
def events():
    if not current_user.is_authenticated:
        return Response("Unauthorized", status=401, mimetype="text/plain")

    user_id = int(current_user.get_id())
    society_id = getattr(current_user, 'society_id', None)

    if not _sse_acquire(user_id):
        return Response("Too many open streams", status=429, mimetype="text/plain",
                        headers={"Retry-After": "30"})

    def _stream():
        queue = []
        lock = threading.Lock()

        def _local_push(payload):
            with lock:
                queue.append(payload)

        broker.register(user_id, society_id, _local_push)

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

    resp = Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    # call_on_close runs even if the client disconnects before the generator
    # produces its first byte, so the slot can never leak.
    resp.call_on_close(lambda: _sse_release(user_id))
    return resp
