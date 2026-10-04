# app/security/roles.py
"""
The one place the role vocabulary is defined.

Three different vocabularies were in play:

  persisted   users.role CHECK constraint: admin / apartment / vendor / security
  virtual     "master" — NEVER stored in users.role. Computed as
              (role='admin' AND society_id IS NULL AND is_master_admin) and then
              handed to the session / JWT / portal router.
  legacy      "master_admin" — appears only as the *flag* users.is_master_admin,
              but the architecture notes (and some older code/docs) also use it as
              if it were a role name.

This module fixes the contract: persisted roles, the single derivation of the
virtual master role, and a normaliser that maps the legacy spelling onto it, so
the persisted role, the session identity and portal routing cannot disagree.

NOTE: these are the *legacy coarse roles* that gate portals. Fine-grained,
society-scoped authorization lives in app/security/policy.py (RBAC tables).
"""
from __future__ import annotations

# users.role CHECK constraint (database/estatehub.sql)
PERSISTED_ROLES: tuple[str, ...] = ("admin", "apartment", "vendor", "security")

# Virtual platform role, derived — never persisted.
MASTER_ROLE = "master"

# Everything the session / token / router may carry.
SESSION_ROLES: tuple[str, ...] = PERSISTED_ROLES + (MASTER_ROLE,)

# Spellings of the platform role seen in older code/docs → canonical session role.
# Deliberately tiny: anything else (e.g. user_type 'owner') is unknown → denied.
_ALIASES = {
    "master_admin": MASTER_ROLE,
    "masteradmin": MASTER_ROLE,
}

# Landing page per session role. Single source for the login redirect and the
# JWT refresh redirect (previously copy-pasted in login_callbacks.py + routes/auth.py).
PORTAL_HOME: dict[str, str] = {
    MASTER_ROLE: "/dashboard/master-societies",
    "admin": "/dashboard/admin-portal",
    "apartment": "/dashboard/owner-portal",
    "vendor": "/dashboard/vendor-portal",
    "security": "/dashboard/pass-evaluation",
}
DEFAULT_PORTAL = "/dashboard/"


def resolve_role(raw_role: str | None, society_id, is_master_admin_flag) -> str | None:
    """
    Map a users row to the role the rest of the app checks.

    The ONLY place the master derivation lives:
        admin + no society + is_master_admin  ->  "master"
    A society-less admin WITHOUT the flag stays a plain "admin" (it must not be
    promoted by being society-less alone), and a flagged user who belongs to a
    society is a society admin, not a platform operator.
    """
    if raw_role == "admin" and not society_id and bool(is_master_admin_flag):
        return MASTER_ROLE
    return raw_role


def normalize_role(value: str | None) -> str | None:
    """
    Canonicalise a role string for comparison. Returns None for anything that is
    not a known role/alias (so unknown values are denied, not guessed at).
    """
    if not value:
        return None
    v = str(value).strip().lower()
    v = _ALIASES.get(v, v)
    return v if v in SESSION_ROLES else None


def portal_home(role: str | None) -> str:
    """Landing path for a session role; unknown roles get the neutral default."""
    return PORTAL_HOME.get(normalize_role(role) or "", DEFAULT_PORTAL)
