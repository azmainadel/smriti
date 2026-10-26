"""The four retrievers. Each returns item ids in rank order and shares one filter clause."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.config import get_settings
from smriti.ml.colors import NEUTRALS, name_to_lab
from smriti.search.query_parser import ParsedQuery


@dataclass
class Filters:
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


def build_filters(pq: ParsedQuery, extra_types: list[str] | None = None) -> Filters:
    """WHERE clause over `items i`. Duplicates are hidden; their originals carry the match."""
    clauses = ["i.duplicate_of IS NULL"]
    params: dict[str, Any] = {}
    types = pq.types or extra_types
    if types:
        clauses.append("i.type = ANY(:types)")
        params["types"] = types
    if pq.date_from:
        clauses.append("i.saved_at >= :date_from")
        params["date_from"] = pq.date_from
    if pq.date_to:
        clauses.append("i.saved_at < :date_to")
        params["date_to"] = pq.date_to + timedelta(days=1)
    if pq.domains:
        ors = []
        for n, d in enumerate(pq.domains):
            ors.append(f"(i.domain = :dom{n} OR i.domain LIKE :domsub{n})")
            params[f"dom{n}"], params[f"domsub{n}"] = d, f"%.{d}"
        clauses.append("(" + " OR ".join(ors) + ")")
    if pq.has_note:
        clauses.append("coalesce(i.note, '') <> ''")
    if pq.tags:
        clauses.append(
            "i.id IN (SELECT it.item_id FROM item_tags it JOIN tags t ON t.id = it.tag_id "
            "WHERE t.name = ANY(:tags))"
        )
        params["tags"] = pq.tags
    return Filters(" AND ".join(clauses), params)


_TOKEN = re.compile(r"[\w]+", re.UNICODE)


def tsquery_string(query: str, *, any_word: bool = False) -> str | None:
    """AND of the words, last word as a prefix so results update while typing."""
    words = [w.lower() for w in _TOKEN.findall(query)][:16]
    if not words:
        return None
    parts = [f"'{w}'" for w in words[:-1]] + [f"'{words[-1]}':*"]
    return (" | " if any_word else " & ").join(parts)


# Ranking reads every matching tsvector, so a term found in most of the library costs a
# full scan. Rank at most this many matches; for such terms the semantic list carries ranking.
MAX_RANKED_MATCHES = 3000


async def keyword(
    session: AsyncSession, pq: ParsedQuery, f: Filters, limit: int
) -> list[uuid.UUID]:
    results: list[uuid.UUID] = []
    multiword = len(_TOKEN.findall(pq.text)) > 1
    for any_word in (False, True) if multiword else (False,):
        tsq = tsquery_string(pq.text, any_word=any_word)
        if not tsq:
            return []
        rows = await session.execute(
            text(
                "WITH m AS (SELECT ic.item_id, ic.tsv FROM item_content ic JOIN items i ON i.id = ic.item_id "
                f"WHERE ic.tsv @@ to_tsquery('english', :q) AND {f.sql} LIMIT :cap) "
                "SELECT item_id FROM m ORDER BY ts_rank_cd(tsv, to_tsquery('english', :q), 32) DESC LIMIT :limit"
            ),
            {**f.params, "q": tsq, "limit": limit, "cap": MAX_RANKED_MATCHES},
        )
        for item_id in rows.scalars():
            if item_id not in results:
                results.append(item_id)
        # Fall back to OR only when AND finds almost nothing.
        if len(results) >= 3:
            break
    return results


class VectorIndex(Protocol):
    """Nearest-neighbour search over chunk embeddings. pgvector HNSW today; the custom
    HNSW index (project #5) plugs in here and is benchmarked on the same data."""

    async def nearest(
        self, session: AsyncSession, vector: list[float], f: Filters, limit: int
    ) -> list[tuple[uuid.UUID, float, str]]: ...


class PgVectorIndex:
    _iterative: bool | None = None

    async def _supports_iterative_scan(self, session: AsyncSession) -> bool:
        if PgVectorIndex._iterative is None:
            version = (
                await session.execute(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                )
            ).scalar() or "0"
            major, minor = (int(x) for x in version.split(".")[:2])
            PgVectorIndex._iterative = (major, minor) >= (0, 8)
        return PgVectorIndex._iterative

    async def nearest(
        self, session: AsyncSession, vector: list[float], f: Filters, limit: int
    ) -> list[tuple[uuid.UUID, float, str]]:
        # Filtered HNSW scans can stop short; iterative scans (pgvector 0.8+) keep going.
        if await self._supports_iterative_scan(session):
            await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        await session.execute(text("SET LOCAL hnsw.ef_search = 200"))
        rows = await session.execute(
            text(
                "SELECT c.item_id, c.embedding <=> CAST(:v AS vector) AS d, c.text FROM chunks c "
                f"JOIN items i ON i.id = c.item_id WHERE {f.sql} "
                "ORDER BY c.embedding <=> CAST(:v AS vector) LIMIT :limit"
            ),
            {**f.params, "v": str(vector), "limit": limit * 4},
        )
        return [(r.item_id, float(r.d), r.text) for r in rows]


vector_index: VectorIndex = PgVectorIndex()


async def semantic(
    session: AsyncSession,
    vector: list[float],
    f: Filters,
    limit: int,
    max_distance: float | None = None,
) -> tuple[list[uuid.UUID], dict[uuid.UUID, str]]:
    """Nearest chunks collapsed to items; also returns each item's best-matching chunk."""
    max_distance = (
        max_distance if max_distance is not None else get_settings().semantic_max_distance
    )
    order: list[uuid.UUID] = []
    best: dict[uuid.UUID, str] = {}
    for item_id, distance, chunk in await vector_index.nearest(session, vector, f, limit):
        if distance > max_distance:
            break
        if item_id not in best:
            order.append(item_id)
            best[item_id] = chunk
    return order[:limit], best


async def visual(
    session: AsyncSession, clip_vector: list[float], f: Filters, limit: int
) -> list[uuid.UUID]:
    rows = await session.execute(
        text(
            "SELECT a.item_id, min(a.clip_embedding <=> CAST(:v AS vector)) AS d FROM assets a "
            f"JOIN items i ON i.id = a.item_id WHERE a.clip_embedding IS NOT NULL AND {f.sql} "
            "GROUP BY a.item_id ORDER BY d LIMIT :limit"
        ),
        {**f.params, "v": str(clip_vector), "limit": limit},
    )
    # CLIP text-image cosine distances sit in a narrow band; ~0.8 is already unrelated.
    return [r.item_id for r in rows if r.d < 0.8]


async def color(
    session: AsyncSession, colors: list[str], f: Filters, limit: int
) -> list[uuid.UUID]:
    """Items whose palette has a color within reach of the query color in CIELAB.
    A heavier swatch counts more: distance is discounted by its weight."""
    params: dict[str, Any] = {**f.params, "limit": limit}
    scores = []
    for n, name in enumerate(colors):
        L, a, b = name_to_lab(name)
        params |= {f"L{n}": L, f"a{n}": a, f"b{n}": b}
        # Chroma matters more than lightness for chromatic names ("blue" in a dark UI is still blue).
        lw = 1.0 if name in NEUTRALS else 0.5
        scores.append(
            f"min(sqrt({lw} * power((c->'lab'->>0)::float - :L{n}, 2) + power((c->'lab'->>1)::float - :a{n}, 2)"
            f" + power((c->'lab'->>2)::float - :b{n}, 2)) * (1.2 - (c->>'weight')::float))"
        )
    score = " + ".join(scores)
    rows = await session.execute(
        text(
            f"SELECT i.id, {score} AS d FROM items i CROSS JOIN LATERAL jsonb_array_elements(i.palette) c "
            f"WHERE i.palette IS NOT NULL AND {f.sql} GROUP BY i.id "
            f"HAVING {score} < :cutoff ORDER BY d LIMIT :limit"
        ),
        {**params, "cutoff": 40.0 * len(colors)},
    )
    return [r.id for r in rows]
