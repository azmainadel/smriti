import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from smriti.auth import Authed
from smriti.notify import broadcaster

router = APIRouter(tags=["stream"])


@router.get("/stream")
async def stream(request: Request, _: Authed) -> EventSourceResponse:
    """Server-sent events: `item` events carry {id, status, step} as each workflow step lands."""

    async def events() -> AsyncIterator[dict[str, str]]:
        async with broadcaster.subscribe() as queue:
            yield {"event": "ready", "data": "{}"}
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    continue  # sse-starlette sends its own keep-alive pings
                yield {"event": "item", "data": payload}

    return EventSourceResponse(events(), ping=15)
