import re
import time

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import C
from app.api.errors import ApiError, not_found
from app.api.schemas import Items, Quarantine, ReplayStarted
from app.parsers.shape import DELIMS

router = APIRouter(prefix="/api")
_SIG = re.compile(r"^(?P<first>.*?)(?P<delim>[|,\t; ])x(?P<n>\d+)$")


def shape_label(signature: str, count: int) -> str:
    m = _SIG.match(signature)
    if not m:
        return f"{count} records · shape {signature}"
    return f"{count} records · {m['n']} {DELIMS[m['delim']]}-delimited fields starting with {m['first']}"


@router.get("/sources", response_model=Items)
async def sources(c: C):
    since = int(time.time() * 1000) - 60_000
    rates = dict(c.repo.con.execute("SELECT e.device, COUNT(*) FROM events e JOIN raw_events r USING(raw_id)"
                                    " WHERE r.wall_received_at >= ? GROUP BY e.device", (since,)).fetchall())
    cols = ("device", "vendor", "product", "format", "parser", "first_seen", "last_seen", "events_total",
            "expected_gap_s", "status")
    return {"items": [{**{k: s[k] for k in cols}, "rate_epm": float(rates.get(s["device"], 0)),
                       "silent_for_s": c.silence.silent_for_s(s["device"])} for s in c.repo.sources()]}


@router.get("/quarantine", response_model=Quarantine)
async def quarantine(c: C):
    groups = []
    for g in c.repo.quarantine_groups():
        ids = c.repo.quarantine_raw_ids(g["group_id"])[:3]
        groups.append({**g, "shape_label": shape_label(g["shape_signature"], g["count"]),
                       "sample_lines": [c.store.read(r).decode("utf-8", "replace") for r in ids]})
    return {"total": c.repo.quarantine_total(), "groups": groups}


class ReplayReq(BaseModel):
    group_id: str | None = None
    raw_ids: list[str] | None = None


@router.post("/replay", status_code=202, response_model=ReplayStarted)
async def replay(req: ReplayReq, c: C):
    if req.group_id:
        ids = c.repo.quarantine_raw_ids(req.group_id)
        if not ids:
            raise not_found("Quarantine group")
    elif req.raw_ids:
        ids = req.raw_ids
        if any(c.repo.get_raw(r) is None for r in ids):
            raise not_found("Raw record")
    else:
        raise ApiError(422, "validation_error", "Send group_id or raw_ids")
    rp, n = c.replays.start(ids)
    return {"replay_id": rp, "queued": n}
