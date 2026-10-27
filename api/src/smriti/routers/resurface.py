from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from smriti import resurface as rs
from smriti.auth import Authed
from smriti.db import get_session
from smriti.schemas import Resurfaced, ResurfaceOut, item_out

router = APIRouter(tags=["resurface"])


@router.get("/resurface", response_model=ResurfaceOut)
async def resurface(
    session: Annotated[AsyncSession, Depends(get_session)],
    _: Authed,
    surface: Literal["home", "digest", "on-this-day", "serendipity"] = "home",
) -> ResurfaceOut:
    """Items for a surface, each with the reason it came back."""
    match surface:
        case "home":
            picks = await rs.home(session)
        case "digest":
            picks = await rs.digest(session)
        case "on-this-day":
            picks = await rs.on_this_day(session)
        case "serendipity":
            picks = await rs.serendipity(session)
    return ResurfaceOut(
        surface=surface,
        items=[
            Resurfaced(item=item_out(p.item), reason=p.reason, score=round(p.score, 4))
            for p in picks
        ],
    )
