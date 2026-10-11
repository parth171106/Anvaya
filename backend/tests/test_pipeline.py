from datetime import date

from app.core.ids import group_id
from generator.br01 import build_br01_lines
from generator.formats import at
from tests.conftest import D, ingest_scenario


def collect(c):
    seen = []
    c.publish = lambda e, d: seen.append((e, d))  # capture instead of the bus
    return seen


def test_scenario_through_pipeline(c):
    seen = collect(c)
    ingest_scenario(c)
    c.worker.drain()
    s = c.stats()
    assert (s["raw_total"], s["normalized_total"], s["quarantined_total"]) == (207, 207, 0)
    assert s["formats_detected"] == 3 and s["parse_coverage_pct"] == 100.0
    assert (s["sealed_records"], s["sealed_batches"], s["cosigned_batches"]) == (192, 12, 12)
    assert s["sources_total"] == 3 and s["clock"]["label"] == "Scenario clock"
    assert sum(1 for e, _ in seen if e == "event.normalized") == 207
    assert {r["device"]: r["events_total"] for r in c.repo.sources()} == {"fw01": 104, "ids01": 33, "vpn01": 70}
    ev = c.repo.get_event("e-899f4edf0030")
    assert ev.ocsf["dst_endpoint"] == {"ip": "10.2.4.18", "port": 443} and ev.anvaya.parse_confidence == 91
    row = c.repo.summaries(["e-64f70aaee53f"])[0]
    assert (row["src_ip"], row["dst_ip"], row["dst_port"], row["protocol"], row["severity"], row["action"]) == \
        ("198.51.100.9", "10.2.4.18", 22, "tcp", "Medium", None)
    assert row["title"] == "ANVAYA-LAB SCAN Inbound TCP port sweep" and row["batch_id"] == 3


def test_br01_quarantined_in_one_group(c):
    seen = collect(c)
    ingest_scenario(c)
    lines = build_br01_lines(at(D, 10, 14, 3))
    for ln in lines:
        c.ingest(ln.encode(), "http", "127.0.0.1")
    c.worker.drain()
    groups = c.repo.quarantine_groups()
    assert len(groups) == 1
    g = groups[0]
    assert (g["shape_signature"], g["count"], g["reason"], g["transport"]) == ("EDGE|x12", 20, "no_fingerprint", "http")
    assert g["group_id"] == group_id("EDGE|x12") == "qg-38973b20"
    q = [d for e, d in seen if e == "event.quarantined"]
    assert len(q) == 20 and q[0]["preview"] == lines[0] and q[0]["reason"] == "no_fingerprint"
    assert c.stats()["parse_coverage_pct"] == round(100 * 207 / 227, 1)


def test_replay_without_pack_keeps_records_quarantined(c):
    seen = collect(c)
    for ln in build_br01_lines(at(date(2026, 9, 30), 10, 14, 3)):
        c.ingest(ln.encode(), "http", "127.0.0.1")
    c.worker.drain()
    rp, n = c.replays.start(c.repo.quarantine_raw_ids(group_id("EDGE|x12")))
    c.worker.drain()
    done = [d for e, d in seen if e == "replay.completed"]
    assert (rp, n) == ("rp-0001", 20) and done == [{"replay_id": "rp-0001", "parsed": 0, "still_quarantined": 20}]
    assert sum(1 for e, _ in seen if e == "replay.progress") == 20
