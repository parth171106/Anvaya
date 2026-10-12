"""One administrator, scoped collector key, and short-lived server-side sessions."""
import argparse
import getpass
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.requests import Request as ASGIRequest

from app.api.errors import ApiError, envelope

COOKIE = "anvaya_session"
SESSION_SECONDS = 8 * 60 * 60
ITERATIONS = 600_000
router = APIRouter(prefix="/api/auth")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def make_credentials(username: str, password: str, key: str) -> dict:
    if not username.strip() or len(username) > 128 or not 12 <= len(password) <= 1024 or len(key) < 32:
        raise ValueError("Use a username, a 12-1024 character password, and a collector key of at least 32 characters")
    salt = secrets.token_hex(16)
    return {"username": username.strip(), "salt": salt, "password_hash": password_hash(password, salt),
            "collector_key_hash": digest(key)}


class Auth:
    def __init__(self, cfg):
        self.enabled = cfg.auth_file is not None
        self.origin = cfg.public_origin
        self.sessions = {}
        self.attempts = deque()
        if cfg.auth_required and not self.enabled:
            raise ValueError("ANVAYA_AUTH_REQUIRED=1 requires ANVAYA_AUTH_FILE")
        if not self.enabled:
            return
        url = urlsplit(self.origin)
        if (url.scheme not in ("http", "https") or not url.hostname or url.path or url.query or url.fragment
                or url.username or url.password
                or (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))):
            raise ValueError("ANVAYA_PUBLIC_ORIGIN must be an HTTPS origin (HTTP is allowed only on localhost)")
        self.secure_cookie = url.scheme == "https"
        # A missing or malformed file prevents startup; never fall back to anonymous access.
        self.credentials = json.loads(cfg.auth_file.read_text(encoding="utf-8"))
        if not isinstance(self.credentials.get("username"), str) or not self.credentials["username"]:
            raise ValueError("Invalid administrator username in auth file")
        for field, size in (("salt", 16), ("password_hash", 32), ("collector_key_hash", 32)):
            if len(bytes.fromhex(self.credentials[field])) != size:
                raise ValueError(f"Invalid {field} in auth file")

    def session(self, token: str) -> bool:
        expires = self.sessions.get(digest(token), 0)
        return expires > time.time()

    def collector(self, authorization: str) -> bool:
        scheme, _, key = authorization.partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(digest(key), self.credentials["collector_key_hash"])

    def login(self, username: str, password: str) -> str:
        now = time.time()
        while self.attempts and self.attempts[0] <= now - 60:
            self.attempts.popleft()
        if len(self.attempts) >= 10:
            raise ApiError(429, "login_rate_limited", "Too many sign-in attempts. Wait one minute and try again.")
        self.attempts.append(now)  # global limit is deliberate for this single-admin server
        valid_password = hmac.compare_digest(password_hash(password, self.credentials["salt"]),
                                             self.credentials["password_hash"])
        if not (hmac.compare_digest(username.encode(), self.credentials["username"].encode()) and valid_password):
            raise ApiError(401, "invalid_credentials", "Incorrect username or password")
        self.sessions = {key: expiry for key, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 128:
            del self.sessions[next(iter(self.sessions))]
        token = secrets.token_urlsafe(32)
        self.sessions[digest(token)] = now + SESSION_SECONDS
        return token


class AuthMiddleware:
    """Pure ASGI middleware keeps the event stream unbuffered."""
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.auth.enabled:
            return await self.app(scope, receive, send)
        request = ASGIRequest(scope)
        path, method = scope["path"], scope["method"]
        protected = path.startswith("/api/") or path in ("/api", "/docs", "/redoc", "/openapi.json")
        if not protected:
            return await self.app(scope, receive, send)
        public = (method, path) in (("GET", "/api/ready"), ("GET", "/api/auth/session"), ("POST", "/api/auth/login"))
        authorization = request.headers.get("authorization", "")
        if authorization:
            # A collector token never grants dashboard, raw-log, export or administrative access.
            if not self.auth.collector(authorization):
                return await envelope(401, "unauthorized", "Invalid collector credentials")(scope, receive, send)
            if (method, path) not in (("POST", "/api/ingest"), ("GET", "/api/health")):
                return await envelope(403, "forbidden", "Collector key only permits ingestion and health checks")(scope, receive, send)
        else:
            if not public and not self.auth.session(request.cookies.get(COOKIE, "")):
                return await envelope(401, "unauthorized", "Sign in to continue")(scope, receive, send)
            if method not in ("GET", "HEAD", "OPTIONS"):
                # Custom header + exact Origin check; protected deployments do not allow cross-origin CORS.
                if (request.headers.get("x-anvaya-request") != "console"
                        or request.headers.get("origin") != self.auth.origin):
                    return await envelope(403, "forbidden", "Same-origin console request required")(scope, receive, send)

        async def no_cache(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)
        await self.app(scope, receive, no_cache)


@router.get("/session")
async def session(request: Request):
    auth = request.app.state.auth
    authenticated = auth.enabled and auth.session(request.cookies.get(COOKIE, ""))
    return {"enabled": auth.enabled, "authenticated": authenticated,
            "username": auth.credentials["username"] if authenticated else None}


@router.post("/login")
async def login(request: Request):
    auth = request.app.state.auth
    if not auth.enabled:
        raise ApiError(409, "auth_disabled", "Authentication is not enabled for this local pilot")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            raise ApiError(413, "payload_too_large", "Login request too large")
    try:
        data = json.loads(body)
        username, password = data["username"], data["password"]
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 128 or len(password) > 1024:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ApiError(422, "validation_error", "Username and password are required") from None
    token = auth.login(username, password)
    auth.sessions.pop(digest(request.cookies.get(COOKIE, "")), None)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=auth.secure_cookie, samesite="strict", path="/")
    return response


@router.post("/logout")
async def logout(request: Request):
    request.app.state.auth.sessions.pop(digest(request.cookies.get(COOKIE, "")), None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


def main():
    parser = argparse.ArgumentParser(description="Create local deployment credentials without printing secrets")
    parser.add_argument("--directory", type=Path, default=Path("secrets"))
    args = parser.parse_args()
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    auth_file, key_file = directory / "auth.json", directory / "collector.key"
    if auth_file.exists() or key_file.exists():
        parser.error("Credential files already exist; use a new directory to rotate credentials")
    username = input("Administrator username: ").strip()
    password = getpass.getpass("Administrator password (at least 12 characters): ")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords do not match")
    key = secrets.token_urlsafe(32)
    credentials = make_credentials(username, password, key)
    for path, content in ((auth_file, json.dumps(credentials)), (key_file, key + "\n")):
        with path.open("x", encoding="utf-8") as file:
            path.chmod(0o600)
            file.write(content)
    print(f"Created {auth_file} and {key_file}. Keep both private; only auth.json belongs on the server.")


if __name__ == "__main__":
    main()
