import json
import asyncio
import time
from dataclasses import replace

import httpx
import pytest

from app.auth import COOKIE, Auth, digest, make_credentials
from app.main import create_app
from app.api.routes_stream import stream
from starlette.requests import Request
from collectors.windows_auth import local_api, main as collector_main, request_with_retry
from tests.test_live_pilot import live_cfg, make_container

PASSWORD = "college-test-password"
KEY = "test-collector-key-" + "k" * 32
ORIGIN = "https://logs.example.test"
CONSOLE = {"Origin": ORIGIN, "X-Anvaya-Request": "console"}


@pytest.fixture
def auth_cfg(tmp_path):
    credentials = tmp_path / "auth.json"
    credentials.write_text(json.dumps(make_credentials("admin", PASSWORD, KEY)), encoding="utf-8")
    return replace(live_cfg(tmp_path), auth_required=True, auth_file=credentials, public_origin=ORIGIN)


@pytest.fixture
async def secured(auth_cfg):
    app = create_app(auth_cfg, container_factory=make_container)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            yield app, client


async def sign_in(client, password=PASSWORD, headers=CONSOLE):
    return await client.post("/api/auth/login", json={"username": "admin", "password": password}, headers=headers)


async def test_anonymous_requests_cannot_read_or_change_logs(secured):
    _, client = secured
    assert (await client.get("/api/ready")).json() == {"status": "ok"}
    assert (await client.get("/api/auth/session")).json() == {"enabled": True, "authenticated": False, "username": None}
    for path in ("/api/stats", "/api/events", "/api/raw/test", "/api/stream", "/api/health", "/docs", "/openapi.json"):
        assert (await client.get(path)).status_code == 401, path
    for path in ("/api/ingest", "/api/export/parquet", "/api/demo/reset", "/api/parsers/drafts"):
        assert (await client.post(path, json={})).status_code == 401, path


async def test_login_cookie_csrf_logout_and_expiry(secured):
    app, client = secured
    assert (await sign_in(client, headers={})).status_code == 403
    assert (await sign_in(client, headers={**CONSOLE, "Origin": "https://evil.test"})).status_code == 403
    assert (await sign_in(client, password="wrong")).status_code == 401
    result = await sign_in(client)
    assert result.status_code == 200
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    assert result.headers["cache-control"] == "no-store"
    token = client.cookies[COOKIE]
    assert (await client.get("/api/auth/session")).json()["username"] == "admin"
    assert (await client.get("/api/stats")).status_code == 200
    assert (await client.post("/api/ledger/verify", json={})).status_code == 403
    assert (await client.post("/api/ledger/verify", json={}, headers=CONSOLE)).status_code == 200
    assert (await client.post("/api/auth/logout", headers=CONSOLE)).status_code == 200
    client.cookies.set(COOKIE, token)
    assert (await client.get("/api/stats")).status_code == 401  # revoked token cannot be reused
    client.cookies.clear()
    await sign_in(client)
    app.state.auth.sessions[digest(client.cookies[COOKIE])] = time.time() - 1
    assert (await client.get("/api/events")).status_code == 401


async def test_collector_key_has_only_ingest_and_health_access(secured):
    app, client = secured
    key = {"Authorization": f"Bearer {KEY}"}
    assert (await client.get("/api/health", headers=key)).status_code == 200
    for path in ("/api/events", "/api/stats", "/api/raw/test", "/api/stream", "/api/auth/session"):
        assert (await client.get(path, headers=key)).status_code == 403
    assert (await client.post("/api/export/parquet", json={}, headers=key)).status_code == 403
    assert (await client.post("/api/ingest", json={"lines": ["test"]},
                              headers={"Authorization": "Bearer invalid"})).status_code == 401
    headers = {**key, "Idempotency-Key": "authenticated-test", "X-Anvaya-Require-Live": "true"}
    result = await client.post("/api/ingest", json={"lines": ["explicit test fixture"]}, headers=headers)
    retry = await client.post("/api/ingest", json={"lines": ["explicit test fixture"]}, headers=headers)
    assert result.status_code == 202 and retry.json()["raw_ids"] == result.json()["raw_ids"]
    assert app.state.c.repo.counts()["raw_total"] == 1


