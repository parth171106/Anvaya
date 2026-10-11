import sqlite3
from pathlib import Path

import pytest

SCHEMA = Path(__file__).parents[1] / "app" / "storage" / "schema.sql"
TABLES = {"raw_events", "events", "ledger_batches", "witness_signatures", "sources", "parsers", "parser_drafts",
          "quarantine", "incidents", "incident_events", "audit_log", "meta"}


def test_schema_creates_every_table(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    names = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    assert TABLES <= names


def test_audit_log_is_append_only(tmp_path):
    con = sqlite3.connect(tmp_path / "t.db")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    con.execute("insert into audit_log(at, actor, action) values (1, 'system', 'demo.reset')")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("delete from audit_log")
