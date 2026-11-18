"""Settings -> Documents: the register, View / Download route, and Verify / Verify all callbacks for issued Agreement and NOC PDFs.

Offline (fake database + a temp assets folder). The real SQL and the append-only trigger are checked against Postgres in
test_issued_documents_live.py.
"""
import pytest
from flask import Flask

from app.dash_apps.callbacks import documents_callbacks as dcb
from app.dash_apps.pages import documents_page as dp
from app.routes import document_routes as dr
from app.security import guards
from app.services import document_archive as da
from test.archive_fixtures import FakeDB

SID = 7


class Session:
    """What the signed-in person is, as the server session sees it."""
    uid, sid, role = 11, SID, "admin"


@pytest.fixture
def world(tmp_path, monkeypatch):
    db = FakeDB()
    db.nocs[5] = {"id": 5, "society_id": SID, "apartment_id": 3, "certificate_no": "NOC/7/2026/5", "issued_date": "2026-11-17",
                  "valid_until": "2026-11-30", "body_text": "NO OBJECTION CERTIFICATE\nFlat A-101 has no dues.", "qr_payload": "q"}
    db.flats[3] = "A-101"
    monkeypatch.setattr(da, "assets_root", lambda: tmp_path.resolve())
    monkeypatch.setattr(da, "_db", lambda d=None: d if d is not None else db)
    sess = Session()
    sess.uid, sess.sid, sess.role = 11, SID, "admin"
    for mod in (dr, dcb):
        monkeypatch.setattr(mod, "get_current_user_id", lambda: sess.uid)
        monkeypatch.setattr(mod, "get_current_society_id", lambda: sess.sid)
        monkeypatch.setattr(mod, "get_current_user_role", lambda: sess.role)
    monkeypatch.setattr(guards, "get_current_user_id", lambda: sess.uid)
    monkeypatch.setattr(guards, "get_current_user_role", lambda: sess.role)
    monkeypatch.setattr(guards, "_setup_blocks_callback", lambda: False)
    audits = []
    from app.services import onboarding_service as ob
    monkeypatch.setattr(ob, "_audit", lambda sid, uid, action, rtype, rid, extra=None: audits.append((sid, uid, action, rid, extra)))
    doc = da.archive_noc(SID, 5, None, society_name="Green Park", society_address="Agra", db=db)
    return {"db": db, "root": tmp_path, "doc": doc, "sess": sess, "audits": audits}


@pytest.fixture
def client(world):
    app = Flask(__name__)
    app.register_blueprint(dr.documents_bp)
    return app.test_client()


def _file(world):
    return world["root"] / str(SID) / "NOCs" / world["doc"]["filename"]


# ── the route ────────────────────────────────────────────────────────────────────────────────────────────
def test_admin_can_view_the_pdf_inline_with_its_fingerprint(client, world):
    r = client.get(f"/documents/{world['doc']['id']}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF-")
    assert r.headers["X-Document-SHA256"] == world["doc"]["sha256"]
    assert "private" in r.headers["Cache-Control"] and "no-store" in r.headers["Cache-Control"]
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["Content-Disposition"].startswith("inline")
    assert world["audits"][-1][2] == "DOCUMENT_VIEWED"


def test_download_is_an_attachment_named_like_the_stored_file(client, world):
    r = client.get(f"/documents/{world['doc']['id']}?download=1")
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert world["doc"]["filename"] in r.headers["Content-Disposition"]
    assert world["audits"][-1][2] == "DOCUMENT_DOWNLOADED"


def test_only_a_signed_in_admin_of_a_society_gets_a_file(client, world):
    did = world["doc"]["id"]
    world["sess"].uid = None
    assert client.get(f"/documents/{did}").status_code == 401
    world["sess"].uid, world["sess"].role = 11, "apartment"
    assert client.get(f"/documents/{did}").status_code == 403
    world["sess"].role, world["sess"].sid = "admin", None
    assert client.get(f"/documents/{did}").status_code == 403


def test_another_societys_document_and_unknown_ids_are_404(client, world):
    did = world["doc"]["id"]
    world["sess"].sid = 8                                           # a different society's admin, same id
    assert client.get(f"/documents/{did}").status_code == 404
    world["sess"].sid = SID
    assert client.get("/documents/99999").status_code == 404
    assert not any(a[2].startswith("DOCUMENT_") and a[2] != "DOCUMENT_INTEGRITY_FAILED" for a in world["audits"])


def test_an_altered_file_is_refused_with_both_hashes_and_audited(client, world):
    f = _file(world)
    f.write_bytes(f.read_bytes() + b"\n%tampered")
    r = client.get(f"/documents/{world['doc']['id']}")
    assert r.status_code == 409 and not r.data.startswith(b"%PDF") and b"%tampered" not in r.data
    body = r.get_data(as_text=True)
    assert world["doc"]["sha256"] in body and "Integrity check failed" in body
    assert "X-Document-SHA256" not in r.headers
    assert world["audits"][-1][2] == "DOCUMENT_INTEGRITY_FAILED" and world["audits"][-1][4]["status"] == "altered"


