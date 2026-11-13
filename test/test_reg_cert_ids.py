"""The master New Society form's registration-certificate widgets, and the callbacks that wire them,
must use the same pattern-matching id keys. Dash matches a wildcard id only when the key sets are
identical: when the upload had a `field` key and the callback's pattern did not, nothing fired, so no
"uploaded, SHA-256" feedback appeared and the certificate never reached the Create Society handler."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "app/dash_apps/drilldown/renderers.py", ROOT / "app/dash_apps/callbacks/drilldown_callbacks.py"]
ID = re.compile(r'\{\s*"type":\s*"(reg-cert-(?:upload|preview|store))"([^{}]*)\}')


def _key_sets():
    found = {}
    for f in FILES:
        for m in ID.finditer(f.read_text(encoding="utf-8")):
            keys = {"type"} | set(re.findall(r'"(\w+)":', m.group(2)))
            found.setdefault(m.group(1), []).append((f.name, frozenset(keys)))
    return found


def test_every_registration_certificate_id_has_entity_and_field():
    found = _key_sets()
    assert set(found) == {"reg-cert-upload", "reg-cert-preview", "reg-cert-store"}
    for kind, uses in found.items():
        for fname, keys in uses:
            assert keys == {"type", "entity", "field"}, (kind, fname, sorted(keys))


def test_submit_handler_reads_the_store_with_the_same_keys():
    src = FILES[1].read_text(encoding="utf-8")
    assert 'State({"type": "reg-cert-store", "entity": ALL, "field": ALL}, "data")' in src
