# test/archive_fixtures.py
"""Shared fakes for the issued-document tests: just enough of db._execute for issued_documents, nocs, apartments and
signed_records. The real SQL is exercised against Postgres in test_issued_documents_live.py."""
import io


def png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (60, 20), "navy").save(b, "PNG")
    return b.getvalue()


class FakeDB:
    """Just enough of db._execute for issued_documents, nocs and signed_records."""
    def __init__(self):
        self.docs, self.nocs, self.sealed, self.next_id = [], {}, set(), 1
        self.flats = {}                                            # apartment_id -> flat_number

    def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
        s = " ".join(sql.split())
        if s.startswith("SELECT * FROM issued_documents WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND sha256"):
            r = [x for x in self.docs if (x["society_id"], x["subject_kind"], x["subject_id"], x["sha256"]) == tuple(params)]
            return r[0] if r else None
        if s.startswith("INSERT INTO issued_documents"):
            sid, kind, subj = params[0], params[1], params[2]
            ver = 1 + max([x["version"] for x in self.docs if (x["society_id"], x["subject_kind"], x["subject_id"]) == (sid, kind, subj)] or [0])
            keys = ["society_id", "subject_kind", "subject_id", "_a", "_b", "_c", "document_no", "filename", "sha256", "size_bytes",
                    "text_hash", "origin", "event", "created_by"]
            row = dict(zip(keys, params)); [row.pop(k) for k in ("_a", "_b", "_c")]
            row.update(id=self.next_id, version=ver); self.next_id += 1
            if any(x["sha256"] == row["sha256"] and x["subject_id"] == subj for x in self.docs):
                return None
            self.docs.append(row); return row
        if s.startswith("SELECT * FROM issued_documents WHERE id=%s AND society_id=%s"):
            r = [x for x in self.docs if x["id"] == params[0] and x["society_id"] == params[1]]
            return r[0] if r else None
        if s.startswith("SELECT * FROM issued_documents WHERE society_id=%s"):
            return [x for x in self.docs if x["society_id"] == params[0]]
        if s.startswith("SELECT MAX(version) AS v FROM issued_documents WHERE society_id=%s AND subject_kind=%s AND subject_id=%s"):
            vs = [x["version"] for x in self.docs if (x["society_id"], x["subject_kind"], x["subject_id"]) == tuple(params)]
            return {"v": max(vs) if vs else None}
        if s.startswith("SELECT subject_kind, subject_id, MAX(version) AS v FROM issued_documents WHERE society_id=%s GROUP BY"):
            best = {}
            for x in self.docs:
                if x["society_id"] == params[0]:
                    k = (x["subject_kind"], x["subject_id"]); best[k] = max(best.get(k, 0), x["version"])
            return [{"subject_kind": k[0], "subject_id": k[1], "v": v} for k, v in best.items()]
        if s.startswith("SELECT dd.*, CASE WHEN dd.subject_kind = 'noc'"):
            out = []
            for x in sorted((d for d in self.docs if d["society_id"] == params[0]), key=lambda d: d["id"], reverse=True)[:params[1]]:
                flat = self.flats.get((self.nocs.get(x["subject_id"]) or {}).get("apartment_id")) if x["subject_kind"] == "noc" else None
                out.append({**x, "label": f"Flat {flat}" if flat else ""})
            return out
        if s.startswith("SELECT * FROM nocs"):
            n = self.nocs.get(params[0]); return n if n and n["society_id"] == params[1] else None
        if s.startswith("SELECT 1 AS x FROM signed_records"):
            return {"x": 1} if params[0] in self.sealed else None
        if s.startswith("UPDATE nocs SET body_text"):
            self.nocs[params[1]]["body_text"] = params[0]; return None
        if s.startswith("SELECT society_id, apartment_id, certificate_no"):    # document_signing.item_text('noc')
            n = self.nocs[params[0]]
            return {k: n.get(k) for k in ("society_id", "apartment_id", "certificate_no", "issued_date", "valid_until", "body_text")}
        raise AssertionError("unexpected SQL: " + s[:90])


