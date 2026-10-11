from fastapi import APIRouter
from pydantic import BaseModel

from app.aiparser.drafts import DraftError
from app.aiparser.sources import DraftUnavailable
from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import Approved, Draft, DraftTest, DraftView, Items, Rejected

router = APIRouter(prefix="/api")


def drafts_call(fn, *a):
    try:
        return fn(*a)
    except DraftError as e:
        raise ApiError(e.status, e.code, e.message)


@router.get("/parsers", response_model=Items)
async def parsers(c: C):
    return {"items": c.repo.parsers()}


class DraftReq(BaseModel):
    group_id: str


@router.post("/parsers/drafts", status_code=201, response_model=Draft)
async def create_draft(req: DraftReq, c: C):
    try:
        return await c.drafts.create(req.group_id)
    except DraftError as e:
        raise ApiError(e.status, e.code, e.message)
    except DraftUnavailable as e:
        raise ApiError(503, "dependency_unavailable", str(e))


@router.get("/parsers/drafts/{draft_id}", response_model=DraftView)
async def get_draft(draft_id: str, c: C):
    return drafts_call(c.drafts.view, draft_id)


@router.post("/parsers/drafts/{draft_id}/test", response_model=DraftTest)
async def test_draft(draft_id: str, c: C):
    return drafts_call(c.drafts.test, draft_id)


class ApproveReq(BaseModel):
    approved_by: str = "analyst@ntro-demo"


@router.post("/parsers/drafts/{draft_id}/approve", response_model=Approved)
async def approve(draft_id: str, req: ApproveReq, c: C):
    return drafts_call(c.drafts.approve, draft_id, req.approved_by)


class RejectReq(BaseModel):
    reason: str


@router.post("/parsers/drafts/{draft_id}/reject", response_model=Rejected)
async def reject(draft_id: str, req: RejectReq, c: C):
    return drafts_call(c.drafts.reject, draft_id, req.reason)
