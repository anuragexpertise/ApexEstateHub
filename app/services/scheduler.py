from apscheduler.schedulers.background import BackgroundScheduler
import logging
from database.db_manager import db
import app.services.push_service as PushService
from app.services.redis_broker import redis_sync, _REDIS_URL
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

poll_event_signal = threading.Event()

def _get_next_poll_event_time():
    query = '''
    SELECT MIN(event_time) AS next_run FROM (
        SELECT ends_at AS event_time FROM polls WHERE status = 'active' AND ends_at > NOW()
        UNION
        SELECT ends_at - INTERVAL '15 minutes' AS event_time FROM polls WHERE status = 'active' AND reminder_sent_at IS NULL AND (ends_at - INTERVAL '15 minutes') > NOW()
    ) sub;
    '''
    try:
        res = db._execute(query, fetch_one=True)
        return res.get('next_run') if res else None
    except Exception as e:
        logger.error(f"Error fetching next poll event time: {e}")
        return None

def poll_scheduler_loop():
    logger.info("Event-driven poll scheduler loop started.")
    while True:
        poll_event_signal.clear()
        next_run = _get_next_poll_event_time()
        
        if not next_run:
            poll_event_signal.wait()
            continue
            
        now = datetime.now()
        wait_seconds = (next_run - now).total_seconds()
        
        if wait_seconds > 0:
            poll_event_signal.wait(timeout=wait_seconds)
            if poll_event_signal.is_set():
                continue
                
        expire_polls_job()
        time.sleep(1)

def poll_redis_listener_loop():
    if not redis_sync or not _REDIS_URL:
        return
    while True:
        try:
            r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=5, socket_connect_timeout=5)
            pubsub = r.pubsub()
            pubsub.subscribe("poll_schedule_update")
            logger.info("Poll scheduler Redis listener subscribed.")
            for message in pubsub.listen():
                if message["type"] == "message":
                    poll_event_signal.set()
            pubsub.close()
            r.close()
        except Exception as exc:
            time.sleep(2)

def expire_polls_job():
    if not redis_sync or not _REDIS_URL:
        _run_poll_expiry()
        return

    try:
        r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=2)
        acquired = r.set("lock:expire_polls_job", "locked", nx=True, ex=50)
        r.close()
        
        if acquired:
            _run_poll_expiry()
    except Exception as e:
        logger.debug(f"Redis lock error in expire_polls_job: {e}")

def _run_poll_expiry():
    try:
        societies = db._execute("SELECT id FROM societies", fetch_all=True) or []
        for society in societies:
            society_id = society["id"]
            expired = db._execute(
                "SELECT id, society_id, title FROM fn_declare_expired_polls(%s)",
                (society_id,), fetch_all=True,
            ) or []
            for poll in expired:
                try:
                    from app.dash_apps.callbacks.card_catalogue_callbacks import invalidate_kpi_cache
                    invalidate_kpi_cache("polls")
                    PushService.notify_poll_results_declared(
                        society_id, poll.get("title") or "Untitled poll"
                    )
                except Exception:
                    logger.exception(
                        "poll expiry notification failed (poll_id=%s, society_id=%s)",
                        poll.get("id"), society_id,
                    )
    except Exception:
        logger.exception("poll expiry job failed")

    try:
        societies = db._execute("SELECT id FROM societies", fetch_all=True) or []
        for society in societies:
            society_id = society["id"]
            soon_rows = db._execute(
                "SELECT * FROM fn_get_polls_ending_soon(%s, 15)",
                (society_id,), fetch_all=True,
            ) or []
            if soon_rows:
                targets = PushService.get_notification_targets(society_id, roles=["apartment"])
                if targets:
                    for soon in soon_rows:
                        PushService.send_bulk_push(
                            targets, "⏰ Poll Ending Soon",
                            f"Poll '{soon['title']}' ends at {soon['ends_at']}",
                            url="/dashboard/polls", society_id=society_id,
                        )
                        db._execute(
                            "UPDATE polls SET reminder_sent_at = NOW() WHERE id = %s",
                            (soon["id"],),
                        )
    except Exception:
        logger.exception("poll reminder job failed")

def init_scheduler():
    t1 = threading.Thread(target=poll_scheduler_loop, daemon=True, name="poll-scheduler")
    t1.start()
    
    t2 = threading.Thread(target=poll_redis_listener_loop, daemon=True, name="poll-redis-listener")
    t2.start()
    logger.info("Event-driven poll scheduler initialized.")
