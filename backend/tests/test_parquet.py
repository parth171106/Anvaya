import json

import duckdb
import pyarrow.parquet as pq

from app.delivery.parquet import export_parquet, list_exports
from tests.conftest import ingest_scenario


def test_export_count_equals_read_back(c):
    ingest_scenario(c)
    c.worker.drain()
    out = export_parquet(c.repo, c.cfg.data_dir / "lake")
    assert out["rows"] == out["duckdb_rows"] == 207 and out["bytes"] > 0
    t = pq.read_table(out["file"])
    assert t.num_rows == 207 and "ocsf_json" in t.column_names and "anvaya_json" not in t.column_names
    times = t.column("time").to_pylist()
    assert times == sorted(times)
    first = duckdb.sql(f"SELECT device, class_uid FROM read_parquet('{out['file']}') LIMIT 1").fetchone()
    assert first == ("fw01", 4001)
    assert json.loads(t.column("ocsf_json")[0].as_py())["class_uid"] == 4001
    assert list_exports(c.cfg.data_dir / "lake")[0]["rows"] == 207


def test_export_empty_store(c):
    out = export_parquet(c.repo, c.cfg.data_dir / "lake")
    assert out["rows"] == out["duckdb_rows"] == 0


def test_time_window(c):
    recs = ingest_scenario(c)
    c.worker.drain()
    ev = c.repo.get_event("e-" + recs[163].raw_id[2:])
    out = export_parquet(c.repo, c.cfg.data_dir / "lake", ev.ocsf["time"], ev.ocsf["time"])
    assert out["rows"] == out["duckdb_rows"] == 1


def test_siem_file_sink(c):
    ingest_scenario(c)
    c.worker.drain()
    lines = (c.cfg.data_dir / "outbox" / "siem-forward.ndjson").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 207 and lines[0].startswith("<134>1 2026-09-30T04:30:00Z anvaya - ocsf - {")
    assert json.loads(lines[0].split(" - ocsf - ", 1)[1])["class_uid"] == 4001
    st = c.siem.status()
    assert st["forwarded"] == 207 and st["last_payload"] == lines[-1] and st["status"] == "ok"
