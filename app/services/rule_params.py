"""Parameter-level layers: a society's decisions on the values the engine reads.

The clause-level register (society_bye_laws) says a clause is adopted / varied / not adopted. This module records
the actual VALUE a society has decided for a rule defined in rule_parameter_defs (generated from the scheme pack),
at Layer 1 (Model Bye-Law adoption), 2 (Society policy, General Body) or 3 (Board decision). fn_rule() in SQL applies
them, so every function that reads a rule through fn_regime_param_num/text sees the society's adopted value.

Who does what (the same split as the clause-level register):
  * the society ADMIN records a decision, with the meeting minutes attached; with no passed resolution it is saved
    PROVISIONAL and the engine ignores it;
  * a passed, quorate, correctly-typed resolution naming the rule (resolutions.clause_id = rule_key) activates it;
  * MASTER spot-checks active decisions and can flag one (the engine then ignores it until it is cleared).
"""
from __future__ import annotations

import json
from datetime import date

from app.services import regime_rules_admin as rra

DECISION_CHOICES = ("adopted_as_is", "adopted_with_variation", "not_adopted")
# Which Layer-1 decision type can confirm which choice (Layer 2 / 3 have a single decision type each).
_LAYER1_DECISION_CHOICES = rra._LAYER1_DECISION_CHOICES


def _json_safe(d: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else (float(v) if hasattr(v, "as_tuple") else v))
            for k, v in d.items()}


def _def(society_id: int, rule_key: str) -> dict | None:
    return rra._row("""SELECT d.* FROM society_legal_regime slr
                         JOIN rule_parameter_defs d ON d.regime_code = slr.regime_code AND d.rule_key = %s
                        WHERE slr.society_id = %s""", (rule_key, society_id))


def _parse_value(d: dict, raw) -> tuple[float | None, str | None, str | None]:
    """-> (number, text, error) for a variation's raw input, typed by the rule's definition."""
    if d["value_type"] == "text":
        v = str(raw).strip().lower() if raw is not None else ""
        return None, v, None
    try:
        num = float(str(raw).strip())
    except (TypeError, ValueError):
        return None, None, f"{d['rule_key']} must be a number."
    if num != num or num in (float("inf"), float("-inf")):
        return None, None, f"{d['rule_key']} must be a finite number."
    return num, None, None


def _below(society_id: int, rule_key: str, layer: int, on: date) -> dict:
    """The value in force beneath `layer` (what a Layer 2/3 decision may only tighten)."""
    return rra._row("SELECT value, value_text FROM fn_rule(%s, %s, %s, %s)", (society_id, rule_key, on, layer)) or {}


def _check(society_id, rule_key, layer, choice, num, text, on) -> str | None:
    cur = _below(society_id, rule_key, layer, on)
    row = rra._row("SELECT fn_rule_decision_check(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS err",
                   (society_id, rule_key, layer, choice, num, text, cur.get("value"), cur.get("value_text"), on))
    return (row or {}).get("err")


def _resolution_ok(society_id: int, rule_key: str, layer: int, choice: str, resolution_id: int) -> str | None:
    """A resolution can back a decision only if it passed the clause-level tests (this society's, passed, naming this
    rule, right type for the layer, quorate, right body), fits the choice at Layer 1, and the meeting has minutes."""
    res, err = rra._check_resolution(society_id, rule_key, layer, resolution_id)
    if err:
        return err
    if layer == 1 and choice not in _LAYER1_DECISION_CHOICES.get(res["dt_code"], ()):
        return f"A {res['dt_code']} resolution cannot back '{choice.replace('_', ' ')}'."
    m = rra._row("""SELECT m.minutes_pdf FROM resolutions r JOIN meetings m ON m.id = r.meeting_id WHERE r.id = %s""",
                 (resolution_id,))
    if not (m and (m.get("minutes_pdf") or "").strip()):
        return "Attach the meeting minutes to the meeting before it can back a decision."
    if rra._row("""SELECT 1 AS x FROM society_rule_decisions WHERE resolution_id = %s
                   UNION ALL SELECT 1 FROM society_bye_laws WHERE resolution_id = %s LIMIT 1""",
                (resolution_id, resolution_id)):
        return "That resolution already backs another decision; record a new resolution."
    return None


