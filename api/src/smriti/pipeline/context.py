import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smriti.models import Enrichment, Item, ItemContent
from smriti.storage import Storage, get_storage, item_prefix

log = logging.getLogger(__name__)


class StepSkipped(Exception):  # noqa: N818 - control flow, not an error
    """Raised by a step that has nothing to do for this item."""


class PermanentError(Exception):
    """A failure that retrying will not fix, e.g. a 404."""


@dataclass
class StepContext:
    session: AsyncSession
    item: Item
    storage: Storage = field(default_factory=get_storage)
    # Set by enrichment: a hash of the inputs, stored with each output to skip unchanged items.
    fingerprint: str | None = None

    @classmethod
    async def load(cls, session: AsyncSession, item_id: uuid.UUID) -> "StepContext | None":
        item = await session.get(
            Item,
            item_id,
            options=[selectinload(Item.content), selectinload(Item.assets)],
            populate_existing=True,
        )
        return cls(session, item) if item else None

    def key(self, name: str) -> str:
        return f"{item_prefix(self.item.id)}{name}"

    async def put(self, name: str, data: bytes, content_type: str | None = None) -> str:
        key = self.key(name)
        await self.storage.put(key, data, content_type)
        return key

    def content(self) -> ItemContent:
        if self.item.content is None:
            self.item.content = ItemContent(item_id=self.item.id)
        return self.item.content

    async def record(
        self,
        step: str,
        version: int,
        output: dict[str, Any],
        *,
        model: str | None = None,
        tokens: int = 0,
        cost: float = 0.0,
        ms: int = 0,
    ) -> None:
        values = {
            "item_id": self.item.id,
            "step": step,
            "version": version,
            "output": {**output, "_input": self.fingerprint} if self.fingerprint else output,
            "model": model,
            "tokens": tokens,
            "cost": cost,
            "ms": ms,
        }
        stmt = insert(Enrichment).values(**values)
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["item_id", "step", "version"],
                set_={k: stmt.excluded[k] for k in ("output", "model", "tokens", "cost", "ms")},
            )
        )


StepFn = Callable[[StepContext], Awaitable[None]]


@dataclass(frozen=True)
class Step:
    name: str
    version: int
    run: StepFn
    timeout_s: float = 120.0
    max_attempts: int = 3
    # A failed optional step is logged and the workflow continues.
    optional: bool = False


class Timer:
    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        self.ms = 0
        return self

    def __exit__(self, *_: object) -> None:
        self.ms = int((time.perf_counter() - self.start) * 1000)
