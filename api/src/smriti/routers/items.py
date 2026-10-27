import base64
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from smriti import items as item_service
from smriti import resurface
from smriti.auth import Authed
from smriti.db import get_session
from smriti.jobs import queue
from smriti.models import Enrichment, Entity, Item, ItemEntity, ItemStatus, ItemTag, Tag
from smriti.notify import publish
from smriti.pipeline.context import StepContext
from smriti.pipeline.enrich import ENRICHERS
from smriti.pipeline.index import index
from smriti.schemas import (
    AssetOut,
    EnrichmentOut,
    EntityOut,
    ItemCreate,
    ItemDetail,
    ItemOut,
    ItemPage,
    ItemPatch,
    Resurfaced,
    item_out,
)
from smriti.storage import signed_url

router = APIRouter(prefix="/items", tags=["items"])
Session = Annotated[AsyncSession, Depends(get_session)]


def encode_cursor(item: Item) -> str:
    return base64.urlsafe_b64encode(f"{item.saved_at.isoformat()}|{item.id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        saved, item_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(saved), uuid.UUID(item_id)
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad cursor") from e


_SAVE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ItemCreate"}},
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "note": {"type": "string"},
                        "title": {"type": "string"},
                    },
                }
            },
        },
    }
}


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=ItemOut, openapi_extra=_SAVE_BODY
)
async def save_item(request: Request, session: Session, _: Authed) -> ItemOut:
    """Save a URL, text, selection or uploaded file. Returns at once with `status: pending`;
    the workflow fills the item in and `/stream` reports progress."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "file is required")
        item = await item_service.save_file(
            session,
            upload.filename or "upload",
            await upload.read(),
            upload.content_type,
            note=str(form.get("note") or "") or None,
            title=str(form.get("title") or "") or None,
            capture=str(form.get("capture") or "web"),
        )
    else:
        try:
            data = ItemCreate.model_validate_json(await request.body())
        except ValidationError as e:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, e.errors(include_url=False)
            ) from e
        item = await item_service.save(session, data)
    await session.commit()
    await session.refresh(item, ["tags"])
    return item_out(item)


@router.get("", response_model=ItemPage)
async def list_items(
    session: Session,
    _: Authed,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
    type: Annotated[list[str] | None, Query()] = None,
    tag: str | None = None,
    since: date | None = None,
    until: date | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
) -> ItemPage:
    """The grid feed, newest first, cursor-paginated."""
    stmt = select(Item).where(Item.duplicate_of.is_(None))
    if type:
        stmt = stmt.where(Item.type.in_(type))
    if tag:
        stmt = stmt.where(Item.id.in_(select(ItemTag.item_id).join(Tag).where(Tag.name == tag)))
    if since:
        stmt = stmt.where(Item.saved_at >= since)
    if until:
        stmt = stmt.where(Item.saved_at < until + timedelta(days=1))
    if status_:
        stmt = stmt.where(Item.status == status_)
    if cursor:
        saved, item_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(Item.saved_at < saved, and_(Item.saved_at == saved, Item.id < item_id))
        )
    rows = (
        (
            await session.execute(
                stmt.order_by(Item.saved_at.desc(), Item.id.desc()).limit(limit + 1)
            )
        )
        .scalars()
        .all()
    )
    page = rows[:limit]
    return ItemPage(
        items=[item_out(i) for i in page],
        next_cursor=encode_cursor(page[-1]) if len(rows) > limit else None,
    )


async def _load(session: AsyncSession, item_id: uuid.UUID) -> Item:
    item = await item_service.get(session, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item not found")
    return item


@router.get("/{item_id}/card", response_model=ItemOut)
async def get_card(item_id: uuid.UUID, session: Session, _: Authed) -> ItemOut:
    """Just what a grid card needs; the web app refetches this as status events arrive."""
    return item_out(await _load(session, item_id))


@router.get("/{item_id}", response_model=ItemDetail)
async def get_item(item_id: uuid.UUID, session: Session, _: Authed) -> ItemDetail:
    item = await _load(session, item_id)
    content = item.content
    enrichments = (
        (
            await session.execute(
                select(Enrichment)
                .where(Enrichment.item_id == item_id)
                .order_by(Enrichment.step, Enrichment.version.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, Enrichment] = {}
    for e in enrichments:  # the latest version wins
        latest.setdefault(e.step, e)
    entities = (
        (
            await session.execute(
                select(Entity)
                .join(ItemEntity)
                .where(ItemEntity.item_id == item_id)
                .order_by(Entity.kind, Entity.name)
            )
        )
        .scalars()
        .all()
    )
    duplicates = (
        (await session.execute(select(Item.id).where(Item.duplicate_of == item_id))).scalars().all()
    )
    related = await resurface.related(session, item_id)
    summary = latest.get("summary")
    return ItemDetail(
        **item_out(item).model_dump(),
        content_html=content.html if content else None,
        text_length=len(content.text or "") if content else 0,
        lang=content.lang if content else None,
        key_points=(summary.output.get("key_points") or []) if summary else [],
        archive_url=signed_url(content.html_archive_key) if content else None,
        screenshot_url=signed_url(content.screenshot_key) if content else None,
        original_url=signed_url(item.original_key),
        assets=[
            AssetOut(
                id=a.id,
                kind=a.kind,
                url=signed_url(a.storage_key) or "",
                width=a.width,
                height=a.height,
                caption=a.caption,
                ocr_text=a.ocr_text,
                colors=a.colors,
            )
            for a in sorted(item.assets, key=lambda a: a.position)
        ],
        entities=[EntityOut(name=e.name, kind=e.kind) for e in entities],
        enrichments=[
            EnrichmentOut(
                step=e.step,
                version=e.version,
                output=e.output,
                model=e.model,
                tokens=e.tokens,
                cost=e.cost,
                ms=e.ms,
                created_at=e.created_at,
            )
            for e in latest.values()
        ],
        related=[
            Resurfaced(item=item_out(p.item), reason=p.reason, score=p.score) for p in related
        ],
        duplicates=list(duplicates),
    )


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(item_id: uuid.UUID, patch: ItemPatch, session: Session, _: Authed) -> ItemOut:
    item = await _load(session, item_id)
    fields = patch.model_fields_set
    if "title" in fields:
        item.title = (patch.title or "").strip() or None
        item.meta = {**item.meta, "title_source": "user"}
    if "note" in fields:
        item.note = (patch.note or "").strip() or None
    if "tags" in fields and patch.tags is not None:
        await item_service.set_user_tags(session, item, patch.tags)
    # Search fields include the title, note and tags: refresh them without re-running the workflow.
    if fields and item.status == ItemStatus.ready:
        await index(StepContext(session, item))
    await publish(session, item.id, item.status, step="edited")
    await session.commit()
    await session.refresh(item, ["tags"])
    return item_out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID, session: Session, _: Authed) -> None:
    item = await _load(session, item_id)
    await item_service.remove(session, item)
    await publish(session, item_id, "deleted")
    await session.commit()


@router.post("/{item_id}/retry", response_model=ItemOut)
async def retry_item(item_id: uuid.UUID, session: Session, _: Authed) -> ItemOut:
    """Re-run the failed steps of one item."""
    item = await _load(session, item_id)
    await queue.retry_failed(session, item_id)
    item.status, item.error = ItemStatus.pending, None
    await publish(session, item.id, item.status, step="retry")
    await session.commit()
    await session.refresh(item, ["tags"])
    return item_out(item)


@router.post("/{item_id}/reenrich", response_model=ItemOut)
async def reenrich_item(item_id: uuid.UUID, session: Session, _: Authed) -> ItemOut:
    """Re-run every enrichment step for one item, e.g. after switching models."""
    item = await _load(session, item_id)
    for enricher in ENRICHERS.values():
        await queue.enqueue(
            session,
            item_id,
            f"enrich.{enricher.name}",
            enricher.version,
            chain=False,
            key_suffix=f"manual-{uuid.uuid4().hex[:8]}",
        )
    await session.commit()
    await session.refresh(item, ["tags"])
    return item_out(item)


@router.get("/{item_id}/more-like-this", response_model=list[Resurfaced])
async def more_like_this(
    item_id: uuid.UUID, session: Session, _: Authed, limit: int = 12
) -> list[Resurfaced]:
    picks = await resurface.related(session, item_id, n=limit)
    return [Resurfaced(item=item_out(p.item), reason=p.reason, score=p.score) for p in picks]
