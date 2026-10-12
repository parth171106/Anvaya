"""Live-mode regressions; all event XML below is an explicit test fixture, never pilot data."""
import asyncio
import json
import time

import httpx
import pytest

from app.core import config
from app.core.container import Container
from app.main import create_app
from app.pilot import ConsoleFiles
from app.pipeline.worker import normalize
from app.parsers.registry import PackRegistry
from collectors.windows_auth import event_payload, forward, local_api
from tests.conftest import ocsf_impl


def xml_fixture(event_id=4624, ip="-", record_id=42):
    return f'''<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
<System><Provider Name="Microsoft-Windows-Security-Auditing"/><EventID>{event_id}</EventID>
<TimeCreated SystemTime="2026-10-12T00:01:02.1234567Z"/><EventRecordID>{record_id}</EventRecordID>
<Channel>Security</Channel><Computer>LAB-LAPTOP.example</Computer></System>
<EventData><Data Name="TargetUserName">test-आदित्य</Data><Data Name="TargetDomainName">LAB</Data>
<Data Name="IpAddress">{ip}</Data><Data Name="IpPort">51234</Data><Data Name="LogonType">3</Data>
<Data Name="ExtraVendorField">preserve me &amp; this</Data></EventData></Event>'''


def live_cfg(tmp_path):
    return config.load({"ANVAYA_DATA_DIR": str(tmp_path / "live"), "ANVAYA_DEMO_MODE": "0",
                        "ANVAYA_SYSLOG_BIND_HOST": "127.0.0.1", "ANVAYA_SYSLOG_UDP_PORT": "0",
                        "OLLAMA_URL": "http://127.0.0.1:9"})


def make_container(cfg):
    enums, validate = ocsf_impl()
    return Container(cfg, enums=enums, validate=validate)


@pytest.mark.parametrize("event_id,status,ip", [(4624, "Success", "-"), (4625, "Failure", "192.0.2.25"),
                                                (4624, "Success", "::1")])
def test_windows_auth_schema_lineage_and_xml(event_id, status, ip):
    xml = xml_fixture(event_id, ip)
    payload = event_payload(xml)
    data = json.dumps(payload, ensure_ascii=False).encode()
    enums, validate = ocsf_impl()
    out = normalize(data, "r-test", 1, 0, "utf-8", PackRegistry(), enums, validate)
    assert out.reason is None, out.detail
    ev = out.event
    assert ev.ocsf["class_uid"] == 3002 and ev.ocsf["status"] == status
    assert ev.ocsf["user"]["name"] == "test-आदित्य"
    assert ev.anvaya.device == "LAB-LAPTOP.example"
    assert ev.ocsf["unmapped"]["windows_event_xml"] == xml
    assert ev.anvaya.roundtrip.ok and ev.anvaya.roundtrip.dropped == 0
    assert validate(ev.ocsf) is None
    trace = next(t for t in ev.anvaya.lineage if t.path == "user.name")
    a, b = trace.spans[0]
    assert data[a:b].decode() == "test-आदित्य"
    assert ("source_ip" in payload) == (ip != "-")


def test_pending_records_recover_once_and_verify(tmp_path):
    cfg = live_cfg(tmp_path)
    c = make_container(cfg)
    data = json.dumps(event_payload(xml_fixture())).encode()
    rec = c.ingest(data, "http", "127.0.0.1")
    assert c.repo.pending_raw_ids() == [rec.raw_id]
    assert c.repo.con.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
    c.close_stores()  # process stopped after acceptance, before normalization
    for expected_queued in (1, 0):
        c = make_container(cfg)
        try:
            assert c.queue.qsize() == expected_queued
            c.worker.drain()
            if c.ledger.unsealed:
                c.ledger.seal()
            assert c.repo.counts()["normalized_total"] == 1
            assert c.repo.con.execute("SELECT events_total FROM sources").fetchone()[0] == 1
            assert c.store.read(rec.raw_id) == data
            assert c.ledger.verify_record(rec.raw_id)["ok"]
        finally:
            c.close_stores()


