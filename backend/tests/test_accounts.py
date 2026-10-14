"""Synthetic accounts/logs exercise isolation, upgrade compatibility and enrollment."""
import asyncio
import io
import json
import zipfile
from dataclasses import replace
from urllib.parse import urlsplit

import httpx
import pytest
from starlette.requests import Request

from app.accounts import TERMS_VERSION
from app.auth import Auth, COOKIE, digest, make_credentials
from app.api.routes_stream import stream
from app.main import create_app
from tests.test_auth import ORIGIN, CONSOLE, PASSWORD, KEY, sign_in
from tests.test_live_pilot import live_cfg, make_container, xml_fixture
from collectors.windows_auth import event_payload


@pytest.fixture
def multi_cfg(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(make_credentials("admin", PASSWORD, KEY)))
    return replace(live_cfg(tmp_path), auth_file=path, auth_required=True, public_origin=ORIGIN, multi_user=True)


@pytest.fixture
async def multi(multi_cfg):
    app = create_app(multi_cfg, container_factory=make_container)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            yield app, client


async def accept_owner(client):
    assert (await sign_in(client)).status_code == 200
    assert (await client.post("/api/auth/accept-terms", json={"terms_version": TERMS_VERSION}, headers=CONSOLE)).status_code == 200


async def test_ai_context_and_evidence_are_private_to_workspace(multi, monkeypatch):
    from unittest.mock import AsyncMock
    app, owner = multi
    assert (await owner.get("/api/ai/status")).status_code == 401
    await accept_owner(owner)
    alice, aid, _ = await enroll(app, owner, "alice-ai")
    bob, bid, _ = await enroll(app, owner, "bob-ai")
    try:
        a, b = app.state.workspaces.get(aid), app.state.workspaces.get(bid)
        for container in (a, b):
            container.cfg = replace(container.cfg, ai_evidence_enabled=True)
            monkeypatch.setattr(container.assistant.provider, "configured", lambda: True)
            container.assistant.provider.complete = AsyncMock(return_value={"sql": "SELECT time FROM events"})
        key = a.assistant.remember({"question": "alice only", "sql": "SELECT title FROM events", "params": {},
                                    "columns": ["title"], "rows": [["Alice private data"]]})["query_id"]
        for path, body in (
            ("/api/ai/preview", {"kind": "search", "target": key}),
            ("/api/ai/explain", {"kind": "search", "target": key, "consent": True}),
            ("/api/search", {"question": "follow up", "use_ai": True, "consent": True, "previous_id": key}),
        ):
            res = await bob.post(path, json=body, headers=CONSOLE)
            assert res.status_code == 404
            assert "Alice private data" not in res.text
        b.assistant.provider.complete.assert_not_called()
        preview = await alice.post("/api/ai/preview", json={"kind": "search", "target": key}, headers=CONSOLE)
        assert preview.status_code == 200 and "Alice private data" in preview.text
        denied = await alice.post("/api/ai/explain", json={"kind": "search", "target": key}, headers=CONSOLE)
        assert denied.status_code == 422
        assert (await alice.post("/api/ai/preview", json={"kind": "search", "target": key})).status_code == 403
        a.assistant.provider.complete.assert_not_called()
    finally:
        await alice.aclose()
        await bob.aclose()


async def enroll(app, owner, name):
    inv = await owner.post("/api/admin/invites", headers=CONSOLE)
    assert inv.status_code == 201
    invite = urlsplit(inv.json()["url"]).fragment.removeprefix("invite=")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN)
    result = await client.post("/api/auth/register", json={"invite": invite, "username": name,
                               "password": PASSWORD, "terms_version": TERMS_VERSION}, headers=CONSOLE)
    assert result.status_code == 201, result.text
    assert (await client.post("/api/auth/login", json={"username": name, "password": PASSWORD}, headers=CONSOLE)).status_code == 200
    return client, result.json()["account_id"], invite


async def test_invitation_terms_privileges_and_public_notices(multi):
    app, owner = multi
    assert (await owner.get("/api/legal")).json()["version"] == TERMS_VERSION
    assert (await owner.post("/api/admin/invites", headers=CONSOLE)).status_code == 401
    assert (await sign_in(owner)).status_code == 200
    assert (await owner.get("/api/stats")).json()["error"]["code"] == "terms_required"
    assert (await owner.post("/api/auth/accept-terms", json={"terms_version": "old"}, headers=CONSOLE)).status_code == 422
    await owner.post("/api/auth/accept-terms", json={"terms_version": TERMS_VERSION}, headers=CONSOLE)
    member, account_id, used_invite = await enroll(app, owner, "alice")
    try:
        assert (await member.get("/api/auth/session")).json()["role"] == "member"
        for path in ("/api/admin/invites", f"/api/admin/accounts/{account_id}/disable"):
            assert (await member.post(path, headers=CONSOLE)).status_code == 403
        assert (await member.get("/api/admin/accounts")).status_code == 403
        assert (await member.post("/api/auth/register", json={"invite": used_invite, "username": "another",
            "password": PASSWORD, "terms_version": TERMS_VERSION}, headers=CONSOLE)).status_code == 400
        assert app.state.auth.accounts.con.execute("SELECT COUNT(*) FROM acceptances WHERE account_id=?", (account_id,)).fetchone()[0] == 1
        assert (await member.post("/api/account/collector-key", headers={})).status_code == 403
        archive = await member.get("/api/account/collector-download")
        assert archive.status_code == 200
        assert archive.headers["cache-control"] == "no-store"
        with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
            assert "collector.key" not in z.namelist()
            assert z.read("endpoint.txt").decode() == ORIGIN
            assert b"--api-key-file collector.key" in z.read("start.ps1")
    finally:
        await member.aclose()


