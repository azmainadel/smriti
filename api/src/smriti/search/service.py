"""Hybrid search: retrieve in parallel, fuse with reciprocal rank fusion, re-rank lightly."""

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smriti.config import get_settings
from smriti.db import get_sessionmaker
from smriti.ml import adapter
from smriti.models import Item
from smriti.search import retrievers
from smriti.search.query_parser import ParsedQuery, needs_llm, parse

log = logging.getLogger(__name__)
RRF_K = 60
WEIGHTS = {"keyword": 1.0, "semantic": 1.0, "visual": 0.7, "color": 1.2}


@dataclass
class Hit:
    item: Item
    score: float
    sources: list[str]
    highlight: str | None = None


@dataclass
class SearchResult:
    parsed: ParsedQuery
    hits: list[Hit]
    took_ms: int
    timings: dict[str, int] = field(default_factory=dict)
    fallback: bool = False  # no exact results: these are the closest matches without filters


def rrf(
    ranked: dict[str, list[uuid.UUID]], weights: dict[str, float] = WEIGHTS
) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for name, ids in ranked.items():
        w = weights.get(name, 1.0)
        for rank, item_id in enumerate(ids):
            scores[item_id] = scores.get(item_id, 0.0) + w / (RRF_K + rank + 1)
    return scores


def rerank_boost(item: Item, phrase_hit: bool, now: datetime) -> float:
    """Multiplier from recency, the user's own history, and an exact-phrase match."""
    age_days = max((now - item.saved_at).total_seconds() / 86400, 0)
    recency = math.exp(-age_days / 365)
    history = math.log1p(item.open_count)
    return (
        1
        + 0.15 * recency
        + 0.08 * history
        + (0.25 if phrase_hit else 0)
        + (0.05 if item.note else 0)
    )


class _LlmFilters(BaseModel):
    text: str
    date_from: str | None = None
    date_to: str | None = None


async def _llm_assist(pq: ParsedQuery) -> None:
    """Ask the small LLM for a date range the rules could not read. Bounded to 400 ms."""
    try:
        async with asyncio.timeout(0.4):
            result = await adapter.complete_json(
                "query",
                f"Today is {datetime.now(UTC).date().isoformat()}. Split the search query into the "
                "topic text and an optional saved-date range (ISO dates). Do not invent ranges.",
                pq.text,
                _LlmFilters,
            )
    except (TimeoutError, adapter.ModelError):
        return
    if result and result.output.date_from:
        try:
            pq.date_from = datetime.fromisoformat(result.output.date_from).date()
            pq.date_to = (
                datetime.fromisoformat(result.output.date_to).date()
                if result.output.date_to
                else None
            )
            pq.text = result.output.text
        except ValueError:
            pass


async def _timed(name: str, timings: dict[str, int], coro):  # noqa: ANN001, ANN202
    start = time.perf_counter()
    try:
        return await coro
    finally:
        timings[name] = int((time.perf_counter() - start) * 1000)


async def _in_session(fn, *args):  # noqa: ANN001, ANN202
    # Each retriever gets its own connection so they run in parallel.
    async with get_sessionmaker()() as session, session.begin():
        return await fn(session, *args)


async def _browse(session: AsyncSession, f: retrievers.Filters, limit: int) -> list[uuid.UUID]:
    rows = await session.execute(
        text(f"SELECT i.id FROM items i WHERE {f.sql} ORDER BY i.saved_at DESC LIMIT :limit"),
        {**f.params, "limit": limit},
    )
    return list(rows.scalars())


async def _highlights(session: AsyncSession, ids: list[uuid.UUID], q: str) -> dict[uuid.UUID, str]:
    tsq = retrievers.tsquery_string(q, any_word=True)
    if not tsq or not ids:
        return {}
    rows = await session.execute(
        text(
            "SELECT item_id, ts_headline('english', left(coalesce(text, ''), 50000), to_tsquery('english', :q), "
            "'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=24, MinWords=8, "
            "FragmentDelimiter= … ') AS h FROM item_content WHERE item_id = ANY(:ids) "
            "AND tsv @@ to_tsquery('english', :q)"
        ),
        {"q": tsq, "ids": ids},
    )
    return {r.item_id: r.h for r in rows if r.h and "<mark>" in r.h}


