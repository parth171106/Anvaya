"""Each TRD.md §16 endpoint returns its documented shape and errors. Runs the real lifespan (UDP listener, worker,
sealer, monitors) in DEMO_MODE against a temp data dir."""
import asyncio
import json
import socket
import time

import httpx
import pytest

from app.api.routes_stream import frame
from app.core import config
from app.core.clock import wall_ms
from app.core.container import Container
from app.main import create_app
from generator.formats import at
from tests.conftest import ocsf_impl


def free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_cfg(tmp_path, demo=True):
    return config.load({"ANVAYA_DEMO_MODE": "1" if demo else "0", "ANVAYA_DATA_DIR": str(tmp_path / "data"),
                        "ANVAYA_SYSLOG_UDP_PORT": str(free_udp_port()), "OLLAMA_URL": "http://127.0.0.1:9"})


def factory(cfg):
    enums, validate = ocsf_impl()
    return Container(cfg, enums=enums, validate=validate)


@pytest.fixture
async def api(tmp_path):
    app = create_app(make_cfg(tmp_path), container_factory=factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            client.c = app.state.c
            yield client


def err(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and "message" in body["error"]


async def wait_for(pred, timeout=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if await pred():
            return True
        await asyncio.sleep(0.1)
    return False


async def run_scenario_fast(api):
    """Start the real generator over UDP, then jump the scenario clock so every scripted line is due now."""
    r = await api.post("/api/demo/scenario/start", json={"speed": 40})
    assert r.status_code == 202 and r.json() == {"phase": "scripted", "speed": 40, "scripted_lines": 207}
    clk = api.c.clock
    clk.anchor_wall, clk.anchor_scn = wall_ms(), clk.steady_ms - 500

    async def all_in():
        s = (await api.get("/api/stats")).json()
        return s["raw_total"] >= 207 and s["normalized_total"] >= 207
    assert await wait_for(all_in)


async def test_health_and_stats(api):
    h = (await api.get("/api/health")).json()
    assert h["demo_mode"] is True and h["version"] == "1.0.0"
    assert set(h["components"]) >= {"vault", "database", "ledger", "witnesses", "llm", "network"}
    assert h["components"]["llm"]["status"] == "fallback" and h["components"]["witnesses"]["ok_count"] == 2
    s = (await api.get("/api/stats")).json()
    assert s["raw_total"] == 0 and s["parse_coverage_pct"] is None
    b = s["last_bench"]  # null until `make bench` has written docs/BENCHMARKS.md, then its latest measured row
    assert b is None or (b["eps"] > 0 and b["machine"] and b["measured_at"] > 0)
    assert s["clock"]["label"] == "Scenario clock" and s["clock"]["display_tz"] == "Asia/Kolkata"


async def test_scenario_end_to_end_over_udp(api):
    seen = []
    api.c.publish = lambda e, d: (seen.append(e), api.c.bus.publish(e, d))
    err(await api.post("/api/demo/tamper"), 409, "conflict")
    await run_scenario_fast(api)
    err(await api.post("/api/demo/scenario/start"), 409, "conflict")

    ev = await api.get("/api/events", params={"limit": 5})
    assert ev.status_code == 200 and len(ev.json()["items"]) == 5 and ev.json()["next_before_seq"] is not None
    detail = (await api.get("/api/events/e-" + api.c.ledger.tamper_target().raw_id[2:])).json()
    assert detail["raw"]["seq"] == 164 and detail["ocsf"]["dst_endpoint"]["ip"] == "10.2.4.18"
    err(await api.get("/api/events/e-000000000000"), 404, "not_found")
    err(await api.get("/api/raw/r-000000000000"), 404, "not_found")
    raw = await api.get(f"/api/raw/{detail['raw']['raw_id']}")
    assert raw.headers["x-raw-seq"] == "164" and len(raw.content) == 174

    inc = (await api.get("/api/incidents")).json()["items"]
    assert [(i["incident_id"], i["risk"], i["event_count"]) for i in inc] == [("inc-0001", 95, 56)]
    d = (await api.get("/api/incidents/inc-0001")).json()
    assert d["risk_breakdown"] == {"stages": 75, "devices": 10, "ordered": 10} and len(d["stages_detail"]) == 3
    err(await api.get("/api/incidents/inc-9999"), 404, "not_found")
    assert "incident.opened" in seen and "incident.updated" in seen and "event.normalized" in seen

    b = (await api.get("/api/ledger/batches")).json()
    assert b["items"][0]["batch_id"] >= 12 and len(b["primary_key_fingerprint"]) == 16
    assert all(w["cosigned"] for w in b["items"][-1]["witnesses"])
    v = (await api.post("/api/ledger/verify")).json()
    assert v["verdict"] == "verified"
    w = (await api.get("/api/witnesses")).json()["items"]
    assert [x["label"] for x in w] == ["NTRO witness · simulated, local", "CERT-In witness · simulated, local"]

    t = (await api.post("/api/demo/tamper")).json()
    assert t == {"raw_id": detail["raw"]["raw_id"], "offset": 153, "from": "8", "to": "9", "field": "dst_endpoint.ip"}
    assert (await api.post("/api/demo/tamper")).json() == t   # idempotent
    v = (await api.post("/api/ledger/verify")).json()
    assert v["verdict"] == "tampered" and len(v["failed_records"]) == 1
    assert v["failed_records"][0]["first_diff_offset"] == 153
    rv = (await api.post(f"/api/ledger/verify/{t['raw_id']}")).json()
    assert rv["ok"] is False and rv["changed"] == {"from": "8", "to": "9"}
    assert (await api.get(f"/api/events/e-{t['raw_id'][2:]}")).json()["raw"]["text"][145:154] == "10.2.4.19"
    rs = (await api.post("/api/demo/reseal")).json()
    assert rs["resealed_batches"][0] == 11
    v = (await api.post("/api/ledger/verify")).json()
    assert v["verdict"] == "witness_mismatch" and v["witness_status"][0]["mismatched_batches"][0] == 11

    q = (await api.post("/api/search", json={"question": "What did 10.2.4.18 do in the last hour?"})).json()
    assert q["engine"] == "template" and q["row_count"] == 17
    err(await api.post("/api/search", json={"question": "tell me a joke"}), 422, "unanswerable")
    assert len((await api.get("/api/search/suggestions")).json()["items"]) == 4

    src = {s["device"]: s for s in (await api.get("/api/sources")).json()["items"]}
    assert set(src) == {"fw01", "ids01", "vpn01"} and src["fw01"]["format"] == "cisco-asa-syslog"


async def test_unknown_source_flow(api, tmp_path):
    assert (await api.post("/api/demo/inject-unknown")).json() == {"lines": 20}
    err(await api.post("/api/demo/inject-unknown"), 409, "conflict")

    async def quarantined():
        return (await api.get("/api/quarantine")).json()["total"] == 20
    assert await wait_for(quarantined)
    g = (await api.get("/api/quarantine")).json()["groups"][0]
    assert g["shape_label"] == "20 records · 12 pipe-delimited fields starting with EDGE"
    assert g["transport"] == "http" and len(g["sample_lines"]) == 3
    err(await api.post("/api/replay", json={"group_id": "qg-00000000"}), 404, "not_found")
    err(await api.post("/api/replay", json={}), 422, "validation_error")
    err(await api.post("/api/parsers/drafts", json={"group_id": "qg-00000000"}), 404, "not_found")

    from app.aiparser.drafts import DraftService
    from app.aiparser.sources import CachedDraftSource
    from tests.test_parser_drafts import hand_authored_cache
    api.c.drafts = DraftService(api.c, CachedDraftSource(hand_authored_cache(tmp_path)))
    d = await api.post("/api/parsers/drafts", json={"group_id": g["group_id"]})
    assert d.status_code == 201 and d.json()["origin"] == "hand_authored"
    did = d.json()["draft_id"]
    err(await api.post(f"/api/parsers/drafts/{did}/approve", json={}), 409, "not_promotable")
    t = (await api.post(f"/api/parsers/drafts/{did}/test")).json()
    assert t["promotable"] and t["holdout"] == {"passed": 6, "total": 6}
    assert (await api.get(f"/api/parsers/drafts/{did}")).json()["test"]["promotable"] is True
    a = (await api.post(f"/api/parsers/drafts/{did}/approve", json={"approved_by": "analyst@ntro-demo"})).json()
    assert a["parser"]["name"] == "acme-edge" and a["queued"] == 20

    async def replayed():
        return (await api.get("/api/quarantine")).json()["total"] == 0
    assert await wait_for(replayed)
    names = [p["name"] for p in (await api.get("/api/parsers")).json()["items"]]
    assert names == ["suricata-eve", "fortigate-kv", "cisco-asa", "windows-security", "acme-edge"]


async def test_demo_controls_and_reset(api):
    assert (await api.get("/api/demo/state")).json()["phase"] == "idle"
    err(await api.post("/api/demo/speed", json={"speed": 15}), 422, "validation_error")
    assert (await api.post("/api/demo/speed", json={"speed": 10})).json() == {"speed": 10}
    assert (await api.post("/api/demo/silence", json={"device": "fw01", "silent": True})).json() == \
        {"device": "fw01", "silent": True}
    assert (await api.get("/api/demo/state")).json()["silenced"] == ["fw01"]
    await api.post("/api/demo/silence", json={"device": "fw01", "silent": False})
    err(await api.post("/api/demo/reseal"), 409, "conflict")
    await run_scenario_fast(api)
    t0 = time.monotonic()
    r = (await api.post("/api/demo/reset")).json()
    assert r["ok"] is True and time.monotonic() - t0 < 15
    s = (await api.get("/api/stats")).json()
    assert s["raw_total"] == 0 and s["normalized_total"] == 0 and s["open_incidents"] == 0
    st = (await api.get("/api/demo/state")).json()
    assert (st["phase"], st["silenced"], st["tampered"], st["speed"]) == ("idle", [], False, 40)
    await run_scenario_fast(api)  # a second run after reset gives the same deterministic result
    inc = (await api.get("/api/incidents")).json()["items"]
    assert [(i["incident_id"], i["risk"]) for i in inc] == [("inc-0001", 95)]


async def test_demo_routes_403_outside_demo_mode(tmp_path):
    app = create_app(make_cfg(tmp_path, demo=False), container_factory=factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            assert (await client.get("/api/demo/state")).json() == {"demo_mode": False}
            for path in ("reset", "scenario/start", "inject-unknown", "tamper", "reseal"):
                err(await client.post(f"/api/demo/{path}"), 403, "demo_disabled")


async def test_ingest_errors(api):
    err(await api.post("/api/ingest", content=b"x" * (8 * 1024 * 1024 + 1), headers={"content-type": "text/plain"}),
        413, "payload_too_large")
    err(await api.post("/api/ingest", content=b'{"nope":1}', headers={"content-type": "application/json"}),
        422, "validation_error")
    r = await api.post("/api/ingest", content=b"a\nb\x00c", headers={"content-type": "text/plain"})
    assert r.status_code == 202 and r.json()["accepted"] == 2 and r.json()["flagged"] == 1


async def test_sse_bus_replay_and_resync():
    from app.stream.bus import EventBus
    bus = EventBus()
    for i in range(3):
        bus.publish("event.normalized", {"i": i})
    q, backlog = bus.subscribe(1)
    assert [m[0] for m in backlog] == [2, 3]
    assert frame(backlog[0]) == 'id: 2\nevent: event.normalized\ndata: {"i":1}\n\n'
    for i in range(2100):
        bus.publish("x", i)
    assert bus.subscribe(1)[1] is None  # older than the 2,000-message buffer → resync
    assert json.loads(frame((1, "e", {"a": at.__name__}))[len("id: 1\nevent: e\ndata: "):]) == {"a": "at"}