async def test_login_throttle_and_no_cross_origin_cors(secured):
    _, client = secured
    for _ in range(10):
        assert (await sign_in(client, password="wrong")).status_code == 401
    assert (await sign_in(client)).status_code == 429
    response = await client.options("/api/auth/login", headers={"Origin": "https://evil.test",
                                    "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in response.headers


def test_auth_configuration_fails_closed(auth_cfg, tmp_path):
    with pytest.raises(ValueError, match="requires ANVAYA_AUTH_FILE"):
        create_app(replace(auth_cfg, auth_file=None))
    with pytest.raises(FileNotFoundError):
        create_app(replace(auth_cfg, auth_file=tmp_path / "missing.json"))
    for origin in ("http://logs.example.test", "https://logs.example.test/path", "", "https://user:pass@logs.test"):
        with pytest.raises(ValueError, match="HTTPS origin"):
            create_app(replace(auth_cfg, public_origin=origin))
    auth_cfg.auth_file.write_text("{}")
    with pytest.raises(ValueError):
        create_app(auth_cfg)


def test_restart_invalidates_sessions_but_retains_credentials(auth_cfg):
    first = Auth(auth_cfg)
    token = first.login("admin", PASSWORD)
    assert first.session(token)
    second = Auth(auth_cfg)
    assert not second.session(token)
    assert second.collector(f"Bearer {KEY}")
    assert second.session(second.login("admin", PASSWORD))


def test_remote_collector_requires_https_and_key(monkeypatch):
    import argparse
    import sys
    assert local_api("https://logs.example.test/") == "https://logs.example.test"
    for url in ("http://logs.example.test", "https://user:pass@logs.test", "https://logs.test/?token=x"):
        with pytest.raises(argparse.ArgumentTypeError):
            local_api(url)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(SystemExit):
        collector_main(["--api", "https://logs.example.test"])


def test_collector_does_not_follow_redirect_or_retry_invalid_credentials():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://different.example.test/api/ingest"})

    with httpx.Client(base_url=ORIGIN, transport=httpx.MockTransport(handle),
                      headers={"Authorization": f"Bearer {KEY}"}, follow_redirects=False) as client:
        with pytest.raises(httpx.HTTPStatusError):
            request_with_retry(client, "POST", "/api/ingest", json={"lines": ["fixture"]})
    assert len(seen) == 1


async def test_existing_event_stream_stops_after_session_revocation(secured):
    app, client = secured
    await sign_in(client)
    token = client.cookies[COOKIE]
    request = Request({"type": "http", "method": "GET", "path": "/api/stream", "app": app,
                       "headers": [(b"cookie", f"{COOKIE}={token}".encode())]})
    response = await stream(request, app.state.c)
    iterator = response.body_iterator
    try:
        assert "retry:" in await anext(iterator)
        app.state.c.bus.publish("test", {"fixture": "before logout"})
        assert "before logout" in await asyncio.wait_for(anext(iterator), 2)
        await client.post("/api/auth/logout", headers=CONSOLE)
        app.state.c.bus.publish("test", {"fixture": "after logout"})
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(iterator), 2)
        assert not app.state.c.bus.subscribers
    finally:
        await iterator.aclose()


def test_certificate_failure_stops_instead_of_disabling_verification():
    import ssl
    attempts = []

    def handle(request):
        attempts.append(request)
        try:
            raise ssl.SSLCertVerificationError("untrusted certificate")
        except ssl.SSLCertVerificationError as exc:
            raise httpx.ConnectError("certificate rejected", request=request) from exc

    with httpx.Client(base_url=ORIGIN, transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RuntimeError, match="TLS certificate verification failed"):
            request_with_retry(client, "GET", "/api/health")
    assert len(attempts) == 1
