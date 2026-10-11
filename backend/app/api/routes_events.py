import json

from fastapi import APIRouter, Query

from app.api.deps import C
from app.api.errors import not_found
from app.api.schemas import EventDetail, EventPage
from app.core.models import EventFilter

router = APIRouter(prefix="/api")


@router.get("/events", response_model=EventPage)
async def list_events(c: C, limit: int = Query(50, ge=1, le=200), before_seq: int | None = None,
                      device: str | None = None, format: str | None = None, class_uid: int | None = None,
                      q: str | None = None):
    items, nxt = c.repo.list_events(EventFilter(limit=limit, before_seq=before_seq, device=device, format=format,
                                                class_uid=class_uid, q=q))
    return {"items": items, "next_before_seq": nxt}


@router.get("/events/{event_id}", response_model=EventDetail)
async def get_event(event_id: str, c: C):
    ev = c.repo.get_event(event_id)
    if ev is None:
        raise not_found("Event")
    rec = c.repo.get_raw(ev.raw_id)
    raw = {"raw_id": rec.raw_id, "seq": rec.seq, "size": rec.size, "encoding": rec.meta.encoding,
           "flags": rec.meta.flags, "transport": rec.meta.transport, "peer_ip": rec.meta.peer_ip,
           "received_at": rec.received_at, "raw_sha256": rec.raw_sha256, "batch_id": rec.batch_id,
           "text": c.store.read(rec.raw_id).decode("utf-8", "replace")}  # what the vault holds now (shows tamper)
    return {"event_id": ev.event_id, "raw": raw, "ocsf": ev.ocsf, "anvaya": json.loads(ev.anvaya.model_dump_json())}
