"""Plan v4, C.7 -- the NOC list and the Security Salaries (security) list: one column each, none duplicated, and every column
is one the list loader fills. Runs on the entity metadata and, when a live seeded database is configured, on real rows."""
import os

import pytest

from app.dash_apps.drilldown import schema_introspect as si


@pytest.fixture(scope="module")
def meta():
    return si.get_entity_meta()


@pytest.mark.parametrize("entity", ["nocs", "security"])
def test_no_column_appears_twice(meta, entity):
    cols = meta[entity]["list_columns"]
    fields = [c["field"] for c in cols]
    names = [c["name"] for c in cols]
    assert len(fields) == len(set(fields)), fields
    assert len(names) == len(set(names)), names


def test_noc_list_has_only_columns_the_loader_returns(meta):
    fields = [c["field"] for c in meta["nocs"]["list_columns"]]
    assert fields == ["apartment_id", "certificate_no", "status", "issued_date", "valid_until"]
    assert meta["nocs"]["list_columns"][0]["alias"] == "flat_number"
    assert {"revoked_at", "revoked_by"} <= {f["field"] for f in meta["nocs"]["profile_fields"]}   # still on the profile


def test_security_list_drops_the_blank_penalty_and_renames_the_month_count(meta):
    cols = {c["field"]: c["name"] for c in meta["security"]["list_columns"]}
    assert "ptl_penalty" not in cols
    assert cols["shift_count"] == "Shifts till date" and cols["shifts_this_month"] == "Shifts This Month"
    assert cols["salary_due"] == "Salary Due" and cols["salary_paid"] == "Salary Paid"


@pytest.mark.skipif(os.getenv("ESTATEHUB_LIVE_TESTS") != "1", reason="needs the seeded Postgres")
@pytest.mark.parametrize("entity", ["nocs", "security"])
def test_every_listed_column_is_in_the_loaded_rows(meta, entity):
    from app.dash_apps.drilldown import loaders
    rows, _ = loaders.load_list(entity, {"society_id": 1})
    if not rows:
        pytest.skip("no rows seeded for this list")
    keys = set(rows[0])
    for c in meta[entity]["list_columns"]:
        assert (c.get("alias") or c["field"]) in keys or c["field"] in keys, c
