"""Step 5: enrichment. Each sub-step is versioned, runs in its own transaction, and can be
re-run in bulk when a model improves (POST /admin/reindex)."""

import asyncio
import base64
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, text

from smriti.db import get_sessionmaker
from smriti.ml import adapter
from smriti.ml.colors import palette_from_hex
from smriti.ml.heuristics import extractive_summary, keyword_tags, normalize_tag, proper_nouns
from smriti.ml.imaging import analyze
from smriti.ml.textsig import simhash
from smriti.models import Chunk, Enrichment, Item, ItemEntity, ItemTag, ItemType, Tag
from smriti.pipeline.chunking import chunk_html
from smriti.pipeline.context import StepContext, Timer
from smriti.pipeline.ocr import ocr_image
from smriti.vocab import upsert_entity, upsert_tag

log = logging.getLogger(__name__)
LLM_INPUT_CHARS = 6000
TAG_SNAP_SIMILARITY = 0.86


@dataclass(frozen=True)
class Enricher:
    name: str
    version: int
    run: Callable[[StepContext], Awaitable[None]]
    phase: int = 1  # phase 2 runs after phase 1 finishes (it reads phase 1 output)


def llm_input(item: Item) -> str:
    body = item.content.text if item.content else ""
    parts = [
        f"Title: {item.title}" if item.title else "",
        f"Source: {item.domain}" if item.domain else "",
        f"Description: {item.meta.get('description')}" if item.meta.get("description") else "",
        f"User note: {item.note}" if item.note else "",
        (body or "")[:LLM_INPUT_CHARS],
    ]
    return "\n".join(p for p in parts if p)


# ---------- summary ----------


class SummaryOut(BaseModel):
    summary: str = Field(description="One plain sentence saying what this is about.")
    key_points: list[str] = Field(description="Up to 3 short key points.")

    @field_validator("key_points")
    @classmethod
    def _at_most_three(cls, v: list[str]) -> list[str]:
        return v[:3]  # small models overshoot; trim rather than fail


async def summarize(ctx: StepContext) -> None:
    item = ctx.item
    text = (item.content.text if item.content else "") or ""
    if item.type in (ItemType.image, ItemType.palette) or (
        len(text) < 200 and item.type != ItemType.video
    ):
        # Short notes and quotes are their own summary.
        item.summary = (
            None if item.type in (ItemType.image, ItemType.palette) else text[:280] or None
        )
        await ctx.record("summary", SUMMARY.version, {"summary": item.summary, "key_points": []})
        return
    with Timer() as t:
        result = await adapter.complete_json(
            "summary",
            "You summarize saved web content for a personal library. Be concrete and neutral.",
            llm_input(item),
            SummaryOut,
        )
    if result:
        out, model, tokens, cost = result.output, result.model, result.tokens, result.cost
    else:
        summary, points = extractive_summary(text, item.meta.get("description"))
        out, model, tokens, cost = (
            SummaryOut(summary=summary, key_points=points),
            "heuristic",
            0,
            0.0,
        )
    item.summary = out.summary
    await ctx.record(
        "summary", SUMMARY.version, out.model_dump(), model=model, tokens=tokens, cost=cost, ms=t.ms
    )


# ---------- tags ----------


class TagsOut(BaseModel):
    tags: list[str] = Field(description="3 to 8 lowercase topic tags.")

    @field_validator("tags")
    @classmethod
    def _at_most_eight(cls, v: list[str]) -> list[str]:
        return v[:8]


