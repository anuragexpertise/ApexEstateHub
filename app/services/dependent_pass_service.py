# app/services/dependent_pass_service.py
"""
Authorized Dependent Time-based Pass: how a CHILD, or a tutor / visitor who comes for a child, gets through the gate.

Why this exists (DPDP Act 2023, s.9): a society may store a child's basic details with a parent's verifiable consent
(s.9(1)), but may not track or monitor a child's behaviour (s.9(3)). A login plus a gate_access row per scan would build
exactly that: a timestamped timeline of a child's comings and goings. So a dependent never gets a login, and a scan of
their pass is a point-in-time check that leaves nothing behind:

  * the pass belongs to a FLAT and is valid only between two dates, on chosen weekdays, inside a daily window (IST);
  * a gate scan answers PASS / FAIL and alerts the parent in real time, and writes NOTHING: no gate_access row, no scan
    list, no per-pass timestamp (the dependent_passes table has no such column, on purpose);
  * the parent alert is delivered and not stored (push_service.send_push_notification(persist=False));
  * a revoked or long-expired pass is deleted after a short grace period (purge_stale), run whenever a pass is issued.

This module holds the pure rules (check_window) and the writes (create_pass / revoke_pass / purge_stale). The QR check
itself lives in qr_service.validate_dependent_pass_qr, which calls check_window and alert_guardians.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta

from database.db_manager import db

logger = logging.getLogger(__name__)

PASS_KINDS = {"child": "Child", "tutor": "Tutor / child's visitor"}

# Python weekday(): Monday = 0 ... Sunday = 6
WEEKDAY_SETS = {
    "all": frozenset(range(7)),
    "mon_fri": frozenset(range(5)),
    "mon_sat": frozenset(range(6)),
    "sat_sun": frozenset({5, 6}),
}
WEEKDAY_LABELS = {"all": "Every day", "mon_fri": "Mon-Fri", "mon_sat": "Mon-Sat", "sat_sun": "Sat-Sun"}
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# A pass is for a school term or a tuition course, not for life; this keeps one from quietly becoming permanent.
MAX_VALIDITY_DAYS = 366
# Revoked / expired passes stay this long (so the parent still sees them in the list), then are deleted.
GRACE_DAYS = 7


# ── pure rules ───────────────────────────────────────────────────────────────────────────────────────────────────
def _hhmm(t) -> str:
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)[:5]


def window_label(p: dict) -> str:
    return f"{_hhmm(p['window_from'])} - {_hhmm(p['window_to'])}"


def check_window(p: dict, now: datetime) -> tuple[bool, str]:
    """Is this pass usable at `now` (IST)? Returns (allowed, reason). `p` needs status, valid_from, valid_until,
    weekdays, window_from, window_to. The reason is shown to the guard, so it says what is wrong and nothing more."""
    if p["status"] != "active":
        return False, "This pass has been revoked"
    today = now.date()
    if today < p["valid_from"]:
        return False, f"Not valid until {p['valid_from']:%d-%b-%Y}"
    if today > p["valid_until"]:
        return False, "This pass has expired"
    if now.weekday() not in WEEKDAY_SETS.get(p["weekdays"], WEEKDAY_SETS["all"]):
        return False, f"Not valid on {_DAY_NAMES[now.weekday()]} (valid {WEEKDAY_LABELS.get(p['weekdays'], '')})"
    t = now.time().replace(microsecond=0, tzinfo=None)
    if not (p["window_from"] <= t <= p["window_to"]):
        return False, f"Outside the permitted time ({window_label(p)})"
    return True, "Within the permitted time"


def _parse_date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return None


def _parse_time(v) -> time | None:
    if isinstance(v, time):
        return v.replace(microsecond=0, tzinfo=None)
    try:
        parts = [int(x) for x in str(v).strip().split(":")]
        return time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
    except (TypeError, ValueError, IndexError):
        return None


# ── writes ───────────────────────────────────────────────────────────────────────────────────────────────────────
def create_pass(society_id: int, apartment_id: int, pass_kind: str, label: str, valid_from, valid_until,
                window_from, window_to, weekdays: str, actor_user_id: int | None,
                guardian_consent: bool = False) -> tuple[bool, str, int | None]:
    """Issue a pass for a flat. The caller has already decided the actor may do this for this flat.

    A child's pass needs the parent / lawful guardian's consent (DPDP s.9(1)); it is recorded in the same transaction
    as the pass, so no child's pass exists without its consent record."""
    from app.services import qr_service
    from app.utils import now_ist

    pass_kind = str(pass_kind or "").strip().lower()
    if pass_kind not in PASS_KINDS:
        return False, "Choose who the pass is for: a child, or a tutor / child's visitor", None
    label = " ".join(str(label or "").split())
    if not label:
        return False, "Enter a first name or nickname for the guard to match (not a full name or an ID number)", None
    if len(label) > 100:
        return False, "Keep the name or nickname under 100 characters", None
    weekdays = str(weekdays or "all").strip().lower()
    if weekdays not in WEEKDAY_SETS:
        return False, "Choose the days the pass is valid", None
    d_from, d_to = _parse_date(valid_from), _parse_date(valid_until)
    if not d_from or not d_to:
        return False, "Enter the first and last day the pass is valid", None
    if d_to < d_from:
        return False, "The last valid day cannot be before the first", None
    if d_to < now_ist().date():
        return False, "The last valid day is already past", None
    if (d_to - d_from).days + 1 > MAX_VALIDITY_DAYS:
        return False, f"A pass can be valid for at most {MAX_VALIDITY_DAYS} days; issue a new one when it ends", None
    t_from, t_to = _parse_time(window_from), _parse_time(window_to)
    if not t_from or not t_to:
        return False, "Enter the daily time window (from and to)", None
    if t_to <= t_from:
        return False, "The daily window must end after it starts, on the same day", None
    if pass_kind == "child" and not guardian_consent:
        return False, ("A parent or lawful guardian must consent before a child's pass is issued. "
                       "Choose 'Yes' under Parent/guardian consent."), None
    if not db._execute("SELECT 1 AS x FROM apartments WHERE id=%s AND society_id=%s AND active",
                       (apartment_id, society_id), fetch_one=True):
        return False, "That flat is not in this society", None
    # The pass's QR is only trustworthy when signed (a typed "<society>-DEP-<n>" must never work), so refuse to
    # issue one until this society has its signing key.
    if not qr_service._get_signing_secret(society_id):
        return False, "This society's QR signing key is not set up yet; complete the Setup Wizard first", None

    purge_stale(society_id)
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO dependent_passes (society_id, apartment_id, pass_kind, label, valid_from, valid_until, "
                "window_from, window_to, weekdays, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (society_id, apartment_id, pass_kind, label, d_from, d_to, t_from, t_to, weekdays, actor_user_id))
            pid = cur.fetchone()["id"]
            if pass_kind == "child":
                from app.services import dpdp_service as dpdp
                notice = dpdp.ensure_notice(society_id, actor_user_id)
                cur.execute(
                    "INSERT INTO consent_records (society_id, person_key, person_role, purpose, notice_version, "
                    "lawful_basis, created_by) VALUES (%s, %s, 'family', 'guardian_consent', %s, 'consent', %s)",
                    (society_id, f"dependent_pass:{pid}", notice["version"], actor_user_id))
    except Exception as e:  # noqa: BLE001
        logger.error("create_pass failed: %s", e)
        return False, f"Could not issue the pass: {str(e).splitlines()[0][:160]}", None
    flat = (db._execute("SELECT flat_number FROM apartments WHERE id=%s", (apartment_id,), fetch_one=True) or {}
            ).get("flat_number", "")
    return True, f"Pass issued for Flat {flat}: {label}", pid


def revoke_pass(pass_id: int, society_id: int, apartment_id: int | None = None) -> tuple[bool, str]:
    """Revoke at once (the QR stops working immediately). `apartment_id` restricts a resident to their own flat; an
    admin passes None. The row is deleted after GRACE_DAYS by purge_stale."""
    sql = ("UPDATE dependent_passes SET status='revoked', revoked_at=NOW() "
           "WHERE id=%s AND society_id=%s AND status='active'")
    params: list = [pass_id, society_id]
    if apartment_id is not None:
        sql += " AND apartment_id=%s"
        params.append(apartment_id)
    done = db._execute(sql + " RETURNING id", params, fetch_one=True)
    if not done:
        return False, "That pass was not found, or it is already revoked"
    db._execute("UPDATE consent_records SET withdrawn_at = COALESCE(withdrawn_at, NOW()) "
                "WHERE society_id=%s AND person_key=%s AND purpose='guardian_consent'",
                (society_id, f"dependent_pass:{pass_id}"))
    return True, "Pass revoked. Its QR no longer works."


def purge_stale(society_id: int | None = None, grace_days: int = GRACE_DAYS) -> int:
    """Delete passes revoked, or expired, more than `grace_days` ago, so no standing record of who a family let in
    survives its purpose. The consent record is kept (it is the proof consent was given)."""
    from app.utils import now_ist
    cutoff = now_ist().date() - timedelta(days=grace_days)
    scope, params = ("AND society_id=%s", [society_id]) if society_id else ("", [])
    rows = db._execute(
        "DELETE FROM dependent_passes WHERE (valid_until < %s OR (status='revoked' AND revoked_at < NOW() - %s::interval)) "
        + scope + " RETURNING id", [cutoff, f"{int(grace_days)} days"] + params, fetch_all=True) or []
    return len(rows)


# ── the parent alert ─────────────────────────────────────────────────────────────────────────────────────────────
def guardian_user_ids(society_id: int, apartment_id: int, created_by: int | None) -> list[int]:
    """Who is told: the flat's owner login(s) and whoever issued the pass (if they still have a login on this flat)."""
    ids = [r["id"] for r in (db._execute(
        "SELECT id FROM users WHERE society_id=%s AND linked_id=%s AND role='apartment' AND user_type='owner' "
        "AND active IS NOT FALSE", (society_id, apartment_id), fetch_all=True) or [])]
    if created_by and created_by not in ids and db._execute(
            "SELECT 1 AS x FROM users WHERE id=%s AND society_id=%s AND linked_id=%s AND role='apartment' "
            "AND active IS NOT FALSE", (created_by, society_id, apartment_id), fetch_one=True):
        ids.append(created_by)
    return ids


def alert_guardians(p: dict, mode: str, allowed: bool, reason: str = "", background: bool = True) -> list[int]:
    """Tell the parent a dependent's pass was used (or refused) at the gate. Real-time and NOT stored: the push goes
    out with persist=False, so no in-app notification row, and nothing here is kept after it is sent.
    Returns the user ids alerted. A failure to alert never changes the gate's answer."""
    try:
        targets = guardian_user_ids(p["society_id"], p["apartment_id"], p.get("created_by"))
    except Exception as e:  # noqa: BLE001
        logger.error("dependent pass alert lookup failed: %s", e)
        return []
    if not targets:
        return []
    flat, label = p.get("flat_number") or "", p.get("label") or "Dependent"
    if allowed:
        title = "Dependent pass used at the gate"
        body = f"{label} {'entered' if mode != 'exit' else 'left'} (Flat {flat}). Nothing is recorded."
    else:
        title = "Dependent pass refused at the gate"
        body = f"{label}'s pass was refused (Flat {flat}): {reason}."

    def _send():
        from app.services.push_service import send_push_notification
        for uid in targets:
            try:
                send_push_notification(uid, title, body, society_id=p["society_id"], persist=False)
            except Exception as e:  # noqa: BLE001
                logger.error("dependent pass alert failed for user %s: %s", uid, e)

    if background:
        threading.Thread(target=_send, daemon=True, name="dependent-pass-alert").start()
    else:
        _send()
    return targets