async def _cross_encoder_rerank(
    query: str, hits: list[Hit], texts: dict[uuid.UUID, str]
) -> list[Hit]:
    model = _cross_encoder()
    top = hits[:50]
    docs = [texts.get(h.item.id) or h.item.title or "" for h in top]
    scores = await asyncio.to_thread(lambda: list(model.rerank(query, docs)))
    ranked = [h for _, h in sorted(zip(scores, top, strict=True), key=lambda x: -x[0])]
    return ranked + hits[50:]


_ce = None


def _cross_encoder():  # noqa: ANN202
    global _ce
    if _ce is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _ce = TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")
    return _ce


async def search(
    session: AsyncSession,
    q: str,
    *,
    limit: int = 40,
    types: list[str] | None = None,
    now: datetime | None = None,
    use_llm: bool = True,
    cross_encoder: bool | None = None,
) -> SearchResult:
    started = time.perf_counter()
    settings = get_settings()
    pq = parse(q, now)
    if use_llm and needs_llm(pq):
        await _llm_assist(pq)
    f = retrievers.build_filters(pq, types)
    n = settings.search_candidates
    timings: dict[str, int] = {}

    tasks: dict[str, asyncio.Task] = {}
    best_chunks: dict[uuid.UUID, str] = {}
    async with asyncio.TaskGroup() as tg:
        if pq.text:
            tasks["keyword"] = tg.create_task(
                _timed("keyword", timings, _in_session(retrievers.keyword, pq, f, n))
            )
            vector = await _timed("embed", timings, adapter.embed_query(pq.text))
            tasks["semantic"] = tg.create_task(
                _timed("semantic", timings, _in_session(retrievers.semantic, vector, f, n))
            )
            if adapter.vision_enabled():
                clip = await adapter.clip_embed_text(pq.text)
                if clip:
                    tasks["visual"] = tg.create_task(
                        _timed("visual", timings, _in_session(retrievers.visual, clip, f, n))
                    )
        if pq.colors:
            tasks["color"] = tg.create_task(
                _timed("color", timings, _in_session(retrievers.color, pq.colors, f, n))
            )
        if not tasks:
            tasks["browse"] = tg.create_task(_in_session(_browse, f, limit))

    ranked: dict[str, list[uuid.UUID]] = {}
    for name, task in tasks.items():
        result = task.result()
        if name == "semantic":
            ranked[name], best_chunks = result
        else:
            ranked[name] = result

    if "browse" in ranked:
        fused = {item_id: 1.0 / (i + 1) for i, item_id in enumerate(ranked["browse"])}
    else:
        fused = rrf(ranked)
    top_ids = sorted(fused, key=fused.get, reverse=True)[: limit * 2]

    items = {
        i.id: i
        for i in (
            await session.execute(
                select(Item).where(Item.id.in_(top_ids)).options(selectinload(Item.assets))
            )
        ).scalars()
    }
    now_utc = datetime.now(UTC)
    phrases = [p.lower() for p in pq.phrases] or (
        [pq.text.lower()] if len(pq.text.split()) > 1 else []
    )
    highlights = await _highlights(session, top_ids[:limit], pq.text) if pq.text else {}

    hits: list[Hit] = []
    for item_id in top_ids:
        item = items.get(item_id)
        if not item:
            continue
        haystack = f"{item.title or ''} {item.note or ''} {best_chunks.get(item_id, '')} {highlights.get(item_id, '')}".lower()
        phrase_hit = any(
            p in haystack.replace("<mark>", "").replace("</mark>", "") for p in phrases
        )
        score = fused[item_id] * (
            1 if "browse" in ranked else rerank_boost(item, phrase_hit, now_utc)
        )
        sources = [name for name, ids in ranked.items() if item_id in ids]
        snippet = highlights.get(item_id) or (best_chunks.get(item_id, "")[:240] or None)
        hits.append(Hit(item, score, sources, snippet))
    hits.sort(key=lambda h: h.score, reverse=True)

    if cross_encoder if cross_encoder is not None else settings.search_rerank_cross_encoder:
        hits = await _cross_encoder_rerank(pq.text, hits, best_chunks)

    result = SearchResult(pq, hits[:limit], int((time.perf_counter() - started) * 1000), timings)

    # No results with filters: show the closest matches without them, and say so.
    if not result.hits and pq.has_filters and pq.text:
        relaxed = await search(session, pq.text, limit=limit, now=now, use_llm=False)
        relaxed.parsed, relaxed.fallback = pq, True
        relaxed.took_ms = int((time.perf_counter() - started) * 1000)
        return relaxed
    return result
