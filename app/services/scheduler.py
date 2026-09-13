from apscheduler.schedulers.background import BackgroundScheduler
import logging
from database.db_manager import db
import app.services.push_service as PushService
from app.services.redis_broker import redis_sync, _REDIS_URL

logger = logging.getLogger(__name__)

def expire_polls_job():
    """
    Checks for expired polls and triggers their expiry logic.
    Uses a Redis lock to ensure that if multiple gunicorn workers
    are running this background scheduler, only one executes the job.
    """
    if not redis_sync or not _REDIS_URL:
        # Fallback if no redis, but might run multiple times if multiple workers
        _run_poll_expiry()
        return

    try:
        r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=2)
        # Try to acquire a lock for 50 seconds (since job runs every 60 seconds)
        acquired = r.set("lock:expire_polls_job", "locked", nx=True, ex=50)
        r.close()
        
        if acquired:
            _run_poll_expiry()
    except Exception as e:
        logger.debug(f"Redis lock error in expire_polls_job: {e}")

def _run_poll_expiry():
    try:
        db._execute("SELECT fn_declare_expired_polls()")
    except Exception as e:
        logger.error(f"Error executing fn_declare_expired_polls: {e}")

    try:
        # Check for polls ending in the next 15 minutes across all societies
        # We need distinct society IDs to fetch targets correctly.
        societies = db._execute("SELECT id FROM societies", fetch_all=True)
        for row in (societies or []):
            sid = row["id"]
            soon_rows = db._execute(
                "SELECT * FROM fn_get_polls_ending_soon(%s, %s)",
                (sid, 15), fetch_all=True,
            )
            if soon_rows:
                targets = PushService.get_notification_targets(sid, roles=["apartment"])
                if targets:
                    for soon in soon_rows:
                        PushService.send_bulk_push(
                            targets, "⏰ Poll Ending Soon",
                            f"Poll '{soon['title']}' ends at {soon['ends_at']}",
                            url="/dashboard/polls", society_id=sid,
                        )
                        db._execute(
                            "UPDATE polls SET reminder_sent_at = NOW() WHERE id = %s",
                            (soon["id"],),
                        )
    except Exception as e:
        logger.error(f"Error in poll push reminders: {e}")

def init_scheduler():
    scheduler = BackgroundScheduler()
    # Run every minute
    scheduler.add_job(func=expire_polls_job, trigger="interval", seconds=60)
    scheduler.start()
    logger.info("APScheduler initialized for background jobs.")
