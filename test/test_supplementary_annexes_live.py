"""Supplementary annexures F, G, H: roster hashing, the F->G->H chain, office-bearer-only signing (live Postgres)."""
import hashlib
import json
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("ESTATEHUB_LIVE_TESTS") != "1", reason="live DB tests are opt-in")


@pytest.fixture()
def soc():
    from datetime import date, timedelta
    from app.services import onboarding_service as ob, society_service as ss
    import uuid
    pid = uuid.uuid4().hex[:8]
    sid = ss.create_society_checked({"name": f"Supp {pid}", "address": "x", "pan": "ABCDE1234K", "reg_num": "R9", "reg_cert_hash": "d" * 64,
                                     "state": "UP", "constitution": "AOA", "validity": str(date.today() + timedelta(days=30)), "created_by": 1})
    db = ob.db
    db._execute("UPDATE societies SET onboarding_state='active' WHERE id=%s", (sid,))
    db._execute("INSERT INTO society_agreements (society_id, body_text) VALUES (%s,'agreement text')", (sid,))
    db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, active) VALUES (%s,'A-1','Private Name',TRUE),(%s,'A-2','Other',TRUE)", (sid, sid))
    db = ob.db
    yield ob, db, sid                       # audit_events is append-only, so the society is left in the test database


def test_roster_hash_counts_flats_and_never_uses_names(soc):
    ob, db, sid = soc
    n, sha = ob._roster_hash(sid, "apartment")
    assert n == 2 and sha == hashlib.sha256(ob.canonical(["A-1", "A-2"]).encode()).hexdigest()
    assert ob._roster_hash(sid, "vendor") == (0, None)
    for role in ("security", "supervisor", "staff"):
        ob._roster_hash(sid, role)                    # every role's SQL must run


def test_annex_f_holds_no_personal_data(soc):
    ob, db, sid = soc
    ob.build_supplementary_annex(sid, "F", 1)
    row = db._execute("SELECT content FROM onboarding_supplementary_annexes WHERE society_id=%s AND annex_code='F'", (sid,), fetch_one=True)
    assert "Private Name" not in json.dumps(row["content"])


def test_chain_cannot_fork_and_rebuild_replaces_draft(soc):
    ob, db, sid = soc
    ob.build_supplementary_annex(sid, "F", 1)
    ob.build_supplementary_annex(sid, "F", 1)                       # rebuild: still one draft
    assert db._execute("SELECT COUNT(*) AS n FROM onboarding_supplementary_annexes WHERE society_id=%s AND annex_code='F'", (sid,), fetch_one=True)["n"] == 1
    with pytest.raises(ob.OnboardingError, match="must be signed and sealed"):
        ob.build_supplementary_annex(sid, "G", 1)


def test_seal_needs_signatures_and_operator_is_not_a_signer(soc):
    ob, db, sid = soc
    from app.services import document_signing as ds
    ob.build_supplementary_annex(sid, "F", 1)
    with pytest.raises(ob.OnboardingError, match="signed by the President, Secretary and Treasurer"):
        ob.seal_supplementary_annex(sid, "F", 1)
    pol = ds.DEFAULT_POLICY["supplementary_annex"]
    assert "platform" not in pol["eligible"] and pol["min"] == 3


def test_signing_kind_is_accepted_by_the_schema(soc):
    ob, db, sid = soc
    ob.build_supplementary_annex(sid, "F", 1)
    rid = db._execute("SELECT id FROM onboarding_supplementary_annexes WHERE society_id=%s AND annex_code='F'", (sid,), fetch_one=True)["id"]
    db._execute("INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                "VALUES (%s,'supplementary_annex',%s,'SIGNING_AGREEMENT','h','s',1,'k','a','[]'::jsonb)", (sid, rid))
    ob.seal_supplementary_annex(sid, "F", 1)
    assert ob.supplementary_annex_status(sid)["F"]["status"] == "sealed"
    ob.build_supplementary_annex(sid, "G", 1)                       # now allowed
    ob.build_supplementary_annex(sid, "F", 1)                       # a later correction builds a new draft
    db._execute("INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                "SELECT %s,'supplementary_annex',id,'SIGNING_AGREEMENT','h2','s',1,'k','a','[]'::jsonb FROM onboarding_supplementary_annexes WHERE society_id=%s AND annex_code='F' AND status='draft'", (sid, sid))
    ob.seal_supplementary_annex(sid, "F", 1)                        # re-seal supersedes the old one (no unique-violation)
    assert db._execute("SELECT COUNT(*) AS n FROM onboarding_supplementary_annexes WHERE society_id=%s AND annex_code='F' AND status='superseded'", (sid,), fetch_one=True)["n"] == 1
