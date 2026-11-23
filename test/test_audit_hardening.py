"""Hermetic tests for the pre-production audit fixes (no database needed)."""
import importlib
import time

import pytest

from app.utils import rate_limit


def test_rate_limit_blocks_after_max_and_recovers():
    rate_limit.reset()
    assert all(rate_limit.rate_ok("k", 3, 0.2) for _ in range(3))
    assert rate_limit.rate_ok("k", 3, 0.2) is False
    assert rate_limit.rate_ok("other", 3, 0.2) is True      # keys are independent
    time.sleep(0.25)
    assert rate_limit.rate_ok("k", 3, 0.2) is True           # window expired


def test_webpush_expired_subscription_is_purged(monkeypatch):
    """A 410 from the push service must delete the subscription instead of
    raising out of the handler (requests.Response has no .read())."""
    ps = pytest.importorskip("app.services.push_service")

    class Resp:
        status_code = 410
        text = "gone"

    def boom(**_kw):
        raise ps.WebPushException("gone", response=Resp())

    deleted = []
    monkeypatch.setattr(ps, "VAPID_PRIVATE_KEY", "k")
    monkeypatch.setattr(ps, "VAPID_PUBLIC_KEY", "k")
    monkeypatch.setattr(ps, "_create_notification", lambda *a, **k: None)
    monkeypatch.setattr(ps, "get_push_subscriptions",
                        lambda uid: [{"id": 7, "endpoint": "e", "p256dh": "p", "auth": "a"}])
    monkeypatch.setattr(ps, "webpush", boom)
    monkeypatch.setattr(ps.db, "_execute", lambda sql, params=None, **k: deleted.append((sql, params)))

    ok, _msg = ps.send_push_notification(1, "t", "b")
    assert ok is False
    assert any("DELETE FROM push_subscriptions" in s and p == (7,) for s, p in deleted)


def test_webpush_called_with_timeout(monkeypatch):
    ps = pytest.importorskip("app.services.push_service")
    seen = {}
    monkeypatch.setattr(ps, "VAPID_PRIVATE_KEY", "k")
    monkeypatch.setattr(ps, "VAPID_PUBLIC_KEY", "k")
    monkeypatch.setattr(ps, "_create_notification", lambda *a, **k: None)
    monkeypatch.setattr(ps, "get_push_subscriptions",
                        lambda uid: [{"id": 1, "endpoint": "e", "p256dh": "p", "auth": "a"}])
    monkeypatch.setattr(ps, "webpush", lambda **k: seen.update(k))
    monkeypatch.setattr(ps.db, "_execute", lambda *a, **k: None)
    ps.send_push_notification(1, "t", "b")
    assert seen.get("timeout") == ps.WEBPUSH_TIMEOUT


def test_sse_caps_and_release():
    sse = pytest.importorskip("app.routes.sse")
    importlib.reload(sse)
    assert sse._sse_acquire(1) and sse._sse_acquire(1)
    assert sse._sse_acquire(1) is False                      # per-user cap (2)
    sse._sse_release(1)
    assert sse._sse_acquire(1) is True                       # slot freed
    for _ in range(2):
        sse._sse_release(1)
    assert sse._sse_total == 0 and sse._sse_per_user == {}
