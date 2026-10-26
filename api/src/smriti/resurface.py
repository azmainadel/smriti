"""Resurfacing: bring saved items back when they become relevant, and say why.

Score = (relevance to now, forgetting curve, importance) x dismiss penalty, with a hard
freshness rule: nothing shown on an earlier day in the last 14 days comes back.
The metric that matters is the share of resurfaced items the user opens.
"""

import logging
import math
import smtplib
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from html import escape

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smriti.config import get_settings
from smriti.db import get_sessionmaker
from smriti.models import AppSetting, Chunk, Event, Item, ItemStatus, ItemTag, Tag

log = logging.getLogger(__name__)
FRESHNESS_DAYS = 14
RECENT_DAYS = 7
BASE_INTERVAL_DAYS = 7.0
INTERVAL_GROWTH = 2.2


@dataclass
class Pick:
    item: Item
    score: float
    reason: str
    signals: dict[str, float]


# ---------- pure scoring ----------


def forgetting(days_since_seen: float, times_seen: int) -> float:
    """Spaced-repetition style: each view pushes the next return further out.
    0 right after a view, approaching 1 once the interval has passed."""
    interval = BASE_INTERVAL_DAYS * INTERVAL_GROWTH ** max(times_seen, 0)
    return 1 - math.exp(-max(days_since_seen, 0) / interval)


def importance(has_note: bool, open_count: int, from_highlight: bool) -> float:
    return 0.45 * has_note + 0.3 * min(max(open_count - 1, 0), 3) / 3 + 0.25 * from_highlight


def relevance(similarity: float) -> float:
    """Map cosine similarity to [0, 1]; below 0.45 is noise for most text embedders."""
    return min(max((similarity - 0.45) / 0.4, 0.0), 1.0)


def combine(
    rel: float,
    forget: float,
    imp: float,
    dismissals: int,
    weights: tuple[float, float, float] = (0.5, 0.3, 0.2),
) -> float:
    wr, wf, wi = weights
    return (wr * rel + wf * forget + wi * imp) * 0.5**dismissals


def _ago(then: datetime, now: datetime) -> str:
    days = (now - then).days
    if days < 14:
        return f"{days} days ago" if days > 1 else "recently"
    if days < 60:
        return f"{days // 7} weeks ago"
    if days < 365:
        return f"{days // 30} months ago"
    years = days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def _plural(word: str, n: int) -> str:
    return word if n == 1 else (word + "es" if word.endswith(("s", "x")) else word + "s")


# ---------- context: what the user is into right now ----------


@dataclass
class Context:
    recent_ids: list[uuid.UUID]
    recent_vectors: np.ndarray  # (n, dim), normalized
    recent_titles: dict[uuid.UUID, str]
    recent_tags: Counter[str]
    recent_types_by_tag: dict[str, Counter[str]]


async def _context(session: AsyncSession, now: datetime) -> Context:
    since = now - timedelta(days=RECENT_DAYS)
    opened = select(Event.item_id).where(Event.kind == "open", Event.at >= since)
    rows = await session.execute(
        select(Item.id, Item.title, Item.type)
        .where(Item.status == ItemStatus.ready, (Item.saved_at >= since) | Item.id.in_(opened))
        .order_by(Item.saved_at.desc())
        .limit(30)
    )
    recent = rows.all()
    ids = [r.id for r in recent]
    vectors = np.zeros((0, 1))
    if ids:
        vecs = (
            (
                await session.execute(
                    select(Chunk.embedding).where(Chunk.item_id.in_(ids), Chunk.kind == "item")
                )
            )
            .scalars()
            .all()
        )
        vectors = np.array([np.asarray(v, dtype=np.float32) for v in vecs]) if vecs else vectors
    tag_rows = await session.execute(
        select(ItemTag.item_id, Tag.name)
        .join(Tag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id.in_(ids))
    )
    types = {r.id: r.type for r in recent}
    tags: Counter[str] = Counter()
    by_tag: dict[str, Counter[str]] = {}
    for item_id, name in tag_rows:
        tags[name] += 1
        by_tag.setdefault(name, Counter())[types[item_id]] += 1
    return Context(ids, vectors, {r.id: r.title or "" for r in recent}, tags, by_tag)


# ---------- candidates ----------


async def _shown_before_today(session: AsyncSession, now: datetime) -> set[uuid.UUID]:
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await session.execute(
        select(Event.item_id).where(
            Event.kind == "resurface",
            Event.at >= now - timedelta(days=FRESHNESS_DAYS),
            Event.at < start_today,
        )
    )
    return set(rows.scalars())