async def test_two_workspaces_cannot_read_raw_search_export_or_stream_each_other(multi):
    app, owner = multi
    await accept_owner(owner)
    alice, alice_id, _ = await enroll(app, owner, "alice")
    bob, bob_id, _ = await enroll(app, owner, "bob")
    try:
        keys = [(await client.post("/api/account/collector-key", headers=CONSOLE)).json()["key"] for client in (alice, bob)]
        raw_ids = []
        for client, key, marker in zip((alice, bob), keys, ("ALICE-PRIVATE", "BOB-PRIVATE")):
            payload = event_payload(xml_fixture().replace("LAB-LAPTOP", marker))
            result = await client.post("/api/ingest", json={"lines": [json.dumps(payload)]},
                headers={"Authorization": f"Bearer {key}", "Idempotency-Key": "same-key-different-workspace"})
            assert result.status_code == 202
            raw_ids.extend(result.json()["raw_ids"])
        for c in app.state.workspaces.containers.values():
            c.worker.drain()
        assert (await owner.get("/api/stats")).json()["raw_total"] == 0
        for client, own_id, other_id, marker, other in ((alice, raw_ids[0], raw_ids[1], "ALICE-PRIVATE", "BOB-PRIVATE"),
                                                      (bob, raw_ids[1], raw_ids[0], "BOB-PRIVATE", "ALICE-PRIVATE")):
            assert (await client.get(f"/api/raw/{own_id}")).status_code == 200
            assert (await client.get(f"/api/raw/{other_id}")).status_code == 404
            for path in ("/api/events", "/api/sources", "/api/incidents", "/api/quarantine", "/api/ledger/batches", "/api/delivery/status"):
                result = await client.get(path)
                assert result.status_code == 200, path
                assert other not in result.text
            assert marker in (await client.get("/api/events")).text
            result = await client.post("/api/search", json={"question": "show recent events"}, headers=CONSOLE)
            assert result.status_code == 200 and result.json()["row_count"] == 1
            assert other not in result.text
            suggestions = (await client.get("/api/search/suggestions")).json()["items"]
            assert any(marker in q for q in suggestions) and all(other not in q for q in suggestions)
            result = await client.post("/api/export/parquet", json={}, headers=CONSOLE)
            assert result.status_code == 200
            assert (await client.get("/api/stats", headers={"X-Workspace-ID": "owner"})).json()["raw_total"] == 1
        a, b = app.state.workspaces.get(alice_id), app.state.workspaces.get(bob_id)
        assert a.cfg.data_dir != b.cfg.data_dir and a.bus is not b.bus
        q, _ = a.bus.subscribe(None)
        b.bus.publish("test", {"secret": "bob"})
        assert q.empty()
        a.bus.unsubscribe(q)
        assert a.keys != b.keys
        assert (await alice.get("/api/events", headers={"Authorization": f"Bearer {keys[0]}"})).status_code == 403
    finally:
        await alice.aclose(); await bob.aclose()


async def test_rotation_disable_and_revocation_close_sessions_and_stream(multi):
    app, owner = multi
    await accept_owner(owner)
    member, account_id, _ = await enroll(app, owner, "alice")
    try:
        old = (await member.post("/api/account/collector-key", headers=CONSOLE)).json()["key"]
        new = (await member.post("/api/account/collector-key", headers=CONSOLE)).json()["key"]
        assert not app.state.auth.collector(f"Bearer {old}")
        assert app.state.auth.collector(f"Bearer {new}")
        c = app.state.workspaces.get(account_id)
        request = Request({"type": "http", "method": "GET", "path": "/api/stream", "app": app,
            "headers": [(b"cookie", f"{COOKIE}={member.cookies[COOKIE]}".encode())]})
        response = await stream(request, c)
        iterator = response.body_iterator
        assert "retry:" in await anext(iterator)
        assert (await owner.post(f"/api/admin/accounts/{account_id}/disable", headers=CONSOLE)).status_code == 200
        c.bus.publish("test", {"after": "disable"})
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(iterator), 2)
        assert (await member.get("/api/stats")).status_code == 401
        assert (await member.get("/api/health", headers={"Authorization": f"Bearer {new}"})).status_code == 401
        assert (await owner.post("/api/admin/accounts/owner/disable", headers=CONSOLE)).status_code == 409
    finally:
        await member.aclose()


