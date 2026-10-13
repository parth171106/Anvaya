from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import Items, SearchResult
from app.search.nl2sql import QueryTimeout, Unanswerable
from app.search.templates import workspace_suggestions

router = APIRouter(prefix="/api")


class SearchReq(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


@router.post("/search", response_model=SearchResult)
async def search(req: SearchReq, c: C):
    try:
        return await c.search.answer(req.question)
    except Unanswerable:
        raise ApiError(422, "unanswerable", "ANVAYA couldn't turn that into a query.", {"suggestions": workspace_suggestions(c.repo, c.cfg.demo_mode)})
    except QueryTimeout:
        raise ApiError(422, "unanswerable", "That question took too long. Try narrowing the time window.",
                       {"suggestions": workspace_suggestions(c.repo, c.cfg.demo_mode), "reason": "timeout"})


@router.get("/search/suggestions", response_model=Items)
async def suggestions(c: C):
    return {"items": workspace_suggestions(c.repo, c.cfg.demo_mode)}
