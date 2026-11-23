# Dependency Remediation (H2-01)

## Problem

CI `pip-audit --strict` ignores 11 known-vulnerable advisories (PYSEC-*) for
the Flask 2.2 / Werkzeug 2.2 / Dash 2.14 stack pinned in `requirements.txt`.
Reachability of these advisories in ApexEstateHub's code paths is not
assessed.

## Required fix

1. Run `pip-audit -r requirements.txt` (without --ignore-vuln) to get the
   full list of advisories.
2. For each ignored CVE, determine if it is reachable in ApexEstateHub's
   request-handling code paths (Flask request parsing, Werkzeug debugging,
   Dash frontend, etc.).
3. Upgrade reachable vulnerable packages. Flask 2.2 → 2.3+/3.x, Werkzeug
   2.2 → 2.3+/3.x, Dash 2.14 → latest.
4. Document any accepted (unreachable) risk in this file, per the CI
   comment's convention ("Remove an id from this list when its package is
   upgraded, never add one without a note in docs/").

## Related

- B1-04: same old pins in requirements.txt.
