"""Outage/replay tests use fixture XML and isolated databases, never data/live."""
import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.main import create_app
from collectors import windows_auth
from tests.test_live_pilot import live_cfg, make_container, xml_fixture


def test_outage_lost_reply_and_server_restart_do_not_duplicate(tmp_path, monkeypatch):
    cfg = live_cfg(tmp_path)
    app = create_app(cfg, container_factory=make_container)
    app.state.c = make_container(cfg)
    checkpoint = tmp_path / "collector.json"
    state = {"last_record_id": 0}
    attempts, waits, raw_ids = [], [], []
    monkeypatch.setattr(windows_auth.time, "sleep", waits.append)

    async def dispatch(request):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            return await api.post("/api/ingest", content=request.content, headers=request.headers)

    def handle(request):
        attempts.append((request.content, request.headers["Idempotency-Key"]))
        assert state["last_record_id"] == 0 and not checkpoint.exists()
        if len(attempts) == 1:
            raise httpx.ConnectError("server offline", request=request)
        if len(attempts) == 3:
            app.state.c = make_container(cfg)  # reopen the persisted database/vault
        response = asyncio.run(dispatch(request))
        assert response.status_code == 202
        raw_ids.append(response.json()["raw_ids"])
        if len(attempts) == 2:
            app.state.c.close_stores()
            raise httpx.ReadTimeout("accepted, but reply was lost", request=request)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    try:
        with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
            assert windows_auth.forward(client, [xml_fixture()], state, checkpoint) == 1
        c = app.state.c
        assert waits == [1, 2] and len(set(attempts)) == 1
        assert raw_ids[0] == raw_ids[1]
        assert c.repo.counts()["raw_total"] == 1 and c.queue.qsize() == 1
        c.worker.drain()
        c.ledger.seal()
        assert c.repo.counts()["normalized_total"] == 1
        assert c.ledger.verify_record(raw_ids[0][0])["ok"]
        assert json.loads(checkpoint.read_text())["last_record_id"] == 42
    finally:
        app.state.c.close_stores()


async def test_ingest_key_conflicts_validation_and_unkeyed_behavior(tmp_path):
    app = create_app(live_cfg(tmp_path), container_factory=make_container)
    app.state.c = c = make_container(live_cfg(tmp_path))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            headers = {"Idempotency-Key": "test:42", "X-Anvaya-Require-Live": "true"}
            original = await api.post("/api/ingest", json={"lines": ["original"]}, headers=headers)
            duplicate = await api.post("/api/ingest", json={"lines": ["original"]}, headers=headers)
            assert duplicate.json()["raw_ids"] == original.json()["raw_ids"]
            assert duplicate.headers["Idempotency-Key"] == "test:42"
            conflict = await api.post("/api/ingest", json={"lines": ["different"]}, headers=headers)
            assert conflict.status_code == 409
            for lines, key in [([], "valid"), (["a", "b"], "valid"), (["a"], ""), (["a"], "x" * 129)]:
                assert (await api.post("/api/ingest", json={"lines": lines},
                                       headers={"Idempotency-Key": key})).status_code == 422
            assert c.repo.counts()["raw_total"] == 1
            # Generic ingestion without a key still preserves repeated log lines as separate records.
            assert (await api.post("/api/ingest", json={"lines": ["original", "original"]})).status_code == 202
            assert c.repo.counts()["raw_total"] == 3
            c.cfg = replace(c.cfg, demo_mode=True)
            rejected = await api.post("/api/ingest", json={"lines": ["real log"]}, headers=headers)
            assert rejected.status_code == 409
            assert c.repo.counts()["raw_total"] == 3
    finally:
        c.close_stores()


def test_retry_backoff_is_capped_and_permanent_errors_stop(monkeypatch):
    waits = []
    codes = iter([503, 429, 502, 503, 503, 503, 503, 200, 403])
    monkeypatch.setattr(windows_auth.time, "sleep", waits.append)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(next(codes))),
                      base_url="http://127.0.0.1") as client:
        assert windows_auth.request_with_retry(client, "GET", "/api/health").status_code == 200
        assert waits == [1, 2, 4, 8, 16, 30, 30]
        with pytest.raises(httpx.HTTPStatusError):
            windows_auth.request_with_retry(client, "GET", "/api/health")
        assert len(waits) == 7


def test_checkpoint_write_failure_does_not_advance_memory(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint.json"
    state = {"last_record_id": 0}
    keys = []

    def handle(request):
        keys.append(request.headers["Idempotency-Key"])
        return httpx.Response(202, json={"accepted": 1}, headers={"Idempotency-Key": keys[-1]})

    def fail_save(*_):
        raise OSError("disk unavailable")

    original_save = windows_auth.save_checkpoint
    monkeypatch.setattr(windows_auth, "save_checkpoint", fail_save)
    with httpx.Client(transport=httpx.MockTransport(handle), base_url="http://127.0.0.1") as client:
        with pytest.raises(OSError):
            windows_auth.forward(client, [xml_fixture()], state, checkpoint)
        assert state["last_record_id"] == 0 and not checkpoint.exists()
        monkeypatch.setattr(windows_auth, "save_checkpoint", original_save)
        assert windows_auth.forward(client, [xml_fixture()], state, checkpoint) == 1
        assert keys[0] == keys[1]


def test_receipt_migration_and_atomic_raw_commit(tmp_path, monkeypatch):
    cfg = live_cfg(tmp_path)
    c = make_container(cfg)
    original = c.ingest(b"existing log", "http", "127.0.0.1")
    c.repo.con.execute("DROP TABLE ingest_receipts")  # simulate an older pilot database
    c.close_stores()
    c = make_container(cfg)
    try:
        assert c.store.read(original.raw_id) == b"existing log"
        original_insert = c.repo.insert_ingest_receipt

        def fail_insert(*_):
            raise RuntimeError("receipt failed")

        monkeypatch.setattr(c.repo, "insert_ingest_receipt", fail_insert)
        with pytest.raises(RuntimeError, match="receipt failed"):
            c.ingest(b"retry me", "http", "127.0.0.1", idempotency_key="retry")
        assert c.repo.counts()["raw_total"] == 1
        assert c.repo.ingest_receipt("retry") is None
        monkeypatch.setattr(c.repo, "insert_ingest_receipt", original_insert)
    finally:
        c.close_stores()


def test_old_server_cannot_silently_acknowledge_without_receipt(tmp_path):
    state = {"last_record_id": 0}
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(202, json={"accepted": 1})),
                      base_url="http://127.0.0.1") as client:
        with pytest.raises(RuntimeError, match="restart the updated pilot"):
            windows_auth.forward(client, [xml_fixture()], state, tmp_path / "checkpoint.json")
    assert state["last_record_id"] == 0