async def snap_tags(ctx: StepContext, proposed: list[str]) -> list[Tag]:
    """Map proposed tags onto existing ones by embedding similarity so the vocabulary stays small."""
    names = sorted(dict.fromkeys(n for n in (normalize_tag(t) for t in proposed) if n))[:8]
    if not names:
        return []
    vectors = (await adapter.embed_texts(names)).output
    out: list[Tag] = []
    for name, vec in zip(names, vectors, strict=True):
        tag = (await ctx.session.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag is not None and tag.embedding is None:
            tag.embedding = vec
        if tag is None:
            distance = Tag.embedding.cosine_distance(vec)
            nearest = (
                await ctx.session.execute(
                    select(Tag, distance.label("d"))
                    .where(Tag.embedding.is_not(None))
                    .order_by(distance)
                    .limit(1)
                )
            ).first()
            if nearest and 1 - nearest.d >= TAG_SNAP_SIMILARITY:
                tag = nearest.Tag
            else:
                tag = await upsert_tag(ctx.session, name, vec)
        if tag not in out:
            out.append(tag)
    return out


async def tag(ctx: StepContext) -> None:
    item = ctx.item
    with Timer() as t:
        result = await adapter.complete_json(
            "tags",
            "Propose 3 to 8 short lowercase topic tags for this saved item. Prefer general, reusable "
            "topics (e.g. 'typography', 'machine-learning', 'japanese-carpentry') over specifics.",
            llm_input(item),
            TagsOut,
        )
    text = (item.content.text if item.content else "") or ""
    proposed = result.output.tags if result else keyword_tags(item.title or "", text)
    tags = await snap_tags(ctx, proposed)

    await ctx.session.execute(
        delete(ItemTag).where(ItemTag.item_id == item.id, ItemTag.source == "auto")
    )
    user_tag_ids = set(
        (
            await ctx.session.execute(select(ItemTag.tag_id).where(ItemTag.item_id == item.id))
        ).scalars()
    )
    for tg in tags:
        if tg.id not in user_tag_ids:
            ctx.session.add(ItemTag(item_id=item.id, tag_id=tg.id, source="auto"))
    await ctx.record(
        "tags",
        TAGS.version,
        {"proposed": proposed, "tags": [tg.name for tg in tags]},
        model=result.model if result else "heuristic",
        tokens=result.tokens if result else 0,
        cost=result.cost if result else 0.0,
        ms=t.ms,
    )


# ---------- entities ----------


class EntityOut(BaseModel):
    name: str
    kind: str = Field(pattern="^(person|place|product|org|topic)$")


class EntitiesOut(BaseModel):
    entities: list[EntityOut]

    @field_validator("entities")
    @classmethod
    def _at_most_twenty(cls, v: list[EntityOut]) -> list[EntityOut]:
        return v[:20]


async def extract_entities(ctx: StepContext) -> None:
    item = ctx.item
    with Timer() as t:
        result = await adapter.complete_json(
            "entities",
            "Extract the named people, places, products, organizations and main topics from this "
            "saved item. Use canonical names. kind is one of person, place, product, org, topic.",
            llm_input(item),
            EntitiesOut,
        )
    if result:
        found = [(e.name.strip(), e.kind) for e in result.output.entities if e.name.strip()]
    else:
        found = [
            (n, "topic") for n in proper_nouns((item.content.text if item.content else "") or "")
        ]

    await ctx.session.execute(delete(ItemEntity).where(ItemEntity.item_id == item.id))
    seen: set[int] = set()
    for name, kind in sorted(found):
        entity = await upsert_entity(ctx.session, name, kind)
        if entity.id not in seen:
            seen.add(entity.id)
            ctx.session.add(ItemEntity(item_id=item.id, entity_id=entity.id))
    await ctx.record(
        "entities",
        ENTITIES.version,
        {"entities": [{"name": n, "kind": k} for n, k in found]},
        model=result.model if result else "heuristic",
        tokens=result.tokens if result else 0,
        cost=result.cost if result else 0.0,
        ms=t.ms,
    )


# ---------- text embeddings ----------


def item_vector_text(item: Item) -> str:
    parts = [item.title, item.note, item.meta.get("description"), item.summary]
    if item.type in (ItemType.quote, ItemType.note) and item.content:
        parts.append(item.content.text)
    text = "\n".join(p for p in parts if p)
    return (
        text
        or ((item.content.text or "")[:1000] if item.content else "")
        or (item.source_url or "")
    )


async def embed(ctx: StepContext) -> None:
    item = ctx.item
    content = item.content
    specs = chunk_html(content.html, content.text) if content else []
    specs = specs[:400]  # a 400-chunk cap keeps book-length PDFs from flooding the index
    texts = [item_vector_text(item)] + [c.text for c in specs]
    ocr = " ".join(filter(None, [content.ocr_text if content else None]))
    if ocr:
        texts.append(ocr[:2000])
    with Timer() as t:
        result = await adapter.embed_texts(texts)
    await ctx.session.execute(delete(Chunk).where(Chunk.item_id == item.id))
    kinds = ["item"] + [c.kind for c in specs] + (["ocr"] if ocr else [])
    for i, (kind, chunk_text, vec) in enumerate(zip(kinds, texts, result.output, strict=True)):
        ctx.session.add(
            Chunk(
                item_id=item.id,
                ordinal=i,
                kind=kind,
                text=chunk_text,
                embedding=vec,
                embed_model=result.model,
            )
        )
    await ctx.record(
        "embeddings",
        EMBEDDINGS.version,
        {"chunks": len(texts)},
        model=result.model,
        tokens=result.tokens,
        ms=t.ms,
    )


# ---------- images: hashes, colors, OCR, captions, CLIP ----------


async def images(ctx: StepContext) -> None:
    item = ctx.item
    assets = sorted(item.assets, key=lambda a: a.position)
    stats = {"assets": len(assets), "ocr": 0, "captions": 0, "clip": 0}
    tokens, cost, model = 0, 0.0, None
    with Timer() as t:
        blobs = [await ctx.storage.get(a.storage_key) for a in assets]
        for asset, data in zip(assets, blobs, strict=True):
            info = await asyncio.to_thread(analyze, data)
            asset.phash, asset.colors = info.phash, info.colors
            # OCR only where text in the image is the point: screenshots, images, tweet media.
            if item.type in (ItemType.image, ItemType.tweet) or asset.kind == "thumbnail":
                asset.ocr_text = await asyncio.to_thread(ocr_image, data)
                stats["ocr"] += bool(asset.ocr_text)
            if item.type == ItemType.image and asset.position == 0:
                caption = await adapter.describe_image(
                    "caption",
                    base64.b64encode(data).decode(),
                    "Write one sentence of alt text for this image: what it shows, colors, any text.",
                )
                if caption:
                    asset.caption = caption.output
                    tokens, cost, model = (
                        tokens + caption.tokens,
                        cost + caption.cost,
                        caption.model,
                    )
                    stats["captions"] += 1
        if vectors := await adapter.clip_embed_images(blobs):
            for asset, vec in zip(assets, vectors, strict=True):
                asset.clip_embedding = vec
            stats["clip"] = len(vectors)

    # Item palette: the palette itself, or the lead image's colors.
    if item.type == ItemType.palette and item.meta.get("colors"):
        item.palette = palette_from_hex(item.meta["colors"])
    elif assets and assets[0].colors:
        item.palette = assets[0].colors

    ocr_text = "\n".join(a.ocr_text for a in assets if a.ocr_text)
    if ocr_text or (item.content and item.content.ocr_text):
        ctx.content().ocr_text = ocr_text or None
    if item.type == ItemType.image and assets and assets[0].caption and not item.summary:
        item.summary = assets[0].caption
    await ctx.record(
        "images", IMAGES.version, stats, model=model, tokens=tokens, cost=cost, ms=t.ms
    )


# ---------- duplicates ----------

_HAMMING_SQL = "bit_count(('x' || lpad(to_hex({col} # :h), 16, '0'))::bit(64))"


async def dedup(ctx: StepContext) -> None:
    item = ctx.item
    s = ctx.session
    text_body = (item.content.text if item.content else "") or ""
    item.simhash = simhash(text_body) if len(text_body) > 200 else None
    match: tuple[uuid.UUID, str] | None = None

    if item.canonical_url:
        row = await s.execute(
            select(Item.id)
            .where(
                Item.canonical_url == item.canonical_url,
                Item.id != item.id,
                Item.duplicate_of.is_(None),
                Item.saved_at < item.saved_at,
            )
            .order_by(Item.saved_at)
            .limit(1)
        )
        if found := row.scalar():
            match = (found, "url")

    if not match and item.simhash is not None:
        row = await s.execute(
            text(
                f"SELECT id FROM items WHERE simhash IS NOT NULL AND id != :id AND duplicate_of IS NULL "
                f"AND saved_at < :saved AND {_HAMMING_SQL.format(col='simhash')} <= 3 ORDER BY saved_at LIMIT 1"
            ),
            {"id": item.id, "saved": item.saved_at, "h": item.simhash},
        )
        if found := row.scalar():
            match = (found, "simhash")

    lead = next((a for a in item.assets if a.position == 0 and a.phash is not None), None)
    if not match and item.type == ItemType.image and lead:
        row = await s.execute(
            text(
                "SELECT a.item_id FROM assets a JOIN items i ON i.id = a.item_id "
                "WHERE i.type = 'image' AND a.position = 0 AND a.phash IS NOT NULL AND i.id != :id "
                f"AND i.duplicate_of IS NULL AND i.saved_at < :saved AND {_HAMMING_SQL.format(col='a.phash')} <= 6 "
                "ORDER BY i.saved_at LIMIT 1"
            ),
            {"id": item.id, "saved": item.saved_at, "h": lead.phash},
        )
        if found := row.scalar():
            match = (found, "phash")

    item.duplicate_of = match[0] if match else None
    await ctx.record(
        "dedup",
        DEDUP.version,
        {"duplicate_of": str(match[0]) if match else None, "by": match[1] if match else None},
    )


SUMMARY = Enricher("summary", 1, summarize)
TAGS = Enricher("tags", 1, tag)
ENTITIES = Enricher("entities", 1, extract_entities)
IMAGES = Enricher("images", 1, images)
# Embeddings read the summary for the whole-item vector, so they wait for phase 1.
EMBEDDINGS = Enricher("embeddings", 1, embed, phase=2)
DEDUP = Enricher("dedup", 1, dedup, phase=2)
ENRICHERS: dict[str, Enricher] = {
    e.name: e for e in (SUMMARY, TAGS, ENTITIES, IMAGES, EMBEDDINGS, DEDUP)
}


async def _done(item_id: uuid.UUID, enricher: Enricher) -> bool:
    async with get_sessionmaker()() as s:
        row = await s.execute(
            select(Enrichment.output).where(
                Enrichment.item_id == item_id,
                Enrichment.step == enricher.name,
                Enrichment.version == enricher.version,
            )
        )
        output = row.scalar()
        return output is not None and "error" not in output


async def run_enricher(
    item_id: uuid.UUID, enricher: Enricher, *, force: bool = False
) -> str | None:
    """Run one sub-step in its own transaction. Returns an error message, or None."""
    if not force and await _done(item_id, enricher):
        return None
    async with get_sessionmaker()() as session:
        ctx = await StepContext.load(session, item_id)
        if ctx is None:
            return None
        try:
            await enricher.run(ctx)
            await session.commit()
            return None
        except Exception as e:
            await session.rollback()
            log.exception("enrichment %s failed", enricher.name)
            message = f"{type(e).__name__}: {e}"
    # The failed transaction is gone; record the error in a fresh one.
    async with get_sessionmaker()() as session:
        await StepContext(session, Item(id=item_id)).record(
            enricher.name, enricher.version, {"error": message[:2000]}
        )
        await session.commit()
    return message


async def enrich_all(item_id: uuid.UUID) -> list[str]:
    errors: list[str] = []
    for phase in (1, 2):
        batch = [e for e in ENRICHERS.values() if e.phase == phase]
        results = await asyncio.gather(*(run_enricher(item_id, e) for e in batch))
        errors += [f"{e.name}: {r}" for e, r in zip(batch, results, strict=True) if r]
    return errors
