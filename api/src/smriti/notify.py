"""Item status changes over Postgres LISTEN/NOTIFY, fanned out to SSE subscribers."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.db import asyncpg_dsn

ITEMS_CHANNEL = "smriti_items"
log = logging.getLogger(__name__)


async def publish(session: AsyncSession, item_id: uuid.UUID, status: str, **extra: object) -> None:
    """Queue a notification; Postgres delivers it when the transaction commits."""
    payload = json.dumps({"id": str(item_id), "status": status, **extra}, default=str)
    await session.execute(text("SELECT pg_notify(:c, :p)"), {"c": ITEMS_CHANNEL, "p": payload})


class Broadcaster:
    """One LISTEN connection per API process, shared by all open SSE streams."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._conn: asyncpg.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure_listening(self) -> None:
        async with self._lock:
            if self._conn and not self._conn.is_closed():
                return
            self._conn = await asyncpg.connect(asyncpg_dsn())
            await self._conn.add_listener(ITEMS_CHANNEL, self._on_notify)

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: str) -> None:
        for queue in list(self._subscribers):
            if queue.qsize() < 1000:
                queue.put_nowait(payload)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[str]]:
        await self._ensure_listening()
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def close(self) -> None:
        if self._conn and not self._conn.is_closed():
            await self._conn.close()


broadcaster = Broadcaster()