# ── reads ─────────────────────────────────────────────────────────────────────
def effective_rules_for_society(society_id: int, on: date | None = None) -> list[dict]:
    """Every rule of the society's scheme with its effective value, the layer that supplied it and its status."""
    return rra._rows("""
        SELECT d.rule_key, d.label, d.instrument, d.provision, d.clause_id, d.nature, d.base_source, d.value_type,
               d.unit, d.layers, d.tighten, d.droppable, d.enforcement, d.feeds, d.verification, d.needs_decision,
               d.implemented, d.choices, d.vary_min, d.vary_max,
               r.value, r.value_text, r.layer, r.status, r.source, r.decision_id, r.ignored,
               (SELECT COUNT(*) FROM society_rule_decisions p
                 WHERE p.society_id = slr.society_id AND p.rule_key = d.rule_key AND p.status = 'provisional') AS provisional
          FROM society_legal_regime slr
          JOIN rule_parameter_defs d ON d.regime_code = slr.regime_code
          LEFT JOIN LATERAL fn_rule(slr.society_id, d.rule_key, %s) r ON TRUE
         WHERE slr.society_id = %s
         ORDER BY d.instrument, d.rule_key""", (on or date.today(), society_id))


def list_decisions(society_id: int, rule_key: str | None = None) -> list[dict]:
    return rra._rows("""SELECT * FROM society_rule_decisions WHERE society_id = %s AND (%s::text IS NULL OR rule_key = %s)
                         ORDER BY rule_key, layer, effective_from DESC""", (society_id, rule_key, rule_key))


# ── writes ────────────────────────────────────────────────────────────────────
def save_decision(actor_id, actor_role, society_id: int, rule_key: str, layer: int, choice: str, value,
                  effective_from, reason: str, resolution_id: int | None = None, actor_society_id=None) -> tuple[bool, str]:
    """Record a society's decision on a rule. Admin of that society only. With no resolution it is stored
    provisional (and the engine ignores it); with a valid passed resolution it is stored active."""
    rra._require_writer(actor_role, actor_society_id, society_id, master_ok=False)
    d = _def(society_id, rule_key)
    if not d:
        return False, f"{rule_key} is not a configurable rule in this society's legal scheme."
    if choice not in DECISION_CHOICES:
        return False, f"Choice must be one of {DECISION_CHOICES}."
    num = text = None
    if choice == "adopted_with_variation":
        num, text, perr = _parse_value(d, value)
        if perr:
            return False, perr
    elif value not in (None, ""):
        return False, "A value can only be given when the rule is adopted with a variation."
    start = rra._d(effective_from)
    if not start:
        return False, "Choose the date the decision takes effect."
    if start < date.today():
        return False, "A decision cannot be back-dated."
    why = rra._text(reason, rra.MIN_TEXT)
    if not why:
        return False, f"Say why the rule is changing (at least {rra.MIN_TEXT} characters)."
    err = _check(society_id, rule_key, int(layer), choice, num, text, start)
    if err:
        return False, err
    if resolution_id:
        rerr = _resolution_ok(society_id, rule_key, int(layer), choice, int(resolution_id))
        if rerr:
            return False, rerr
        status, proposed = choice, None
    else:
        status, proposed = "provisional", choice

    latest = rra._row("""SELECT status, proposed_status, value, value_text, effective_from FROM society_rule_decisions
                          WHERE society_id = %s AND rule_key = %s AND layer = %s ORDER BY effective_from DESC LIMIT 1""",
                      (society_id, rule_key, layer))
    if latest and start <= latest["effective_from"]:
        return False, f"The new decision must start after the latest existing one ({latest['effective_from']:%d %b %Y})."
    if latest and (latest["status"], latest["proposed_status"],
                   float(latest["value"]) if latest["value"] is not None else None, latest["value_text"]) == (status, proposed, num, text):
        return False, "That is already the decision in force; nothing to change."

    row = rra._row(
        """WITH closed AS (
               UPDATE society_rule_decisions SET effective_to = CAST(%(start)s AS date) - 1
                WHERE society_id = %(s)s AND rule_key = %(k)s AND layer = %(l)s
                  AND effective_from < %(start)s AND (effective_to IS NULL OR effective_to >= %(start)s)
               RETURNING effective_from
           ), ins AS (
               INSERT INTO society_rule_decisions (society_id, rule_key, layer, status, proposed_status, value, value_text,
                                                   resolution_id, effective_from, created_by)
               VALUES (%(s)s, %(k)s, %(l)s, %(st)s, %(pr)s, %(num)s, %(txt)s, %(res)s, %(start)s, %(uid)s)
               RETURNING id, society_id, rule_key, layer, status, proposed_status, value, value_text, resolution_id, effective_from
           )
           INSERT INTO regime_rule_audit (target_table, society_id, rule_key, action, old_value, new_value, reason,
                                          changed_by, changed_by_role)
           SELECT 'society_rule_decisions', ins.society_id, ins.rule_key, 'new_version',
                  (SELECT to_jsonb(closed) FROM closed), to_jsonb(ins), %(why)s, %(uid)s, %(role)s FROM ins RETURNING id""",
        {"s": society_id, "k": rule_key, "l": int(layer), "st": status, "pr": proposed, "num": num, "txt": text,
         "res": resolution_id, "start": start, "why": why, "uid": actor_id, "role": actor_role})
    if not row:
        return False, "Nothing was saved."
    state = "provisional until a passed resolution backs it" if status == "provisional" else "active"
    return True, f"{rule_key} (layer {layer}) saved from {start:%d %b %Y} - {state}."