def test_account_persistence_bootstrap_does_not_restore_rotated_key(multi_cfg):
    auth = Auth(multi_cfg)
    auth.accounts.accept("owner", TERMS_VERSION)
    invite = auth.accounts.invite()["token"]
    account_id = auth.accounts.register(invite, "alice", PASSWORD, TERMS_VERSION)
    key = auth.accounts.rotate_key(account_id)
    owner_key = auth.accounts.rotate_key("owner")
    auth.accounts.close()
    auth = Auth(multi_cfg)
    try:
        assert auth.session(auth.login("alice", PASSWORD))
        assert auth.collector(f"Bearer {key}")
        assert auth.collector(f"Bearer {owner_key}")
        assert not auth.collector(f"Bearer {KEY}")
        assert auth.accounts.by_id(account_id)["terms_version"] == TERMS_VERSION
    finally:
        auth.accounts.close()


async def test_public_signup_requires_terms_and_enforces_capacity_and_throttle(multi):
    app, client = multi
    store = app.state.auth.accounts
    store.public_signup = True
    assert (await client.get("/api/auth/session")).json()["public_signup"] is True
    body = {"username": "public-user", "password": PASSWORD, "terms_version": TERMS_VERSION}
    assert (await client.post("/api/auth/register", json=body)).status_code == 403
    assert (await client.post("/api/auth/register", json={**body, "terms_version": ""}, headers=CONSOLE)).status_code == 422
    response = await client.post("/api/auth/register", json=body, headers=CONSOLE)
    assert response.status_code == 201
    assert store.by_id(response.json()["account_id"])["role"] == "member"
    assert (await client.post("/api/auth/register", json={**body, "username": "PUBLIC-USER"}, headers=CONSOLE)).status_code == 409
    store.limit = 2
    assert (await client.post("/api/auth/register", json={**body, "username": "overflow"}, headers=CONSOLE)).status_code == 409
    await client.post("/api/auth/register", json=body, headers=CONSOLE)
    assert (await client.post("/api/auth/register", json=body, headers=CONSOLE)).status_code == 429


async def test_invalid_expired_revoked_invites_limits_and_quota(multi):
    app, owner = multi
    await accept_owner(owner)
    store = app.state.auth.accounts
    for mode in ("expired", "revoked"):
        inv = store.invite()
        with store.con:
            store.con.execute("UPDATE invites SET expires_at=0 WHERE token_hash=?" if mode == "expired" else
                              "UPDATE invites SET revoked=1 WHERE token_hash=?", (digest(inv["token"]),))
        response = await owner.post("/api/auth/register", json={"invite": inv["token"], "username": "tester", "password": PASSWORD, "terms_version": TERMS_VERSION}, headers=CONSOLE)
        assert response.status_code == 400
    member, account_id, _ = await enroll(app, owner, "tester")
    try:
        c = app.state.workspaces.get(account_id)
        c.cfg = replace(c.cfg, workspace_raw_limit=5)
        headers = {**CONSOLE, "Idempotency-Key": "quota-fixture"}
        assert (await member.post("/api/ingest", json={"lines": ["12345"]}, headers=headers)).status_code == 202
        assert (await member.post("/api/ingest", json={"lines": ["12345"]}, headers=headers)).status_code == 202
        assert (await member.post("/api/ingest", json={"lines": ["x"]}, headers=CONSOLE)).status_code == 413
        assert (await member.post("/api/auth/register", content=b"x" * 8193, headers=CONSOLE)).status_code == 413
        store.limit = 2
        assert (await owner.post("/api/admin/invites", headers=CONSOLE)).status_code == 409
    finally:
        await member.aclose()


async def test_ssh_incident_and_evidence_are_private(multi):
    from tests.test_correlation import ssh_failures
    app, owner = multi
    await accept_owner(owner)
    alice, aid, _ = await enroll(app, owner, 'alice')
    bob, _, _ = await enroll(app, owner, 'bob')
    try:
        container = app.state.workspaces.get(aid)
        ssh_failures(container, 10)
        container.ledger.seal()
        items = (await alice.get('/api/incidents')).json()['items']
        assert len(items) == 1
        iid = items[0]['incident_id']
        detail = (await alice.get('/api/incidents/' + iid)).json()
        assert 'distinct SSH connections' in detail['explanation'] and len(detail['events']) == 10
        assert (await bob.get('/api/incidents')).json()['items'] == []
        assert (await bob.get('/api/incidents/' + iid)).status_code == 404
        eid = detail['events'][0]['event_id']
        evidence = (await alice.get('/api/events/' + eid)).json()
        raw_id = evidence['raw']['raw_id']
        assert evidence['anvaya']['roundtrip']['ok']
        assert (await bob.get('/api/events/' + eid)).status_code == 404
        assert (await bob.get('/api/raw/' + raw_id)).status_code == 404
        verification = await alice.post('/api/ledger/verify/' + raw_id, headers=CONSOLE)
        assert verification.status_code == 200 and verification.json()['ok'] is True
        assert (await bob.post('/api/ledger/verify/' + raw_id, headers=CONSOLE)).status_code == 404
    finally:
        await alice.aclose()
        await bob.aclose()
