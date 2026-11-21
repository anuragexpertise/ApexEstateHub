"""
H1 (G1/G2): the schema must install on a fresh database.

Parse database/estatehub.sql with pglast and walk the statements *in file
order*.  Keep a set of tables created so far; for every CREATE TRIGGER,
CREATE INDEX, ALTER TABLE and every REFERENCES target in a CREATE TABLE,
assert the referenced table was created earlier in the file.  A statement
that touches a table not yet created cannot install (that is exactly G1:
``CREATE TRIGGER trg_transactions_active_account ... ON transactions`` was
placed before ``CREATE TABLE transactions``).

The trigger now lives directly after the ``CREATE TABLE transactions``
definition, so this test passes.  It is deliberately run first against the
unfixed file (it reports ``trg_transactions_active_account`` on
``transactions``) and passes after the fix.
"""

import pglast
from pglast.ast import (
    AlterTableStmt,
    CreateStmt,
    CreateTrigStmt,
    IndexStmt,
)

SQL_PATH = "database/estatehub.sql"

# Intentional forward references are not allowed by the install rule.  This
# allow-list exists only to document the decision that none are intentional;
# add an entry here only if a genuine forward reference is required and
# install order cannot be changed.  Every entry must be commented with why.
ALLOW_LIST = {
    # ("stmt_index", "trigger", "table"): "reason",
}


def _statements():
    return pglast.parse_sql(open(SQL_PATH, encoding="utf-8").read())


def _forward_references(stmts):
    """Return [(index, kind, target_table)] for references to tables not yet
    created, walking statements in file order."""
    created = set()
    hits = []

    def check(target, kind, index):
        if target and target not in created and target not in _allowed(index, kind, target):
            hits.append((index, kind, target))

    for index, raw in enumerate(stmts, 1):
        stmt = getattr(raw, "stmt", None)
        if isinstance(stmt, CreateStmt):
            name = getattr(stmt.relation, "relname", None)
            if name:
                created.add(name)  # the table exists once this statement runs
            for elt in stmt.tableElts:
                for con in getattr(elt, "constraints", []) or []:
                    pkt = getattr(con, "pktable", None)
                    if pkt and getattr(pkt, "relname", None):
                        check(pkt.relname, "fk", index)
            for con in getattr(stmt, "constraints", []) or []:
                pkt = getattr(con, "pktable", None)
                if pkt and getattr(pkt, "relname", None):
                    check(pkt.relname, "fk-table", index)
        elif isinstance(stmt, (CreateTrigStmt, IndexStmt, AlterTableStmt)):
            check(getattr(stmt.relation, "relname", None), type(stmt).__name__, index)
    return hits


def _allowed(index, kind, target):
    return {t for (i, k, t) in ALLOW_LIST if i == index and k == kind}


def test_schema_has_no_forward_references():
    hits = _forward_references(_statements())
    assert not hits, (
        "schema statements reference tables created later in the file "
        f"(install would fail): {hits}"
    )


def test_transactions_trigger_is_after_table():
    """G1 regression: trg_transactions_active_account must come after CREATE
    TABLE transactions, not before it."""
    stmts = _statements()
    trigger_index = None
    table_index = None
    for index, raw in enumerate(stmts, 1):
        stmt = getattr(raw, "stmt", None)
        if isinstance(stmt, CreateTrigStmt) and stmt.trigname == "trg_transactions_active_account":
            trigger_index = index
        if isinstance(stmt, CreateStmt) and getattr(stmt.relation, "relname", None) == "transactions":
            table_index = index
    assert table_index is not None, "CREATE TABLE transactions not found"
    assert trigger_index is not None, "trg_transactions_active_account not found"
    assert trigger_index > table_index, (
        f"trg_transactions_active_account (stmt {trigger_index}) must come after "
        f"CREATE TABLE transactions (stmt {table_index})"
    )
