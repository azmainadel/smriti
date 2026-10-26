from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.auth import Authed
from smriti.db import get_session
from smriti.models import Event, Item
from smriti.schemas import EventIn

router = APIRouter(tags=["events"])


@router.post("/events", status_code=status.HTTP_204_NO_CONTENT)
async def record_event(
    event: EventIn, session: Annotated[AsyncSession, Depends(get_session)], _: Authed
) -> None:
    """Opens and dismisses feed ranking and resurfacing."""
    item = await session.get(Item, event.item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    if event.kind == "open":
        item.open_count += 1
        item.last_opened_at = datetime.now(UTC)
    session.add(Event(item_id=event.item_id, kind=event.kind, context=event.context))
    await session.commit()