def test_demo_live_storage_cannot_be_mixed(tmp_path):
    cfg = config.load({"ANVAYA_DATA_DIR": str(tmp_path / "live"), "ANVAYA_DEMO_MODE": "1"})
    c = make_container(cfg)
    rec = c.ingest(b"demo fixture", "http", "127.0.0.1")
    c.close_stores()
    with pytest.raises(ValueError, match="separate data directory"):
        make_container(live_cfg(tmp_path))
    c = make_container(cfg)
    assert c.store.read(rec.raw_id) == b"demo fixture"
    c.close_stores()


async def test_worker_failure_requeues_uncommitted_batch(tmp_path):
    c = make_container(live_cfg(tmp_path))
    try:
        rec = c.ingest(json.dumps(event_payload(xml_fixture())).encode(), "http", "127.0.0.1")
        original = c.worker.process

        def fail(_):
            raise RuntimeError("temporary database failure")

        c.worker.process = fail
        with pytest.raises(RuntimeError, match="temporary database"):
            await asyncio.wait_for(c.worker.run(), timeout=3)
        assert c.queue.qsize() == 1
        c.worker.process = original
        c.worker.drain()
        assert c.repo.pending_raw_ids() == []
        assert c.repo.get_raw(rec.raw_id) is not None
        assert c.repo.counts()["normalized_total"] == 1
    finally:
        c.close_stores()


async def test_live_api_accepts_and_normalizes_without_simulation(tmp_path):
    app = create_app(live_cfg(tmp_path), container_factory=make_container)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            assert (await api.get("/api/stats")).json()["raw_total"] == 0
            assert (await api.get("/api/demo/state")).json() == {"demo_mode": False}
            for route in ("reset", "scenario/start", "tamper", "reseal"):
                assert (await api.post(f"/api/demo/{route}")).status_code == 403
            payload = json.dumps(event_payload(xml_fixture(4625, "192.0.2.25")))
            r = await api.post("/api/ingest", json={"lines": [payload]})
            assert r.status_code == 202
            for _ in range(40):
                events = (await api.get("/api/events")).json()["items"]
                if events:
                    break
                await asyncio.sleep(0.1)
            assert len(events) == 1 and events[0]["device"] == "LAB-LAPTOP.example"
            assert abs((await api.get("/api/stats")).json()["clock"]["now_ms"] - time.time() * 1000) < 5000
            app.state.c.ledger.seal()
            raw_id = r.json()["raw_ids"][0]
            assert (await api.get(f"/api/raw/{raw_id}")).content == payload.encode()
            assert (await api.post(f"/api/ledger/verify/{raw_id}")).json()["ok"]
            assert "Synthetic" not in (await api.get("/api/reports/retention")).json()["note"]
            assert (await api.get("/api/stats")).json()["last_bench"] is None


def test_collector_checkpoint_only_after_acceptance(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    state = {"last_record_id": 0}
    response_code = 400  # permanent rejection stops; transient failures are covered by recovery tests

    def handle(request):
        return httpx.Response(response_code, json={"accepted": 1},
                              headers={"Idempotency-Key": request.headers["Idempotency-Key"]})

    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
        with pytest.raises(httpx.HTTPStatusError):
            forward(client, [xml_fixture()], state, checkpoint)
        assert not checkpoint.exists() and state["last_record_id"] == 0
        response_code = 202
        assert forward(client, [xml_fixture()], state, checkpoint) == 1
        assert json.loads(checkpoint.read_text())["last_record_id"] == 42
        assert forward(client, [xml_fixture()], state, checkpoint) == 0


def test_collector_rejects_non_auth_and_remote_destination():
    import argparse
    with pytest.raises(ValueError, match="4624 or 4625"):
        event_payload(xml_fixture(9999))
    with pytest.raises(argparse.ArgumentTypeError):
        local_api("http://example.com")


async def test_console_fallback_does_not_hide_api_or_asset_errors(tmp_path):
    from fastapi import FastAPI
    (tmp_path / "index.html").write_text("<h1>Pilot fixture</h1>")
    app = FastAPI()
    app.mount("/", ConsoleFiles(directory=tmp_path, html=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
        assert (await api.get("/overview")).status_code == 200
        assert (await api.get("/api/missing")).status_code == 404
        assert (await api.get("/assets/missing.js")).status_code == 404
