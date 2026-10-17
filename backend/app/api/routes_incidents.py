from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from app.api.deps import C
from app.api.errors import ApiError, not_found
from app.api.schemas import IncidentDetail, Items
from app.delivery.incident_report import render_pdf, snapshot
from app.delivery.response_plan import prepare

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
    return {**d, "events": c.repo.summaries([i for s in d["stages_detail"] for i in s["event_ids"]]),
            "activity": c.repo.incident_activity(incident_id)}


class InvestigationUpdate(BaseModel, extra='forbid'):
    state: Literal['new', 'investigating', 'resolved']
    controlled_test: StrictBool
    version: int = Field(ge=0, strict=True)
    note: str = Field(default='', max_length=5000)
    assessment: Literal['unreviewed', 'expected', 'suspicious'] | None = None


class ReportOptions(BaseModel, extra='forbid'):
    verify: StrictBool = True


class BlockPlanOptions(BaseModel, extra='forbid'):
    device: str = Field(min_length=1, max_length=255)
    minutes: Literal[5, 15]


@router.post('/incidents/{incident_id}/block-plan')
async def block_plan(incident_id: str, body: BlockPlanOptions, request: Request, c: C):
    principal = getattr(request.state, 'principal', None)
    actor = principal['username'] if principal else 'local analyst'
    try:
        return prepare(c, incident_id, body.device, body.minutes, actor)
    except KeyError:
        raise not_found('Incident')
    except ValueError as error:
        raise ApiError(400, 'bad_request', str(error))


@router.post('/incidents/{incident_id}/report')
async def incident_report(incident_id: str, body: ReportOptions, c: C):
    try:
        data = snapshot(c, incident_id, body.verify)
    except KeyError:
        raise not_found('Incident')
    pdf = await run_in_threadpool(render_pdf, data)
    # A fixed attachment name avoids placing user input in response headers.
    return Response(pdf, media_type='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="anvaya-incident-report.pdf"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.post('/incidents/{incident_id}/investigation', response_model=IncidentDetail)
async def update_investigation(incident_id: str, body: InvestigationUpdate, request: Request, c: C):
    principal = getattr(request.state, 'principal', None)
    actor = principal['username'] if principal else 'local analyst'
    try:
        c.repo.update_incident_workflow(incident_id, body.state, body.controlled_test,
                                       body.version, body.note.strip(), actor, body.assessment)
    except KeyError:
        raise not_found('Incident')
    except ValueError as exc:
        raise ApiError(409, 'conflict', str(exc))
    c.publish('incident.updated', c.correlator.summary(incident_id))
    return await incident(incident_id, c)
