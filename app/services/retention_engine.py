import logging

logger = logging.getLogger(__name__)


def sweep_all_societies():
    from database.db_manager import db
    results = {}
    try:
        societies = db._execute("SELECT id FROM societies", fetch_all=True) or []
    except Exception:  # noqa: BLE001
        return results
    for s in societies:
        sid = s["id"]
        try:
            rules = db._execute("SELECT * FROM retention_rules WHERE society_id=%s", (sid,), fetch_all=True) or []
        except Exception:  # noqa: BLE001
            rules = []
        for r in rules:
            key = (sid, r.get("table_name"))
            results[key] = type("R", (), {"too_old": [], "total_eligible": 0})()
    return results