def _latest_provisional(society_id: int, rule_key: str, layer: int) -> dict | None:
    return rra._row("""SELECT * FROM society_rule_decisions WHERE society_id = %s AND rule_key = %s AND layer = %s
                          AND status = 'provisional' ORDER BY effective_from DESC LIMIT 1""", (society_id, rule_key, layer))


def auto_activate(actor_id, actor_role, society_id: int, resolution_id: int, rule_key: str) -> list[str]:
    """After a PASSED resolution naming `rule_key` is recorded, activate the society's provisional decision(s) on that
    rule that the resolution can validly back. Re-checks the decision against the value beneath it as of today, so a
    decision that was fine when drafted but no longer tightens anything stays provisional."""
    if not _def(society_id, rule_key):
        return []
    notes: list[str] = []
    for layer in (1, 2, 3):
        prov = _latest_provisional(society_id, rule_key, layer)
        if not prov:
            continue
        want = prov["proposed_status"]
        rerr = _resolution_ok(society_id, rule_key, layer, want, resolution_id)
        if rerr:
            continue                                  # not the right resolution for this layer
        start = max(rra._d(prov["effective_from"]) or date.today(), date.today())
        num = float(prov["value"]) if prov["value"] is not None else None
        err = _check(society_id, rule_key, layer, want, num, prov["value_text"], start)
        if err:
            notes.append(f"{rule_key} (layer {layer}) stays provisional: {err}")
            continue
        row = rra._row("""UPDATE society_rule_decisions SET status = proposed_status, proposed_status = NULL,
                                 resolution_id = %s, updated_at = NOW() WHERE id = %s RETURNING *""", (resolution_id, prov["id"]))
        if not row:
            continue
        rra.db._execute("""INSERT INTO regime_rule_audit (target_table, society_id, rule_key, action, old_value, new_value,
                                                         reason, changed_by, changed_by_role)
                           VALUES ('society_rule_decisions', %s, %s, 'confirm_provisional', %s::jsonb, %s::jsonb, %s, %s, %s)""",
                        (society_id, rule_key, json.dumps(_json_safe(dict(prov))), json.dumps(_json_safe(dict(row))),
                         f"Activated automatically by passed resolution #{resolution_id}", actor_id, actor_role))
        notes.append(f"{rule_key} (layer {layer}) is now active as {want.replace('_', ' ')} via resolution #{resolution_id}.")
    return notes


def review_decision(actor_id, actor_role, decision_id: int, outcome: str, note: str) -> tuple[bool, str]:
    """Master spot-check of a society's decision. 'flagged' suspends it (fn_rule ignores it) until set back to
    'confirmed'. The note is required and goes to the audit log."""
    if actor_role != "master":
        raise PermissionError("Master role required.")
    if outcome not in ("confirmed", "flagged"):
        return False, "Outcome must be 'confirmed' or 'flagged'."
    why = rra._text(note, rra.MIN_TEXT)
    if not why:
        return False, f"Say what you checked (at least {rra.MIN_TEXT} characters)."
    old = rra._row("SELECT * FROM society_rule_decisions WHERE id = %s", (decision_id,))
    if not old:
        return False, "Decision not found."
    if old["status"] == "provisional":
        return False, "A provisional decision has no resolution to review yet."
    new = rra._row("""UPDATE society_rule_decisions SET review_status = %s, reviewed_by = %s, reviewed_on = NOW(),
                             review_note = %s, updated_at = NOW() WHERE id = %s RETURNING *""", (outcome, actor_id, why, decision_id))
    rra.db._execute("""INSERT INTO regime_rule_audit (target_table, society_id, rule_key, action, old_value, new_value,
                                                     reason, changed_by, changed_by_role)
                       VALUES ('society_rule_decisions', %s, %s, 'update', %s::jsonb, %s::jsonb, %s, %s, %s)""",
                    (old["society_id"], old["rule_key"], json.dumps(_json_safe(dict(old))), json.dumps(_json_safe(dict(new))),
                     why, actor_id, actor_role))
    return True, ("Decision confirmed." if outcome == "confirmed"
                  else "Decision flagged: the engine ignores it until it is confirmed again.")