async def _event_counts(
    session: AsyncSession, kind: str, ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = await session.execute(
        select(Event.item_id, func.count())
        .where(Event.kind == kind, Event.item_id.in_(ids))
        .group_by(Event.item_id)
    )
    return dict(rows.all())


async def _related_to_recent(
    session: AsyncSession, ctx: Context, per_item: int = 30
) -> dict[uuid.UUID, tuple[float, uuid.UUID]]:
    """Best similarity of each candidate to any recent item, and which recent item it was."""
    best: dict[uuid.UUID, tuple[float, uuid.UUID]] = {}
    if not len(ctx.recent_vectors):
        return best
    anchors = ctx.recent_ids[: len(ctx.recent_vectors)][:10]
    for anchor_id, vec in zip(anchors, ctx.recent_vectors[:10], strict=False):
        rows = await session.execute(
            text(
                "SELECT c.item_id, 1 - (c.embedding <=> CAST(:v AS vector)) AS sim FROM chunks c "
                "WHERE c.kind = 'item' AND c.item_id <> ALL(:recent) "
                "ORDER BY c.embedding <=> CAST(:v AS vector) LIMIT :k"
            ),
            {"v": str(vec.tolist()), "recent": ctx.recent_ids, "k": per_item},
        )
        for item_id, sim in rows:
            if sim > best.get(item_id, (-1.0, anchor_id))[0]:
                best[item_id] = (float(sim), anchor_id)
    return best


async def _load_items(session: AsyncSession, ids: list[uuid.UUID]) -> list[Item]:
    rows = await session.execute(
        select(Item)
        .where(Item.id.in_(ids), Item.status == ItemStatus.ready, Item.duplicate_of.is_(None))
        .options(selectinload(Item.assets))
    )
    return list(rows.scalars())


def _reason(
    item: Item,
    signals: dict[str, float],
    anchor_title: str | None,
    ctx: Context,
    item_tags: list[str],
    now: datetime,
) -> str:
    rel, forget, imp = signals["relevance"], signals["forgetting"], signals["importance"]
    if rel >= max(forget, imp) * 0.8 and rel > 0.2:
        shared = [t for t in item_tags if ctx.recent_tags.get(t)]
        if shared:
            tag = max(shared, key=lambda t: ctx.recent_tags[t])
            types = ctx.recent_types_by_tag.get(tag, Counter())
            n = sum(types.values())
            kind = types.most_common(1)[0][0] if len(types) == 1 else "item"
            return f"Related to the {n} {_plural(kind, n)} on {tag.replace('-', ' ')} you saved this week"
        if anchor_title:
            return f"Similar to “{anchor_title[:60]}”, which you saved recently"
    if imp >= forget and item.note:
        snippet = item.note.strip().splitlines()[0][:70]
        return f"You added a note: “{snippet}”"
    if item.open_count > 1 and imp >= forget:
        return f"You opened this {item.open_count} times"
    seen = item.last_opened_at
    if seen:
        return f"You haven't opened this since {seen.strftime('%B %Y')}"
    return f"Saved {_ago(item.saved_at, now)} and never opened"


async def score_candidates(
    session: AsyncSession, now: datetime, weights=(0.5, 0.3, 0.2), pool: int = 400
) -> list[Pick]:  # noqa: ANN001
    ctx = await _context(session, now)
    related = await _related_to_recent(session, ctx)
    excluded = await _shown_before_today(session, now) | set(ctx.recent_ids)

    # Forgetting candidates: least recently seen, plus a random sample so the long tail gets a chance.
    stale = await session.execute(
        select(Item.id)
        .where(
            Item.status == ItemStatus.ready,
            Item.duplicate_of.is_(None),
            Item.saved_at < now - timedelta(days=2),
        )
        .order_by(func.coalesce(Item.last_opened_at, Item.saved_at))
        .limit(pool // 2)
    )
    sample = await session.execute(
        select(Item.id)
        .where(
            Item.status == ItemStatus.ready,
            Item.duplicate_of.is_(None),
            Item.saved_at < now - timedelta(days=2),
        )
        .order_by(func.random())
        .limit(pool // 2)
    )
    ids = list({*related, *stale.scalars(), *sample.scalars()} - excluded)
    if not ids:
        return []
    items = await _load_items(session, ids)
    ids = [i.id for i in items]
    resurfaced = await _event_counts(session, "resurface", ids)
    dismissed = await _event_counts(session, "dismiss", ids)
    tag_rows = await session.execute(
        select(ItemTag.item_id, Tag.name)
        .join(Tag, Tag.id == ItemTag.tag_id)
        .where(ItemTag.item_id.in_(ids))
    )
    tags_of: dict[uuid.UUID, list[str]] = {}
    for item_id, name in tag_rows:
        tags_of.setdefault(item_id, []).append(name)

    picks = []
    for item in items:
        seen_at = item.last_opened_at or item.saved_at
        sim, anchor = related.get(item.id, (0.0, None))
        signals = {
            "relevance": relevance(sim),
            "forgetting": forgetting(
                (now - seen_at).total_seconds() / 86400,
                item.open_count + resurfaced.get(item.id, 0),
            ),
            "importance": importance(bool(item.note), item.open_count, item.capture == "selection"),
        }
        score = combine(
            signals["relevance"],
            signals["forgetting"],
            signals["importance"],
            dismissed.get(item.id, 0),
            weights,
        )
        reason = _reason(
            item,
            signals,
            ctx.recent_titles.get(anchor) if anchor else None,
            ctx,
            tags_of.get(item.id, []),
            now,
        )
        picks.append(Pick(item, score, reason, signals))
    picks.sort(key=lambda p: p.score, reverse=True)
    return picks


def diversify(picks: list[Pick], n: int) -> list[Pick]:
    """Greedy pick that avoids repeating the same reason or type too often."""
    chosen: list[Pick] = []
    reasons: Counter[str] = Counter()
    types: Counter[str] = Counter()
    for p in picks:
        if reasons[p.reason] >= 1 or types[p.item.type] >= max(2, n // 2):
            continue
        chosen.append(p)
        reasons[p.reason] += 1
        types[p.item.type] += 1
        if len(chosen) == n:
            return chosen
    rest = [p for p in picks if p not in chosen]
    return chosen + rest[: n - len(chosen)]


# ---------- surfaces ----------


async def _log_shown(session: AsyncSession, picks: list[Pick], surface: str, now: datetime) -> None:
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ids = [p.item.id for p in picks]
    already = set(
        (
            await session.execute(
                select(Event.item_id).where(
                    Event.kind == "resurface",
                    Event.item_id.in_(ids),
                    Event.at >= start_today,
                    Event.context["surface"].astext == surface,
                )
            )
        ).scalars()
    )
    for p in picks:
        if p.item.id not in already:
            session.add(
                Event(
                    item_id=p.item.id,
                    kind="resurface",
                    context={"surface": surface, "reason": p.reason},
                )
            )
    await session.commit()


async def home(session: AsyncSession, now: datetime | None = None, n: int = 3) -> list[Pick]:
    now = now or datetime.now(UTC)
    picks = diversify(await score_candidates(session, now), n)
    picks = [p for p in picks if p.score > 0.05]
    await _log_shown(session, picks, "home", now)
    return picks


async def digest(
    session: AsyncSession, now: datetime | None = None, n: int = 7, log_event: bool = True
) -> list[Pick]:
    now = now or datetime.now(UTC)
    # The digest leans on forgetting: it is the weekly look back.
    picks = diversify(await score_candidates(session, now, weights=(0.35, 0.45, 0.2)), n)
    if log_event:
        await _log_shown(session, picks, "digest", now)
    return picks


async def on_this_day(
    session: AsyncSession, now: datetime | None = None, n: int = 10
) -> list[Pick]:
    now = now or datetime.now(UTC)
    rows = await session.execute(
        select(Item)
        .where(
            Item.status == ItemStatus.ready,
            Item.duplicate_of.is_(None),
            func.extract("month", Item.saved_at) == now.month,
            func.extract("day", Item.saved_at) == now.day,
            func.extract("year", Item.saved_at) < now.year,
        )
        .order_by(Item.saved_at.desc())
        .limit(n)
        .options(selectinload(Item.assets))
    )
    picks = [Pick(i, 1.0, f"Saved on this day in {i.saved_at.year}", {}) for i in rows.scalars()]
    await _log_shown(session, picks, "on-this-day", now)
    return picks


async def related(session: AsyncSession, item_id: uuid.UUID, n: int = 5) -> list[Pick]:
    """Reader rail: semantic neighbours, nudged up by shared entities."""
    vec = (
        await session.execute(
            select(Chunk.embedding).where(Chunk.item_id == item_id, Chunk.kind == "item")
        )
    ).scalar()
    if vec is None:
        return []
    rows = await session.execute(
        text(
            "SELECT c.item_id, 1 - (c.embedding <=> CAST(:v AS vector)) AS sim FROM chunks c "
            "JOIN items i ON i.id = c.item_id WHERE c.kind = 'item' AND c.item_id <> :id "
            "AND i.duplicate_of IS NULL AND i.status = 'ready' "
            "ORDER BY c.embedding <=> CAST(:v AS vector) LIMIT 40"
        ),
        {"v": str(np.asarray(vec).tolist()), "id": item_id},
    )
    sims = {r.item_id: float(r.sim) for r in rows}
    if not sims:
        return []
    shared_rows = await session.execute(
        text(
            "SELECT ie.item_id, array_agg(e.name ORDER BY e.name) AS names FROM item_entities ie "
            "JOIN entities e ON e.id = ie.entity_id WHERE ie.item_id = ANY(:ids) "
            "AND ie.entity_id IN (SELECT entity_id FROM item_entities WHERE item_id = :id) GROUP BY ie.item_id"
        ),
        {"ids": list(sims), "id": item_id},
    )
    shared = {r.item_id: r.names for r in shared_rows}
    items = {i.id: i for i in await _load_items(session, list(sims))}
    picks = []
    for other, sim in sims.items():
        if other not in items:
            continue
        names = shared.get(other, [])
        score = sim + min(0.05 * len(names), 0.2)
        reason = f"Also mentions {', '.join(names[:2])}" if names else "Similar topic"
        picks.append(
            Pick(items[other], score, reason, {"similarity": sim, "shared_entities": len(names)})
        )
    picks.sort(key=lambda p: p.score, reverse=True)
    return picks[:n]


async def open_rate(session: AsyncSession, days: int = 28) -> dict[str, float | int]:
    """Share of resurfaced items opened within 7 days of being shown."""
    since = datetime.now(UTC) - timedelta(days=days)
    row = (
        await session.execute(
            text(
                "SELECT count(DISTINCT r.item_id) AS shown, count(DISTINCT o.item_id) AS opened "
                "FROM events r LEFT JOIN events o ON o.item_id = r.item_id AND o.kind = 'open' "
                "AND o.at BETWEEN r.at AND r.at + interval '7 days' "
                "WHERE r.kind = 'resurface' AND r.at >= :since"
            ),
            {"since": since},
        )
    ).one()
    return {
        "shown": row.shown,
        "opened": row.opened,
        "rate": round(row.opened / row.shown, 3) if row.shown else 0.0,
    }


# ---------- weekly digest email ----------


def render_digest_html(picks: list[Pick], base_url: str) -> str:
    rows = "".join(
        f'<li style="margin:0 0 18px"><a href="{base_url}/item/{p.item.id}" style="font:600 17px Georgia,serif;color:#1d1a16">'
        f"{escape(p.item.title or p.item.source_url or 'Untitled')}</a>"
        f'<div style="font:13px system-ui;color:#6b645a;margin-top:4px">{escape(p.reason)}</div></li>'
        for p in picks
    )
    return (
        '<div style="max-width:560px;margin:auto;padding:24px;background:#faf8f4">'
        '<h1 style="font:600 22px Georgia,serif;color:#1d1a16">From your past</h1>'
        f'<ol style="padding-left:18px">{rows}</ol></div>'
    )


async def maybe_send_digest(now: datetime | None = None) -> bool:
    """Called hourly by the worker. Sends at most one digest per 7 days, if opted in."""
    s = get_settings()
    now = now or datetime.now(UTC)
    async with get_sessionmaker()() as session:
        setting = await session.get(AppSetting, "digest")
        config = setting.value if setting else {}
        if not config.get("email") or not (s.smtp_host and s.digest_email_to):
            return False
        last = config.get("last_sent")
        if last and now - datetime.fromisoformat(last) < timedelta(days=7):
            return False
        picks = await digest(session, now)
        if not picks:
            return False
        msg = EmailMessage()
        msg["Subject"] = f"Smriti: {len(picks)} things from your past"
        msg["From"], msg["To"] = s.smtp_from, s.digest_email_to
        msg.set_content("\n\n".join(f"{p.item.title}\n{p.reason}" for p in picks))
        web = config.get("web_url", "http://localhost:3000")
        msg.add_alternative(render_digest_html(picks, web), subtype="html")
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(msg)
        setting.value = {**config, "last_sent": now.isoformat()}
        await session.commit()
        log.info("digest sent", extra={"data": {"items": len(picks)}})
        return True
