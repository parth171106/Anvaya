from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.search.nl2sql import Unanswerable
from app.search.templates import SUGGESTIONS
from generator.br01 import build_br01_lines
from generator.formats import at
from tests.conftest import D, ingest_scenario

IST = ZoneInfo("Asia/Kolkata")
Q1, Q2, Q3, Q4 = SUGGESTIONS


@pytest.fixture
def s(c):
    """Scenario loaded, Ollama absent, clock frozen at scenario 10:12:00."""
    ingest_scenario(c)
    c.worker.drain()
    c.llm.url = "http://127.0.0.1:9"  # nothing listens here → ready() is False
    c.search.clock = SimpleNamespace(now_ms=lambda: at(D, 10, 12), label=lambda: "Scenario clock")
    return c


def hhmmss(ms):
    return datetime.fromtimestamp(ms / 1000, IST).strftime("%H:%M:%S")


async def test_q1_17_rows_in_order(s):
    r = await s.search.answer(Q1)
    assert r["engine"] == "template" and r["model"] is None and r["row_count"] == 17
    assert r["columns"] == ["time", "device", "class_name", "src_ip", "src_port", "dst_ip", "dst_port", "action"]
    got = [(hhmmss(t), dev, src_port, dst_port, act) for t, dev, _, _, src_port, _, dst_port, act in r["rows"]]
    assert got == [
        ("10:08:30", "fw01", 51522, 443, "Allowed"), ("10:07:12", "fw01", 40133, 443, "Allowed"),
        ("10:02:35", "ids01", 40130, 3389, None), ("10:02:33", "fw01", 40112, 8080, "Denied"),
        ("10:02:30", "fw01", 40111, 3389, "Denied"), ("10:02:27", "fw01", 40110, 1433, "Denied"),
        ("10:02:24", "fw01", 40109, 445, "Denied"), ("10:02:21", "fw01", 40108, 139, "Denied"),
        ("10:02:20", "ids01", 40115, 445, None), ("10:02:18", "fw01", 40107, 110, "Denied"),
        ("10:02:15", "fw01", 40106, 80, "Denied"), ("10:02:12", "fw01", 40105, 53, "Denied"),
        ("10:02:09", "fw01", 40104, 25, "Denied"), ("10:02:06", "fw01", 40103, 23, "Denied"),
        ("10:02:05", "ids01", 40100, 22, None), ("10:02:03", "fw01", 40102, 22, "Denied"),
        ("10:02:00", "fw01", 40101, 21, "Denied")]
    assert r["clock_caption"] == "now = 10:12:00 IST (Scenario clock)" and r["params"] == {"now_ms": at(D, 10, 12)}


async def test_q2_counts(s):
    r = await s.search.answer(Q2)
    assert r["rows"] == [["198.51.100.9", 40], ["203.0.113.60", 2]]


async def test_q3_12_denied(s):
    r = await s.search.answer(Q3)
    assert r["row_count"] == 12 and {row[5] for row in r["rows"]} == {"Denied"}
    assert [row[4] for row in r["rows"]] == [8080, 3389, 1433, 445, 139, 110, 80, 53, 25, 23, 22, 21]


async def test_q4_zero_then_twenty(s):
    assert (await s.search.answer(Q4))["row_count"] == 0
    for ln in build_br01_lines(at(D, 10, 14, 3)):
        s.ingest(ln.encode(), "http", "127.0.0.1")
    s.worker.drain()
    acme = (s.registry.builtin_dir.parents[1] / "aiparser" / "acme-edge.fallback.yaml").read_text(encoding="utf-8")
    (s.cfg.data_dir / "packs").mkdir(exist_ok=True)
    (s.cfg.data_dir / "packs" / "acme-edge.yaml").write_text(acme, encoding="utf-8")
    s.registry.reload()
    s.replays.start(s.repo.quarantine_raw_ids(s.repo.quarantine_groups()[0]["group_id"]))
    s.worker.drain()
    r = await s.search.answer(Q4)
    assert r["row_count"] == 20 and sorted(row[7] for row in r["rows"]).count("Denied") == 3


async def test_question_variants_and_unanswerable(s):
    assert (await s.search.answer("what did 10.2.4.18 do in the last 60 minutes"))["row_count"] == 17
    assert (await s.search.answer("  How many events did each device send?  "))["rows"][0] == ["fw01", 104]
    with pytest.raises(Unanswerable):
        await s.search.answer("tell me a joke")
    audit = s.repo.con.execute("SELECT COUNT(*) FROM audit_log WHERE action='search.ask'").fetchone()[0]
    assert audit == 2
