# app/services/redis_broker.py
"""
Redis pub/sub broker for SSE fanout across gunicorn workers.

Each worker runs a background subscriber thread that listens on the
shared Redis channel. When a message arrives, the worker iterates its
local SSE connection map and writes matching events to each open stream.

This is the only cross-process communication path — do NOT use an
in-process dict for fanout; gunicorn workers cannot see each other's
memory.
"""

from __future__ import annotations

import json
import os
import threading
import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL") or os.getenv("KV_URL") or ""

try:
    import redis as redis_sync
    _HAS_REDIS = True
except Exception:
    _HAS_REDIS = False
    redis_sync = None


class RedisBroker:
    """
    Minimal pub/sub facade. Publish is synchronous; subscribe runs a
    daemon thread per process that calls `on_message(channel, payload)`
    for every received message.
    """

    CHANNEL = "sse:events"

    def __init__(self) -> None:
        self._subscriber_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._listeners: dict[int, list] = defaultdict(list)
        self._lock = threading.Lock()
        self._on_message_cb = None

    def register(self, user_id: int, stream):
        with self._lock:
            self._listeners[user_id].append(stream)

    def unregister(self, user_id: int, stream):
        with self._lock:
            try:
                self._listeners[user_id].remove(stream)
            except ValueError:
                pass

    def publish(self, payload: dict):
        """
        Publish a JSON-serialisable dict to the shared channel. Best-effort:
        if Redis is unavailable, log and return silently so the primary
        write path (DB + web push) is never gated on the broker.
        """
        if not _HAS_REDIS or not _REDIS_URL:
            return
        try:
            r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
            r.publish(self.CHANNEL, json.dumps(payload))
            r.close()
        except Exception as exc:
            logger.debug("Redis publish failed (non-fatal): %s", exc)

    def start(self, on_message):
        """
        Start the background subscriber thread. `on_message` is called
        for every event received from Redis.
        """
        if self._subscriber_thread and self._subscriber_thread.is_alive():
            return
        self._on_message_cb = on_message
        self._stop.clear()
        self._subscriber_thread = threading.Thread(
            target=self._subscribe_loop, daemon=True, name="sse-redis-sub"
        )
        self._subscriber_thread.start()
        logger.info("SSE Redis subscriber started")

    def stop(self):
        self._stop.set()

    def _subscribe_loop(self):
        if not _HAS_REDIS or not _REDIS_URL:
            return
        while not self._stop.is_set():
            try:
                r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
                pubsub = r.pubsub()
                pubsub.subscribe(self.CHANNEL)
                logger.info("SSE Redis subscribed to %s", self.CHANNEL)
                for message in pubsub.listen():
                    if self._stop.is_set():
                        break
                    if message["type"] != "message":
                        continue
                    try:
                        payload = json.loads(message["data"])
                    except Exception:
                        continue
                    if self._on_message_cb:
                        try:
                            self._on_message_cb(payload)
                        except Exception as exc:
                            logger.debug("on_message handler error: %s", exc)
                pubsub.close()
                r.close()
            except Exception as exc:
                logger.debug("Redis subscribe loop error (will retry): %s", exc)
                time.sleep(2)

    def dispatch_to_listeners(self, payload: dict):
        """
        Push a payload to every local SSE stream that matches the target
        user_id or (if broadcast) the society_id.
        """
        target_user = payload.get("user_id")
        society_id = payload.get("society_id")
        data = json.dumps(payload) + "\n"
        dead: list[tuple] = []
        with self._lock:
            if target_user:
                for stream in self._listeners.get(target_user, []):
                    try:
                        stream.write(f"data: {data}\n\n")
                    except Exception:
                        dead.append((target_user, stream))
            if society_id:
                for uid, streams in self._listeners.items():
                    if uid == target_user:
                        continue
                    for stream in streams:
                        try:
                            stream.write(f"data: {data}\n\n")
                        except Exception:
                            dead.append((uid, stream))
        for uid, stream in dead:
            self.unregister(uid, stream)


broker = RedisBroker()
