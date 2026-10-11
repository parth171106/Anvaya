from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import C
from app.api.errors import ApiError
from app.api.schemas import Items, SearchResult
from app.search.nl2sql import QueryTimeout, Unanswerable
from app.search.templates import SUGGESTIONS

router = APIRouter(prefix="/api")


class SearchReq(BaseModel):
    question: str


@router.post("/search", response_model=SearchResult)
async def search(req: SearchReq, c: C):
    try:
        return await c.search.answer(req.question)
    except Unanswerable:
        raise ApiError(422, "unanswerable", "ANVAYA couldn't turn that into a query.", {"suggestions": SUGGESTIONS})
    except QueryTimeout:
        raise ApiError(422, "unanswerable", "That question took too long. Try narrowing the time window.",
                       {"suggestions": SUGGESTIONS, "reason": "timeout"})


@router.get("/search/suggestions", response_model=Items)
async def suggestions():
    return {"items": SUGGESTIONS}
