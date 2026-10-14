from fastapi import APIRouter
from typing import Literal
from pydantic import BaseModel, Field

from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import Items, SearchResult
from app.search.nl2sql import QueryTimeout, Unanswerable
from app.search.templates import workspace_suggestions

router = APIRouter(prefix="/api")


class SearchReq(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    use_ai: bool = False
    consent: bool = False
    previous_id: str | None = Field(default=None, max_length=80)


@router.post("/search", response_model=SearchResult)
async def search(req: SearchReq, c: C):
    if req.use_ai:
        return await c.assistant.search(req.question, req.consent, req.previous_id)
    if req.previous_id:
        raise ApiError(422, "ai_required", "Follow-up questions require AI search.")
    try:
        return c.assistant.remember(await c.search.answer(req.question))
    except Unanswerable:
        raise ApiError(422, "unanswerable", "ANVAYA couldn't turn that into a query.", {"suggestions": workspace_suggestions(c.repo, c.cfg.demo_mode)})
    except QueryTimeout:
        raise ApiError(422, "unanswerable", "That question took too long. Try narrowing the time window.",
                       {"suggestions": workspace_suggestions(c.repo, c.cfg.demo_mode), "reason": "timeout"})


@router.get("/search/suggestions", response_model=Items)
async def suggestions(c: C):
    return {"items": workspace_suggestions(c.repo, c.cfg.demo_mode)}


class ExplainReq(BaseModel):
    kind: Literal["search", "incident"]
    target: str = Field(min_length=1, max_length=80)
    consent: bool = False
    preview_id: str | None = Field(default=None, max_length=80)


@router.get("/ai/status")
async def ai_status(c: C):
    return c.assistant.status()


@router.post("/ai/preview")
async def ai_preview(req: ExplainReq, c: C):
    return c.assistant.preview(req.kind, req.target)


@router.post("/ai/explain")
async def ai_explain(req: ExplainReq, c: C):
    return await c.assistant.explain(req.kind, req.target, req.consent, req.preview_id)
