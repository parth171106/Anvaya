"""SQLite implementation of the Repository interface (TRD.md §4, BACKEND_SCHEMA.md §2)."""
import json
import sqlite3
import time
from pathlib import Path

from app.core.models import EventFilter, NormalizedEvent, RawMeta, RawRecord
from app.storage.flatten import flatten

SCHEMA = Path(__file__).with_name("schema.sql")
SUMMARY_COLS = ("e.event_id, e.raw_id, e.seq, e.time, e.device, e.vendor, e.format, e.class_uid, e.class_name,"
                " e.activity_name, e.src_ip, e.src_port, e.dst_ip, e.dst_port, e.protocol, e.direction, e.user_name,"
                " e.action, e.status, e.severity, e.title, e.parse_confidence")
FLAT_COLS = ["event_id", "raw_id", "seq", "time", "device", "vendor", "product", "format", "class_uid", "class_name",
             "activity_name", "src_ip", "src_port", "dst_ip", "dst_port", "protocol", "direction", "user_name",
             "action", "status", "severity", "title", "parse_confidence", "parser", "rule_id", "roundtrip_ok",
             "roundtrip_coverage", "ocsf_json", "anvaya_json"]


def dumps(o) -> str:
    return json.dumps(o, separators=(",", ":"))


class SqliteRepository:
    def __init__(self, db_path: Path, durable: bool = False):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not self.path.exists()
        # One connection, used only from the event loop thread (all routes are async).
        self.con = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA synchronous=FULL" if durable else "PRAGMA synchronous=NORMAL")
        self.con.execute("PRAGMA foreign_keys=ON")
        if fresh:
            self.con.executescript(SCHEMA.read_text(encoding="utf-8"))
        # Additive migration: retain receipts across restarts without rewriting existing logs.
        self.con.execute("CREATE TABLE IF NOT EXISTS ingest_receipts ("
                         "idempotency_key TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL,"
                         "raw_id TEXT NOT NULL REFERENCES raw_events(raw_id))")

    def close(self) -> None:
        self.con.close()

    def execute_readonly(self, sql: str, params: dict, timeout_s: float) -> tuple[list[str], list[list]]:
        """Search runs on a separate mode=ro, query_only connection, aborted after timeout_s; ≤ 200 rows."""
        con = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        try:
            con.execute("PRAGMA query_only = ON")
            deadline = time.monotonic() + timeout_s
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
            try:
                cur = con.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "interrupted" in str(e):
                    raise TimeoutError("query exceeded the time limit")
                raise
            cols = [d[0] for d in cur.description]
            return cols, [list(r) for r in cur.fetchmany(200)]
        finally:
            con.close()

    def tx(self):
        """`with repo.tx():` → one transaction (BEGIN … COMMIT, ROLLBACK on error)."""
        return _Tx(self.con)

    # ---- raw_events -------------------------------------------------------------------------------------------
    def ingest_receipt(self, key: str):
        return self.con.execute("SELECT * FROM ingest_receipts WHERE idempotency_key=?", (key,)).fetchone()

    def insert_ingest_receipt(self, key: str, rec: RawRecord) -> None:
        self.con.execute("INSERT INTO ingest_receipts VALUES (?,?,?)", (key, rec.raw_sha256, rec.raw_id))

    def insert_raw(self, rec: RawRecord) -> None:
        self.con.execute(
            "INSERT INTO raw_events(seq, raw_id, raw_sha256, size, segment, offset, encoding, flags, transport, peer_ip,"
            " received_at, wall_received_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
            (rec.seq, rec.raw_id, rec.raw_sha256, rec.size, rec.segment, rec.offset, rec.meta.encoding,
             dumps(rec.meta.flags), rec.meta.transport, rec.meta.peer_ip, rec.received_at, rec.wall_received_at))

    @staticmethod
    def _raw(r) -> RawRecord:
        return RawRecord(raw_id=r["raw_id"], seq=r["seq"], raw_sha256=r["raw_sha256"], size=r["size"],
                         segment=r["segment"], offset=r["offset"], received_at=r["received_at"],
                         wall_received_at=r["wall_received_at"], batch_id=r["batch_id"],
                         meta=RawMeta(transport=r["transport"], peer_ip=r["peer_ip"], flags=json.loads(r["flags"]),
                                      encoding=r["encoding"]))

    def raw_records(self) -> list[RawRecord]:
        return [self._raw(r) for r in self.con.execute("SELECT * FROM raw_events ORDER BY seq")]

    def pending_raw_ids(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT raw_id FROM raw_events WHERE status='pending' ORDER BY seq")]

    def get_raw(self, raw_id: str) -> RawRecord | None:
        r = self.con.execute("SELECT * FROM raw_events WHERE raw_id=?", (raw_id,)).fetchone()
        return self._raw(r) if r else None

    def unsealed_raw(self) -> list[RawRecord]:
        return [self._raw(r) for r in self.con.execute("SELECT * FROM raw_events WHERE batch_id IS NULL ORDER BY seq")]

    def raw_in_batch(self, b) -> list[sqlite3.Row]:
        return self.con.execute("SELECT seq, raw_id, raw_sha256 FROM raw_events WHERE seq BETWEEN ? AND ? ORDER BY seq",
                                (b["first_seq"], b["last_seq"])).fetchall()

    def set_raw_sha(self, raw_id: str, sha_hex: str) -> None:
        self.con.execute("UPDATE raw_events SET raw_sha256=? WHERE raw_id=?", (sha_hex, raw_id))

    # ---- ledger -----------------------------------------------------------------------------------------------
    def last_batch(self):
        return self.con.execute("SELECT * FROM ledger_batches ORDER BY batch_id DESC LIMIT 1").fetchone()

    def batch(self, batch_id: int):
        return self.con.execute("SELECT * FROM ledger_batches WHERE batch_id=?", (batch_id,)).fetchone()

    def batches(self, from_batch: int = 1) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM ledger_batches WHERE batch_id>=? ORDER BY batch_id",
                                (from_batch,)).fetchall()

    def batches_page(self, limit: int, before_batch: int | None) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM ledger_batches WHERE batch_id < ? ORDER BY batch_id DESC LIMIT ?",
                                (before_batch or 2**62, limit)).fetchall()

    def insert_batch(self, b: dict) -> None:
        self.con.execute("INSERT INTO ledger_batches(batch_id, first_seq, last_seq, leaf_count, merkle_root, prev_head,"
                         " head, signature, pubkey_fp, sealed_at) VALUES (:batch_id,:first_seq,:last_seq,:leaf_count,"
                         ":merkle_root,:prev_head,:head,:signature,:pubkey_fp,:sealed_at)", b)
        self.con.execute("UPDATE raw_events SET batch_id=? WHERE seq BETWEEN ? AND ?",
                         (b["batch_id"], b["first_seq"], b["last_seq"]))

    def update_batch_seal(self, batch_id: int, merkle_root: str, prev_head: str, head: str, signature: str) -> None:
        self.con.execute("UPDATE ledger_batches SET merkle_root=?, prev_head=?, head=?, signature=?, resealed=1"
                         " WHERE batch_id=?", (merkle_root, prev_head, head, signature, batch_id))

    def insert_witness_sig(self, batch_id, witness, status, head, cosig, reason, at) -> None:
        self.con.execute("INSERT INTO witness_signatures VALUES (?,?,?,?,?,?,?)",
                         (batch_id, witness, status, head, cosig, reason, at))

    def witness_sigs(self, batch_ids: list[int]) -> dict[int, dict[str, bool]]:
        out: dict[int, dict[str, bool]] = {}
        q = ",".join("?" * len(batch_ids)) or "NULL"
        for r in self.con.execute(f"SELECT batch_id, witness, status FROM witness_signatures WHERE batch_id IN ({q})",
                                  batch_ids):
            out.setdefault(r[0], {})[r[1]] = r[2] == "cosigned"
        return out

    def cosigned_batches(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM (SELECT batch_id FROM witness_signatures WHERE status='cosigned'"
                                " GROUP BY batch_id HAVING COUNT(*) = 2)").fetchone()[0]

    # ---- meta & audit ------------------------------------------------------------------------------------------
    def set_meta(self, key: str, value) -> None:
        self.con.execute("INSERT INTO meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, dumps(value)))

    def get_meta(self, key: str):
        r = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def audit(self, at: int, actor: str, action: str, obj: str | None = None, detail: dict | None = None) -> None:
        self.con.execute("INSERT INTO audit_log(at, actor, action, object, detail) VALUES (?,?,?,?,?)",
                         (at, actor, action, obj, dumps(detail or {})))

    # ---- events -------------------------------------------------------------------------------------------------
    def insert_events(self, events: list[NormalizedEvent], flags: dict[str, list[str]] | None = None) -> None:
        """Insert (or, on replay, update) events; mark their raw records parsed; upsert sources. Call inside tx()."""
        flags = flags or {}
        for ev in events:
            row = flatten(ev)
            cols = list(row)
            self.con.execute(
                f"INSERT INTO events({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) ON CONFLICT(event_id) DO "
                f"UPDATE SET {','.join(f'{k}=excluded.{k}' for k in cols if k != 'event_id')}", list(row.values()))
            raw = self.con.execute("SELECT flags, received_at, wall_received_at FROM raw_events WHERE raw_id=?",
                                   (ev.raw_id,)).fetchone()
            merged = sorted(set(json.loads(raw["flags"])) | set(flags.get(ev.raw_id, [])))
            self.con.execute("UPDATE raw_events SET status='parsed', flags=? WHERE raw_id=?", (dumps(merged), ev.raw_id))
            a = ev.anvaya
            self.con.execute(
                "INSERT INTO sources(device, vendor, product, format, parser, first_seen, last_seen, first_seen_wall,"
                " last_seen_wall, events_total) VALUES (?,?,?,?,?,?,?,?,?,1) ON CONFLICT(device) DO UPDATE SET"
                " last_seen=MAX(last_seen, excluded.last_seen), last_seen_wall=MAX(last_seen_wall, excluded.last_seen_wall),"
                " events_total=events_total+1, parser=excluded.parser",
                (a.device, a.vendor, a.product, a.format, a.parser, raw["received_at"], raw["received_at"],
                 raw["wall_received_at"], raw["wall_received_at"]))

    def summaries(self, event_ids: list[str]) -> list[dict]:
        q = ",".join("?" * len(event_ids))
        rows = self.con.execute(f"SELECT {SUMMARY_COLS}, r.batch_id, r.flags FROM events e JOIN raw_events r"
                                f" USING(raw_id) WHERE e.event_id IN ({q}) ORDER BY e.seq", event_ids).fetchall()
        return [self._summary(r) for r in rows]

    @staticmethod
    def _summary(r) -> dict:
        d = dict(r)
        d["flags"] = json.loads(d["flags"])
        return d

    def list_events(self, f: EventFilter) -> tuple[list[dict], int | None]:
        where, args = [], []
        if f.before_seq is not None:
            where.append("e.seq < ?"); args.append(f.before_seq)
        for col in ("device", "format", "class_uid"):
            if getattr(f, col) is not None:
                where.append(f"e.{col} = ?"); args.append(getattr(f, col))
        if f.q:
            where.append("(e.src_ip LIKE ? OR e.dst_ip LIKE ? OR e.title LIKE ? OR e.user_name LIKE ?)")
            args += [f"%{f.q}%"] * 4
        sql = (f"SELECT {SUMMARY_COLS}, r.batch_id, r.flags FROM events e JOIN raw_events r USING(raw_id)"
               f"{' WHERE ' + ' AND '.join(where) if where else ''} ORDER BY e.seq DESC LIMIT ?")
        rows = [self._summary(r) for r in self.con.execute(sql, args + [f.limit + 1])]
        more = len(rows) > f.limit
        rows = rows[: f.limit]
        return rows, (rows[-1]["seq"] if more and rows else None)

    def query_events(self, f: EventFilter) -> list[NormalizedEvent]:
        ids = [r["event_id"] for r in self.list_events(f)[0]]
        return [self.get_event(i) for i in ids]

    def get_event(self, event_id: str) -> NormalizedEvent | None:
        r = self.con.execute("SELECT event_id, raw_id, seq, ocsf_json, anvaya_json FROM events WHERE event_id=?",
                             (event_id,)).fetchone()
        if not r:
            return None
        return NormalizedEvent(event_id=r[0], raw_id=r[1], seq=r[2], ocsf=json.loads(r[3]),
                               anvaya=json.loads(r[4]))

    def events_flat(self, from_ms: int | None = None, to_ms: int | None = None) -> list[dict]:
        cols = [c for c in FLAT_COLS if c != "anvaya_json"]
        return [dict(r) for r in self.con.execute(
            f"SELECT {','.join(cols)} FROM events WHERE time >= ? AND time <= ? ORDER BY time",
            (from_ms if from_ms is not None else -2**62, to_ms if to_ms is not None else 2**62))]

    # ---- quarantine ---------------------------------------------------------------------------------------------
    def quarantine(self, raw_id: str, group_id: str, signature: str, reason: str, detail: str | None, at: int) -> None:
        self.con.execute("INSERT INTO quarantine VALUES (?,?,?,?,?,?) ON CONFLICT(raw_id) DO UPDATE SET"
                         " group_id=excluded.group_id, shape_signature=excluded.shape_signature,"
                         " reason=excluded.reason, detail=excluded.detail",
                         (raw_id, group_id, signature, reason, detail, at))
        if reason != "roundtrip_fail":
            self.con.execute("UPDATE raw_events SET status='quarantined' WHERE raw_id=?", (raw_id,))

    def unquarantine(self, raw_id: str) -> None:
        self.con.execute("DELETE FROM quarantine WHERE raw_id=?", (raw_id,))

    def quarantine_groups(self) -> list[dict]:
        rows = self.con.execute(
            "SELECT q.group_id, q.shape_signature, q.reason, COUNT(*) AS count, MIN(r.received_at) AS first_seen,"
            " MAX(r.received_at) AS last_seen, MIN(r.transport) AS transport, MIN(r.peer_ip) AS peer_ip"
            " FROM quarantine q JOIN raw_events r USING(raw_id) GROUP BY q.group_id, q.reason ORDER BY first_seen")
        return [dict(r) for r in rows]

    def quarantine_raw_ids(self, group_id: str) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT q.raw_id FROM quarantine q JOIN raw_events r USING(raw_id) WHERE q.group_id=? ORDER BY r.seq",
            (group_id,))]

    def quarantine_total(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]

    # ---- sources ------------------------------------------------------------------------------------------------
    def sources(self) -> list[dict]:
        return [dict(r) for r in self.con.execute("SELECT * FROM sources ORDER BY device")]

    def update_source_status(self, device: str, status: str, expected_gap_s: float | None) -> None:
        self.con.execute("UPDATE sources SET status=?, expected_gap_s=? WHERE device=?", (status, expected_gap_s, device))

    def wall_times(self, raw_ids: list[str]) -> dict[str, int]:
        q = ",".join("?" * len(raw_ids))
        return {r[0]: r[1] for r in self.con.execute(
            f"SELECT raw_id, wall_received_at FROM raw_events WHERE raw_id IN ({q})", raw_ids)}

    # ---- incidents ----------------------------------------------------------------------------------------------
    def events_from_src(self, ip: str) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT event_id, time, device, class_uid, activity_name, src_ip, dst_ip, dst_port, user_name, action,"
            " status, title FROM events WHERE src_ip=? ORDER BY time, seq", (ip,))]

    def incident_by_key(self, attacker_ip: str, window_start: int):
        return self.con.execute("SELECT * FROM incidents WHERE attacker_ip=? AND window_start=?",
                                (attacker_ip, window_start)).fetchone()

    def upsert_incident(self, inc: dict, links: list[tuple[str, str]]) -> str:
        existing = self.incident_by_key(inc["attacker_ip"], inc["window_start"])
        if existing:
            iid = existing["incident_id"]
            self.con.execute("UPDATE incidents SET target_ip=:target_ip, title=:title, stages=:stages, devices=:devices,"
                             " risk=:risk, level=:level, risk_breakdown=:risk_breakdown, first_time=:first_time,"
                             " last_time=:last_time WHERE incident_id=:incident_id", {**inc, "incident_id": iid})
        else:
            n = self.con.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] + 1
            iid = f"inc-{n:04d}"
            self.con.execute("INSERT INTO incidents(incident_id, attacker_ip, target_ip, window_start, title, stages,"
                             " devices, risk, level, risk_breakdown, first_time, last_time) VALUES (:incident_id,"
                             " :attacker_ip, :target_ip, :window_start, :title, :stages, :devices, :risk, :level,"
                             " :risk_breakdown, :first_time, :last_time)", {**inc, "incident_id": iid})
        self.con.executemany("INSERT OR IGNORE INTO incident_events VALUES (?,?,?)",
                             [(iid, eid, stage) for eid, stage in links])
        return iid

    def incident_summary(self, incident_id: str) -> dict | None:
        r = self.con.execute("SELECT i.*, (SELECT COUNT(*) FROM incident_events e WHERE e.incident_id=i.incident_id)"
                             " AS event_count FROM incidents i WHERE incident_id=?", (incident_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        for k in ("stages", "devices", "risk_breakdown"):
            d[k] = json.loads(d[k])
        return d

    def incidents(self) -> list[dict]:
        ids = [r[0] for r in self.con.execute("SELECT incident_id FROM incidents ORDER BY first_time DESC")]
        return [self.incident_summary(i) for i in ids]

    def incident_events(self, incident_id: str) -> list[dict]:
        return [dict(r) for r in self.con.execute(
            "SELECT ie.stage, e.event_id, e.time, e.device, e.class_uid, e.dst_ip, e.dst_port, e.user_name, e.action,"
            " e.status, e.title, e.src_ip FROM incident_events ie JOIN events e USING(event_id)"
            " WHERE ie.incident_id=? ORDER BY e.time, e.seq", (incident_id,))]

    # ---- parsers ------------------------------------------------------------------------------------------------
    def upsert_parser(self, pack, origin: str, approved_by: str | None = None, approved_at: int | None = None) -> None:
        self.con.execute(
            "INSERT INTO parsers VALUES (?,?,'active',?,?,?,?,?,?,?) ON CONFLICT(name, version) DO UPDATE SET"
            " status='active', yaml=excluded.yaml, yaml_sha256=excluded.yaml_sha256",
            (pack.name, pack.version, origin, pack.format, pack.priority, pack.yaml, pack.yaml_sha256, approved_by,
             approved_at))

    def parsers(self) -> list[dict]:
        stats = {r[0]: (r[1], r[2]) for r in self.con.execute(
            "SELECT parser, COUNT(*), AVG(roundtrip_ok) FROM events GROUP BY parser")}
        out = []
        for r in self.con.execute("SELECT * FROM parsers ORDER BY priority"):
            n, rate = stats.get(f"{r['name']}@{r['version']}", (0, None))
            out.append({"name": r["name"], "version": r["version"], "status": r["status"], "origin": r["origin"],
                        "format": r["format"], "approved_by": r["approved_by"], "approved_at": r["approved_at"],
                        "roundtrip_pass_rate": round(rate, 4) if rate is not None else None, "events_parsed": n})
        return out

    # ---- stats (API 2) ------------------------------------------------------------------------------------------
    def counts(self) -> dict:
        one = lambda sql: self.con.execute(sql).fetchone()[0]
        return {
            "raw_total": one("SELECT COUNT(*) FROM raw_events"),
            "normalized_total": one("SELECT COUNT(*) FROM events"),
            "quarantined_total": one("SELECT COUNT(*) FROM quarantine"),
            "formats_detected": one("SELECT COUNT(DISTINCT format) FROM events"),
            "sealed_records": one("SELECT COUNT(*) FROM raw_events WHERE batch_id IS NOT NULL"),
            "sealed_batches": one("SELECT COUNT(*) FROM ledger_batches"),
            "open_incidents": one("SELECT COUNT(*) FROM incidents WHERE status='open'"),
            "sources_total": one("SELECT COUNT(*) FROM sources"),
            "sources_silent": one("SELECT COUNT(*) FROM sources WHERE status='silent'"),
            "roundtrip_ok": one("SELECT COUNT(*) FROM events WHERE roundtrip_ok=1"),
        }

    def raw_received_since_wall(self, wall_ms: int) -> int:
        return self.con.execute("SELECT COUNT(*) FROM raw_events WHERE wall_received_at >= ?", (wall_ms,)).fetchone()[0]

    # ---- events (subset used by the ledger) ----------------------------------------------------------------------
    def event_evidence(self, raw_id: str):
        """(original bytes captured at parse time, lineage, event_id, device, time) or None if never parsed."""
        r = self.con.execute("SELECT event_id, device, time, ocsf_json, anvaya_json FROM events WHERE raw_id=?",
                             (raw_id,)).fetchone()
        if not r:
            return None
        return (json.loads(r["ocsf_json"])["raw_data"].encode("utf-8"), json.loads(r["anvaya_json"])["lineage"],
                r["event_id"], r["device"], r["time"])


class _Tx:
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.con.execute("BEGIN")

    def __exit__(self, exc_type, *_):
        self.con.execute("ROLLBACK" if exc_type else "COMMIT")
