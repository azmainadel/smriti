"""Race-safe get-or-create for the shared tag and entity vocabularies. Parallel jobs often
propose the same new tag at once; INSERT ... ON CONFLICT DO NOTHING lets one win and the
others read its row."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.models import Entity, Tag


async def upsert_tag(session: AsyncSession, name: str, embedding: Any = None) -> Tag:
    await session.execute(
        insert(Tag)
        .values(name=name, embedding=embedding)
        .on_conflict_do_nothing(index_elements=["name"])
    )
    tag = (await session.execute(select(Tag).where(Tag.name == name))).scalar_one()
    if tag.embedding is None and embedding is not None:
        tag.embedding = embedding  # user-created tags get a vector once enrichment sees them
    return tag


async def upsert_entity(session: AsyncSession, name: str, kind: str) -> Entity:
    """Entities match case-insensitively; the first spelling seen is kept."""
    query = select(Entity).where(func.lower(Entity.name) == name.lower(), Entity.kind == kind)
    if found := (await session.execute(query)).scalars().first():
        return found
    await session.execute(
        insert(Entity)
        .values(name=name[:200], kind=kind)
        .on_conflict_do_nothing(index_elements=["name", "kind"])
    )
    return (await session.execute(query)).scalars().first()
