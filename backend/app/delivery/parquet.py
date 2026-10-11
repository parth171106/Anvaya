"""Parquet export via DuckDB from a registered pyarrow table, checked by reading it back (TRD.md §13). DuckDB never
loads extensions here (no sqlite_scanner), so nothing downloads at runtime."""
import time
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA = pa.schema([
    ("event_id", pa.string()), ("raw_id", pa.string()), ("seq", pa.int64()), ("time", pa.int64()),
    ("device", pa.string()), ("vendor", pa.string()), ("product", pa.string()), ("format", pa.string()),
    ("class_uid", pa.int32()), ("class_name", pa.string()), ("activity_name", pa.string()),
    ("src_ip", pa.string()), ("src_port", pa.int32()), ("dst_ip", pa.string()), ("dst_port", pa.int32()),
    ("protocol", pa.string()), ("direction", pa.string()), ("user_name", pa.string()), ("action", pa.string()),
    ("status", pa.string()), ("severity", pa.string()), ("title", pa.string()), ("parse_confidence", pa.int32()),
    ("parser", pa.string()), ("rule_id", pa.string()), ("roundtrip_ok", pa.int8()),
    ("roundtrip_coverage", pa.float64()), ("ocsf_json", pa.string()),
])


def _q(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def export_parquet(repo, lake_dir: Path, from_ms: int | None = None, to_ms: int | None = None) -> dict:
    t0 = time.perf_counter()
    rows = repo.events_flat(from_ms, to_ms)
    lo = from_ms if from_ms is not None else (rows[0]["time"] if rows else 0)
    hi = to_ms if to_ms is not None else (rows[-1]["time"] if rows else 0)
    lake_dir.mkdir(parents=True, exist_ok=True)
    path = lake_dir / f"events-{lo}-{hi}.parquet"
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    con = duckdb.connect()
    try:
        con.register("t", table)
        con.execute(f"COPY (SELECT * FROM t ORDER BY time) TO {_q(path)} (FORMAT PARQUET)")
        read_back = con.execute(f"SELECT COUNT(*) FROM read_parquet({_q(path)})").fetchone()[0]
    finally:
        con.close()
    return {"file": path.as_posix(), "rows": len(rows), "duckdb_rows": read_back, "bytes": path.stat().st_size,
            "took_ms": round((time.perf_counter() - t0) * 1000)}


def list_exports(lake_dir: Path) -> list[dict]:
    if not lake_dir.exists():
        return []
    return [{"file": f.as_posix(), "rows": pq.read_metadata(f).num_rows, "bytes": f.stat().st_size,
             "created": int(f.stat().st_mtime * 1000)} for f in sorted(lake_dir.glob("events-*.parquet"))]
