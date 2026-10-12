import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.errors import ApiError
from app.api.deps import C
from app.core.container import IdempotencyConflict

MAX_BODY = 8 * 1024 * 1024
router = APIRouter()


def split_body(body: bytes, content_type: str) -> list[bytes]:
    if content_type.startswith("application/json"):
        try:
            lines = json.loads(body)["lines"]
            assert isinstance(lines, list) and all(isinstance(x, str) for x in lines)
        except Exception:
            raise ApiError(422, "validation_error", 'Expected {"lines": ["..."]}')
        return [x.encode("utf-8") for x in lines]
    # text/plain: one event per line; the \n (and a CRLF's \r) is framing, not record content.
    return [ln[:-1] if ln.endswith(b"\r") else ln for ln in body.split(b"\n") if ln not in (b"", b"\r")]


@router.post("/api/ingest", status_code=202)
async def ingest_route(request: Request, c: C):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise ApiError(413, "payload_too_large", "Ingest body is larger than 8 MiB")
    body = bytes(body)
    ctype = request.headers.get("content-type", "text/plain")
    if not (ctype.startswith("text/plain") or ctype.startswith("application/json")):
        raise ApiError(400, "bad_request", "Use text/plain or application/json")
    if request.headers.get("x-anvaya-require-live") == "true" and c.cfg.demo_mode:
        raise ApiError(409, "live_mode_required", "Collector requires a live-mode API")
    peer = request.client.host if request.client else "127.0.0.1"
    lines = split_body(body, ctype)
    if c.cfg.multi_user and (len(lines) > 500 or any(len(line) > 256 * 1024 for line in lines)):
        raise ApiError(413, "payload_too_large", "Send up to 500 logs per request, each no larger than 256 KiB")
    key = request.headers.get("idempotency-key")
    if key is not None and (len(lines) != 1 or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key)):
        raise ApiError(422, "validation_error", "Idempotency-Key requires one log and 1-128 letters, digits, . _ : or -")
    if c.cfg.multi_user and not (key and c.repo.ingest_receipt(key)):
        count, used = c.repo.con.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM raw_events").fetchone()
        if used + sum(map(len, lines)) > c.cfg.workspace_raw_limit or count + len(lines) > 50_000:
            raise ApiError(413, "workspace_full", "This workspace has reached its pilot log storage limit. Contact the operator.")
    try:
        recs = [c.ingest(line, "http", peer, idempotency_key=key) for line in lines]
    except IdempotencyConflict as exc:
        raise ApiError(409, "idempotency_conflict", str(exc)) from exc
    return JSONResponse({"accepted": len(recs), "raw_ids": [r.raw_id for r in recs],
                         "flagged": sum(1 for r in recs if r.meta.flags)}, status_code=202,
                        headers={"Idempotency-Key": key} if key is not None else None)