def test_a_missing_file_is_refused_and_audited(client, world):
    _file(world).unlink()
    r = client.get(f"/documents/{world['doc']['id']}?download=1")
    assert r.status_code == 409 and "could not be found" in r.get_data(as_text=True)
    assert world["audits"][-1][4]["status"] == "missing"


# ── the page ─────────────────────────────────────────────────────────────────────────────────────────────
def _walk(c):
    yield c
    kids = getattr(c, "children", None)
    for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
        if k is not None and not isinstance(k, (str, int, float)):
            yield from _walk(k)


def _text(c) -> str:
    """All the visible text under a component, including plain strings that sit inside a list of children."""
    out = []
    for n in _walk(c):
        kids = getattr(n, "children", None)
        for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
            if isinstance(k, (str, int, float)):
                out.append(str(k))
    return " ".join(out)


def test_only_the_admin_of_a_society_gets_the_tab():
    for role in ("apartment", "accountant", "auditor", "master", "adviser", "", None):
        assert dp.documents_tab(role, SID) is None
    assert dp.documents_tab("admin", None) is None
    assert dp.documents_tab("admin", SID) is not None


def test_register_lists_documents_with_open_links_and_verify_buttons(world):
    world["db"].nocs[5]["body_text"] = "NO OBJECTION CERTIFICATE\nEdited."
    v2 = da.archive_noc(SID, 5, "NO OBJECTION CERTIFICATE\nEdited.", db=world["db"])
    page = dp.register_body(SID)
    text = _text(page)
    assert "NOC/7/2026/5" in text and "Flat A-101" in text and "latest" in text and "earlier version" in text
    hrefs = {getattr(n, "href", None) for n in _walk(page)}
    for d in (world["doc"], v2):
        assert f"/documents/{d['id']}" in hrefs and f"/documents/{d['id']}?download=1" in hrefs
    ids = [n.id for n in _walk(page) if isinstance(getattr(n, "id", None), dict)]
    assert {"type": "idoc-verify", "id": v2["id"]} in ids and {"type": "idoc-status", "id": world["doc"]["id"]} in ids
    codes = [n for n in _walk(page) if n.__class__.__name__ == "Code"]
    assert any(c.title == v2["sha256"] for c in codes)              # the full fingerprint is one hover away


def test_register_filter_and_empty_state(world):
    assert "Nothing has been filed yet" in _text(dp.register_body(SID, "agreement"))   # a NOC only: no agreements yet
    assert "NOC/7/2026/5" in _text(dp.register_body(SID, "noc"))
    assert "Nothing has been filed yet" in _text(dp.register_body(99))


# ── verify_outcome (what Verify shows) ───────────────────────────────────────────────────────────────────
def _res(status="ok", record="current", **kw):
    return {"id": 1, "status": status, "record": record, "expected": "a" * 64, "actual": "b" * 64, **kw}


def test_all_good_shows_success_and_the_record_match():
    statuses, summary = dp.verify_outcome({1: _res()}, [1])
    assert "Verified" in _text(statuses[0]) and "Matches the record" in _text(statuses[0])
    assert summary.children[0].color == "success"


def test_an_altered_file_shows_danger_and_both_hashes_on_hover():
    statuses, summary = dp.verify_outcome({1: _res("altered", "n/a"), 2: _res()}, [1, 2])
    assert "ALTERED" in _text(statuses[0]) and "a" * 64 in statuses[0].title and "b" * 64 in statuses[0].title
    assert summary.children[0].color == "danger" and "1 of 2" in _text(summary)


def test_a_missing_file_says_so():
    statuses, summary = dp.verify_outcome({1: _res("missing", "n/a", actual=None)}, [1])
    assert "File missing" in _text(statuses[0]) and "no file" in statuses[0].title and summary.children[0].color == "danger"


def test_a_pdf_older_than_an_edit_to_the_record_is_flagged_as_stale_not_as_tampered():
    statuses, summary = dp.verify_outcome({1: _res(record="changed")}, [1])
    assert "Verified" in _text(statuses[0]) and "edited since" in _text(statuses[0])
    colours = [a.color for a in summary.children]
    assert colours == ["success", "warning"]


def test_unchecked_rows_come_back_as_none():
    statuses, _ = dp.verify_outcome({2: _res()}, [1, 2, 3])
    assert statuses[0] is None and statuses[1] is not None and statuses[2] is None


# ── record_status, verify_document and the register query ────────────────────────────────────────────────
def test_verify_document_reports_whether_the_record_text_has_changed(world):
    db, did = world["db"], world["doc"]["id"]
    assert da.verify_document(SID, did, db=db)["record"] == "current"
    db.nocs[5]["body_text"] = "NO OBJECTION CERTIFICATE\nSomeone edited this later."       # record moves on, PDF does not
    assert da.verify_document(SID, did, db=db)["record"] == "changed"
    v2 = da.archive_noc(SID, 5, None, db=db)                                                 # filing the new wording
    assert da.verify_document(SID, v2["id"], db=db)["record"] == "current"
    assert da.verify_document(SID, did, db=db)["record"] == "earlier"


