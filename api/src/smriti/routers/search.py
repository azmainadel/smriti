from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.auth import Authed
from smriti.db import get_session
from smriti.schemas import ChipOut, SearchHitOut, SearchOut, item_out
from smriti.search.service import search as run_search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchOut)
async def search(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Authed,
    q: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
    type: Annotated[list[str] | None, Query()] = None,
) -> SearchOut:
    """Free text plus filters parsed out of it. Parsed filters come back as chips with their
    position in `q`, so the client removes a chip by cutting that span out of the query."""
    result = await run_search(session, q, limit=limit, types=type)
    pq = result.parsed
    return SearchOut(
        query=q,
        text=pq.text,
        chips=[ChipOut(**vars(c)) for c in pq.chips],
        hits=[
            SearchHitOut(
                item=item_out(h.item),
                score=round(h.score, 6),
                sources=h.sources,
                highlight=h.highlight,
            )
            for h in result.hits
        ],
        took_ms=result.took_ms,
        timings=result.timings,
        fallback=result.fallback,
    )
