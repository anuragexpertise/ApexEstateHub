"""Scheme packs (schemes/*.toml): the single source of truth for rules, and the conformance checks that keep the
SQL, the Master rule editor and the code that reads each rule in step with it. Pure Python: always runs."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from schemes.loader import BEGIN_MARK, END_MARK, PackError, load_all, load_scheme, parse_pack, render_sql

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "database" / "estatehub.sql").read_text(encoding="utf-8")
GEN_A, GEN_B = SQL.index(BEGIN_MARK), SQL.index(END_MARK) + len(END_MARK)
SQL_OUTSIDE_GENERATED = SQL[:GEN_A] + SQL[GEN_B:]
UP = load_scheme("UP_AOA_2010")

_HEAD = '''[scheme]
code = "T"
state_code = "ZZ"
constitution = "AOA"
name = "t"
primary_law = "t"
effective_from = 2020-01-01
status = "active"
source_reference = "t t t t t t"
'''


def _param(**over):
    d = dict(key="k_one", label="L", instrument="I", provision="P", nature="non_statutory", base_source="model_bye_law",
             type="int", value=5, min=1, max=10, layers="[2]", tighten="lower", enforcement="gated", feeds='["fn_x"]',
             source="Some source text here")
    d.update(over)
    body = "[[parameter]]\n"
    for k, v in d.items():
        if v is None:
            continue
        body += f'{k} = {v}\n' if k in ("value", "min", "max", "layers", "feeds", "droppable", "choices", "implemented") else f'{k} = "{v}"\n'
    return _HEAD + body


def test_packs_parse_and_codes_are_unique():
    packs = load_all()
    assert {p.code for p in packs} >= {"UP_AOA_2010", "GENERIC"}
    assert len({p.code for p in packs}) == len(packs)


def test_valid_minimal_pack_parses():
    s = parse_pack(_param())
    assert s.params[0].key == "k_one" and s.params[0].base_layer == 1


@pytest.mark.parametrize("over,needle", [
    (dict(nature="statutory"), "exactly when base_source"),                       # statutory needs an Act/central source
    (dict(nature="statutory", base_source="state_act_rules", layers="[2]"), "Layer 0"),   # statutory cannot be varied
    (dict(value=99), "outside min/max"),
    (dict(value=1.5), "whole-number"),
    (dict(key="Bad-Key"), "lower_snake_case"),
    (dict(feeds=None), "feeds"),
    (dict(enforcement="policy"), "engine_default"),
    (dict(droppable="true", base_source="engine_default", enforcement="policy"), "droppable"),
    (dict(source="short"), "source"),
    (dict(verification="checked"), "verified_on"),
    (dict(type="text", value=None), "choices"),
    (dict(layers="[4]"), "1, 2, 3"),
])
def test_bad_parameters_are_rejected(over, needle):
    with pytest.raises(PackError) as e:
        parse_pack(_param(**over))
    assert needle in str(e.value)


def test_duplicate_keys_rejected():
    two = _param() + "\n" + _param().split("[[parameter]]\n", 1)[1].join(["[[parameter]]\n", ""])
    with pytest.raises(PackError, match="duplicate"):
        parse_pack(two)


# ── the pack is the single source: nothing derived from it may drift ─────────────────────────
def test_generated_sql_block_is_up_to_date():
    assert SQL[GEN_A:GEN_B] == render_sql(load_all()), "run: python scripts/build_scheme_sql.py"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_scheme_sql.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_regime_rules_admin_specs_come_from_the_pack():
    from app.services.regime_rules_admin import RULE_SPECS
    assert set(RULE_SPECS) == {p.key for p in UP.params}
    assert RULE_SPECS["arrears_disqualify_days"].hi == 365                 # sanity bound, not the society envelope
    assert RULE_SPECS["reserve_appropriation_pct"].statutory is False      # engine policy: no confirm-on-edit
    assert RULE_SPECS["transfer_fee_pct"].statutory is True


def _sql_functions():
    return set(re.findall(r"CREATE OR REPLACE FUNCTION (\w+)\(", SQL))


def test_every_feed_names_a_real_sql_function():
    fns = _sql_functions()
    for s in load_all():
        for p in s.params:
            for f in p.feeds:
                assert f in fns, f"{s.code}.{p.key} feeds {f}, which is not a function in estatehub.sql"


def test_every_implemented_rule_is_actually_read_by_the_sql():
    for p in UP.params:
        if p.implemented:
            assert re.search(rf"'{p.key}'", SQL_OUTSIDE_GENERATED), f"{p.key} is never read by any function"
    unread = [p.key for p in UP.params if not p.implemented]
    assert unread == []       # all rules are now implemented


def test_every_rule_the_sql_reads_has_a_definition():
    read = set(re.findall(r"fn_regime_param_(?:num|text)\([^,()]+,\s*'([a-z0-9_]+)'", SQL_OUTSIDE_GENERATED))
    defined = {p.key for p in UP.params}
    assert read, "pattern found nothing - the check itself is broken"
    assert read <= defined, f"read but undefined: {sorted(read - defined)}"


def test_statutory_rules_are_layer_zero_and_locked():
    st = [p for p in UP.params if p.statutory]
    assert {p.key for p in st} >= {"s22_default_months", "s22_notice_days", "s22_wait_months", "s22_appeal_days",
                                    "s20_recovery_months", "tenant_joint_liability"}
    assert all(p.layers == () and not p.droppable and p.base_layer == 0 for p in st)


def test_no_policy_default_is_presented_as_law():
    for p in UP.params:
        if p.base_source == "engine_default":
            assert p.enforcement == "policy" and p.base_layer is None and p.verification in ("provisional", "disputed")


def test_generic_scheme_carries_no_statutory_rule():
    g = load_scheme("GENERIC")
    assert g.constitution == "GENERIC" and not any(p.statutory for p in g.params)


def test_rule_keys_fit_resolution_clause_ids():
    assert all(len(p.key) <= 30 for s in load_all() for p in s.params)