def test_a_signed_scan_has_no_record_comparison(world):
    scan = da.store_signed_scan(SID, "noc", 5, "NOC/7/2026/5", "scan.pdf", b"%PDF-1.4 scan", 11, db=world["db"])
    assert da.verify_document(SID, scan["id"], db=world["db"])["record"] == "n/a"


def test_list_register_labels_flats_and_marks_the_latest(world):
    db = world["db"]
    v2 = da.archive_noc(SID, 5, "NO OBJECTION CERTIFICATE\nEdited.", db=db)
    rows = da.list_register(SID, db=db)
    assert [r["id"] for r in rows] == [v2["id"], world["doc"]["id"]]            # newest first
    assert all(r["label"] == "Flat A-101" for r in rows)
    assert [r["is_latest"] for r in rows] == [True, False]
    assert da.list_register(8, db=db) == []                                       # another society sees nothing


# ── the callbacks ────────────────────────────────────────────────────────────────────────────────────────
class Cap:
    """A stand-in for the Dash app that keeps the callback functions."""
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(f):
            self.fns[f.__name__] = f
            return f
        return deco


@pytest.fixture
def cbs():
    cap = Cap()
    dcb.register_documents_callbacks(cap)
    return cap.fns


def _trigger(prop_id, value, row_ids):
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    context_value.set(AttributeDict(**{
        "triggered_inputs": [{"prop_id": prop_id, "value": value}],
        "outputs_list": [[{"id": {"type": "idoc-status", "id": i}, "property": "children"} for i in row_ids]]}))


def test_callbacks_register_on_a_real_dash_app():
    from dash import Dash
    app = Dash(__name__, suppress_callback_exceptions=True)
    dcb.register_documents_callbacks(app)
    keys = " ".join(app.callback_map)
    assert "idoc-summary" in keys and "idoc-table" in keys


def test_verify_one_updates_only_its_own_row(cbs, world):
    did = world["doc"]["id"]
    _trigger('{"id":%d,"type":"idoc-verify"}.n_clicks' % did, 1, [did, 999])
    statuses, summary = cbs["idoc_verify"]([1, None], 0)
    assert "Verified" in _text(statuses[0]) and statuses[1].__class__.__name__ == "NoUpdate"        # the other row is left alone
    assert summary.children[0].color == "success" and not world["audits"]


def test_verify_all_flags_the_altered_file_and_audits_it(cbs, world):
    did = world["doc"]["id"]
    f = _file(world)
    f.write_bytes(f.read_bytes() + b"x")
    _trigger("idoc-verify-all.n_clicks", 1, [did])
    statuses, summary = cbs["idoc_verify"]([None], 1)
    assert "ALTERED" in _text(statuses[0]) and summary.children[0].color == "danger"
    assert [(a[2], a[3], a[4]["status"]) for a in world["audits"]] == [("DOCUMENT_INTEGRITY_FAILED", did, "altered")]


def test_a_rerendered_table_or_a_non_admin_does_not_verify(cbs, world):
    from dash.exceptions import PreventUpdate
    did = world["doc"]["id"]
    _trigger('{"id":%d,"type":"idoc-verify"}.n_clicks' % did, None, [did])           # no click, the table was redrawn
    with pytest.raises(PreventUpdate):
        cbs["idoc_verify"]([None], 0)
    world["sess"].role = "apartment"
    _trigger('{"id":%d,"type":"idoc-verify"}.n_clicks' % did, 1, [did])
    with pytest.raises(PreventUpdate):
        cbs["idoc_verify"]([1], 0)


def test_verify_ignores_the_browser_and_only_checks_this_societys_documents(cbs, world):
    world["sess"].sid = 8                                                              # another society's admin
    _trigger("idoc-verify-all.n_clicks", 1, [world["doc"]["id"]])                      # a forged id from the page
    statuses, summary = cbs["idoc_verify"]([None], 1)
    assert "Not found" in _text(statuses[0]) and not world["audits"]


def test_filter_redraws_the_table_for_the_session_society(cbs, world):
    table, summary = cbs["idoc_filter"]("noc")
    assert "NOC/7/2026/5" in _text(table) and summary is None
    world["sess"].sid = 8
    assert "Nothing has been filed yet" in _text(cbs["idoc_filter"]("all")[0])


# ── wiring ───────────────────────────────────────────────────────────────────────────────────────────────
def test_the_governance_settings_get_a_documents_tab_only_when_there_is_one():
    from dash import html

    from app.dash_apps.pages import governance_settings as gs

    def tabs(documents):
        tree = gs._wrap("admin", html.Div(), html.Div(), html.Div(), html.Div(), html.Div(), documents=documents)
        return [t.value for n in _walk(tree) if n.__class__.__name__ == "Tabs" for t in n.children]
    assert "tab-documents" in tabs(html.Div("x")) and "tab-documents" not in tabs(None)


def test_the_blueprint_and_callbacks_are_registered_in_the_app():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app"
    assert "documents_callbacks" in (root / "dash_apps" / "callbacks" / "__init__.py").read_text(encoding="utf-8")
    init = (root / "__init__.py").read_text(encoding="utf-8")
    assert "from app.routes.document_routes import documents_bp" in init and "register_blueprint(documents_bp)" in init
