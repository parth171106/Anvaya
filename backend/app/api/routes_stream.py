import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import C

router = APIRouter(prefix="/api")
PING_S = 15


def frame(msg) -> str:
    i, event, data = msg
    return f"id: {i}\nevent: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/stream")
async def stream(request: Request, c: C):
    last = request.headers.get("last-event-id", "")
    q, backlog = c.bus.subscribe(int(last) if last.isdigit() else None)

    async def gen():
        try:
            yield "retry: 1500\n\n"
            if backlog is None:  # the client is further behind than the replay buffer
                yield "event: resync\ndata: {}\n\n"
            for m in backlog or []:
                yield frame(m)
            while True:
                try:
                    yield frame(await asyncio.wait_for(q.get(), PING_S))
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            c.bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
