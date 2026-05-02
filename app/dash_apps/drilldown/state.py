# app/dash_apps/drilldown/state.py
"""
Navigation State Manager
=========================
Manages the drill-down navigation stack stored in dcc.Store.

Store schema (id="drilldown-store"):
{
  "stack": [
    {
      "card_id":    "list_apartments",
      "label":      "Apartments",
      "filters":    {"society_id": 1, "has_dues": true},
      "prefill":    {},
      "entity_pk":  null,
      "entity_label": null
    }
  ],
  "active_card": "list_apartments",
  "prefill":     {},
  "filters":     {"society_id": 1}
}
"""

from __future__ import annotations
from copy import deepcopy


def initial_state(role: str = "admin", society_id: int | None = None) -> dict:
    """Return a fresh navigation state for a freshly-authenticated user."""
    home_card = _home_card_for_role(role)
    return {
        "stack":       [{"card_id": home_card, "label": "Dashboard", "filters": {}, "prefill": {}, "entity_pk": None, "entity_label": None}],
        "active_card": home_card,
        "prefill":     {},
        "filters":     {"society_id": society_id},
        "csv_entity":  None,
    }


def navigate_to(state: dict, card_id: str, label: str,
                filters: dict | None = None, prefill: dict | None = None,
                entity_pk=None, entity_label: str | None = None) -> dict:
    """
    Push a new card onto the navigation stack.
    If the card is already in the stack, pop back to that level (like browser back).
    """
    state = deepcopy(state)

    # Check if we're navigating to a card already in the stack (go back)
    for i, entry in enumerate(state["stack"]):
        if entry["card_id"] == card_id:
            state["stack"] = state["stack"][: i + 1]
            state["active_card"] = card_id
            state["prefill"] = prefill or {}
            state["filters"] = {**state.get("filters", {}), **(filters or {})}
            return state

    # Push new entry
    merged_filters = {**state.get("filters", {}), **(filters or {})}
    state["stack"].append({
        "card_id":      card_id,
        "label":        label,
        "filters":      merged_filters,
        "prefill":      prefill or {},
        "entity_pk":    entity_pk,
        "entity_label": entity_label,
    })
    state["active_card"] = card_id
    state["prefill"]     = prefill or {}
    state["filters"]     = merged_filters
    return state


def navigate_back(state: dict, to_index: int) -> dict:
    """Pop the navigation stack back to a specific breadcrumb index."""
    state = deepcopy(state)
    if to_index < len(state["stack"]):
        state["stack"] = state["stack"][: to_index + 1]
        entry = state["stack"][-1]
        state["active_card"] = entry["card_id"]
        state["filters"]     = entry.get("filters", state.get("filters", {}))
        state["prefill"]     = entry.get("prefill", {})
    return state


def get_filters(state: dict) -> dict:
    """Get current filter context (merged from stack top)."""
    if not state or not state.get("stack"):
        return {}
    return state["stack"][-1].get("filters", state.get("filters", {}))


def get_prefill(state: dict) -> dict:
    """Get current pre-fill context."""
    return state.get("prefill", {})


def _home_card_for_role(role: str) -> str:
    return {
        "master":    "dashboard_master",
        "admin":     "dashboard_admin",
        "apartment": "dashboard_apartment",
        "vendor":    "dashboard_vendor",
        "security":  "dashboard_security",
    }.get(role, "dashboard_admin")
