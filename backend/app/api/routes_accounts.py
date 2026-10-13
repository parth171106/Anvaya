import io
import json
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictStr, ValidationError

from app.api.errors import ApiError

router = APIRouter(prefix="/api")


def accounts(request):
    store = request.app.state.auth.accounts
    if store is None:
        raise ApiError(404, "not_found", "Private accounts are not enabled on this server")
    return store


def owner(request):
    store = accounts(request)
    if request.state.principal["role"] != "admin":
        raise ApiError(403, "forbidden", "Only the server owner can manage invitations and accounts")
    return store


class Registration(BaseModel):
    invite: StrictStr = Field(default="", max_length=128)
    username: StrictStr = Field(max_length=64)
    password: StrictStr = Field(max_length=1024)
    terms_version: StrictStr = Field(max_length=32)


@router.post("/auth/register", status_code=201)
async def register(request: Request):
    store = accounts(request)
    now = time.time()
    attempts = request.app.state.auth.signup_attempts
    while attempts and attempts[0] <= now - 60:
        attempts.popleft()
    if len(attempts) >= 5:
        raise ApiError(429, "signup_rate_limited", "Too many signup attempts. Wait one minute and try again.")
    attempts.append(now)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 8192:
            raise ApiError(413, "payload_too_large", "Registration request too large")
    try:
        data = Registration.model_validate(json.loads(body))
    except (ValueError, ValidationError):
        raise ApiError(422, "validation_error", "Provide a username, password and accepted terms version") from None
    # Invalid invitations are rejected before costly password hashing.
    account_id = store.register(data.invite, data.username, data.password, data.terms_version)
    return {"ok": True, "account_id": account_id,
            "recovery_code": request.app.state.auth.recovery.issue_code(account_id)}


class Acceptance(BaseModel):
    terms_version: StrictStr = Field(max_length=32)


@router.post("/auth/accept-terms")
async def accept(request: Request, data: Acceptance):
    accounts(request).accept(request.state.principal["id"], data.terms_version)
    return {"ok": True}


@router.get("/account")
async def profile(request: Request):
    store = accounts(request)
    user = store.by_id(request.state.principal["id"])
    return {"username": user["username"], "role": user["role"], "account_id": user["id"],
            "has_collector_key": bool(user["collector_key_hash"]), "terms_version": user["terms_version"],
            "accepted_at": user["accepted_at"], "origin": request.app.state.auth.origin,
            "raw_limit_bytes": request.app.state.c.cfg.workspace_raw_limit,
            **request.app.state.auth.recovery.profile(user['id'])}


@router.post("/account/collector-key")
async def rotate(request: Request):
    key = accounts(request).rotate_key(request.state.principal["id"])
    return {"key": key}  # plaintext is returned once, never persisted on the server


@router.get("/admin/accounts")
async def members(request: Request):
    store = owner(request)
    pending = [dict(r) for r in store.con.execute("""SELECT token_hash AS id,expires_at FROM invites
        WHERE revoked=0 AND used_by IS NULL AND expires_at>? ORDER BY created_at DESC""", (time.time(),))]
    return {"items": store.list(), "invitations": pending, "limit": store.limit}


@router.post("/admin/invites", status_code=201)
async def invite(request: Request):
    result = owner(request).invite()
    # Fragment is not sent to web servers or as a Referer header.
    return {"url": request.app.state.auth.origin + "/join#invite=" + result["token"],
            "expires_at": result["expires_at"]}


@router.post("/admin/invites/{invite_id}/revoke")
async def revoke(request: Request, invite_id: str):
    store = owner(request)
    with store.con:
        store.con.execute("UPDATE invites SET revoked=1 WHERE token_hash=? AND used_by IS NULL", (invite_id,))
    return {"ok": True}


@router.post("/admin/accounts/{account_id}/disable")
async def disable(request: Request, account_id: str):
    owner(request).disable(account_id)
    return {"ok": True}


@router.get("/account/collector-download")
async def collector_download(request: Request):
    accounts(request)
    parents = Path(__file__).resolve().parents
    source = next((base / "collectors" for base in (parents[2], parents[3])
                   if (base / "collectors").is_dir()), None)
    if source is None:
        raise ApiError(503, "collector_unavailable", "Collector files are missing from this server build")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("windows_auth.py", "read-windows-auth.ps1", "__init__.py"):
            archive.writestr("collectors/" + name, (source / name).read_bytes())
        archive.writestr("endpoint.txt", request.app.state.auth.origin)
        archive.writestr("start.ps1", '''$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11 or newer with the Python launcher first.' }
    & ./.venv/Scripts/python.exe -m pip install 'httpx==0.28.1'
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the collector dependency.' }
}
if (!(Test-Path -LiteralPath 'collector.key')) { throw 'Download your collector key from Account and place collector.key in this folder.' }
$api = (Get-Content -LiteralPath endpoint.txt -Raw).Trim()
& ./.venv/Scripts/python.exe -m collectors.windows_auth --api $api --api-key-file collector.key --checkpoint data/checkpoint.json
exit $LASTEXITCODE
''')
        archive.writestr("README.txt", """ANVAYA Windows collector
1. Install Python 3.11 or newer from python.org, including the Python launcher.
2. Extract this ZIP into a private folder on the Windows computer you are authorized to monitor.
3. On ANVAYA's Account page, generate a collector key and save collector.key in this folder.
4. Open PowerShell as Administrator. Change directory to this folder, then run:
   powershell -NoProfile -ExecutionPolicy Bypass -File .\\start.ps1
Keep the window open. Ctrl+C stops collection.

The collector sends Windows Security sign-in events 4624/4625 (initially the last
15 minutes, then new events), including full XML, usernames, computer names and
IP addresses, to your ANVAYA workspace. Get the necessary permission before use.
Read the Terms and Privacy Notice on the server. Do not share collector.key.
Rotating your key in Account immediately invalidates the previous key.
Use a separate extracted folder and checkpoint for each account/computer.
This ZIP contains source code only; it does not contain a password, API key or logs.
""")
    return Response(output.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="anvaya-windows-collector.zip"'})
