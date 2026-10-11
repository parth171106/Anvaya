from fastapi import APIRouter

from app.api.deps import C
from app.api.errors import not_found
from app.api.schemas import IncidentDetail, Items

router = APIRouter(prefix="/api")


@router.get("/incidents", response_model=Items)
async def incidents(c: C):
    return {"items": [c.correlator.summary(i["incident_id"]) for i in c.repo.incidents()]}


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def incident(incident_id: str, c: C):
    d = c.correlator.detail(incident_id)
    if d is None:
        raise not_found("Incident")
    # Additive to TRD API 21: the linked events' summaries, so the timeline's evidence chips need no extra calls.
    return {**d, "events": c.repo.summaries([i for s in d["stages_detail"] for i in s["event_ids"]])}
