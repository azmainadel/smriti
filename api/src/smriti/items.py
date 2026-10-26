"""Saving, editing and deleting items. Shared by the API, email, importers and CLI."""

import mimetypes
import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smriti.ml.heuristics import normalize_tag
from smriti.models import Item, ItemContent, ItemStatus, ItemTag, ItemType, Tag
from smriti.notify import publish
from smriti.pipeline import workflow
from smriti.pipeline.classify import type_from_mime, type_from_text, type_from_url
from smriti.schemas import ItemCreate
from smriti.storage import get_storage, item_prefix
from smriti.urls import canonicalize, domain_of


def _new_item(url: str | None, capture: str, saved_at: datetime | None) -> Item:
    item = Item(
        id=uuid.uuid4(),
        status=ItemStatus.pending,
        source_url=url,
        canonical_url=canonicalize(url) if url else None,
        domain=domain_of(url),
        capture=capture,
        meta={},
        open_count=0,
    )
    if saved_at:
        item.saved_at = saved_at
    # Best guess for the instant card; classify refines it.
    item.type = (type_from_url(url) or ItemType.link) if url else ItemType.note
    return item


async def save(session: AsyncSession, data: ItemCreate) -> Item:
    url = str(data.url) if data.url else None
    storage = get_storage()

    if data.image_url:
        item = _new_item(str(data.image_url), data.capture, data.saved_at)
        item.type = ItemType.image
        item.meta = {"page_url": url, "fixed_type": True}
    elif data.selection:
        item = _new_item(url, "selection", data.saved_at)
        item.type = ItemType.quote
        item.title = data.title
        item.meta = {"fixed_type": True, "quote": data.selection.strip()}
        item.content = ItemContent(item_id=item.id, text=data.selection.strip())
    elif url:
        item = _new_item(url, data.capture, data.saved_at)
        item.title = data.title
        if data.html:
            item.raw_html_key = f"{item_prefix(item.id)}page.html"
            await storage.put(item.raw_html_key, data.html.encode(), "text/html; charset=utf-8")
    else:
        item = _new_item(None, data.capture, data.saved_at)
        text = (data.text or "").strip()
        item.type = type_from_text(text)
        item.content = ItemContent(item_id=item.id, text=text)

    if data.title:
        item.title = data.title
        # The extension sends document.title, which extraction may improve on; a typed title wins.
        if data.capture != "extension":
            item.meta = {**item.meta, "title_source": "user"}
    item.note = (data.note or "").strip() or None
    session.add(item)
    await session.flush()
    if data.tags:
        await set_user_tags(session, item, data.tags)
    await workflow.start(session, item.id)
    await publish(session, item.id, item.status, step="saved")
    return item


async def save_file(
    session: AsyncSession,
    filename: str,
    data: bytes,
    content_type: str | None,
    *,
    note: str | None = None,
    title: str | None = None,
    capture: str = "web",
) -> Item:
    mime = (content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(
        ";"
    )[0]
    item = _new_item(None, capture, None)
    item.type = type_from_mime(mime) or ItemType.link
    if mime.startswith("text/"):
        item.type = ItemType.note
        item.content = ItemContent(item_id=item.id, text=data.decode("utf-8", "replace"))
    else:
        ext = mimetypes.guess_extension(mime) or ""
        item.original_key = f"{item_prefix(item.id)}original{ext}"
        await get_storage().put(item.original_key, data, mime)
    item.title = (
        title or filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip() or None
    )
    item.note = (note or "").strip() or None
    item.meta = {"filename": filename, "mime": mime, "bytes": len(data), "fixed_type": True}
    session.add(item)
    await session.flush()
    await workflow.start(session, item.id)
    await publish(session, item.id, item.status, step="saved")
    return item


async def get(session: AsyncSession, item_id: uuid.UUID) -> Item | None:
    return await session.get(
        Item, item_id, options=[selectinload(Item.content), selectinload(Item.assets)]
    )


async def set_user_tags(session: AsyncSession, item: Item, names: list[str]) -> None:
    """User-edited tags replace all tags on the item and are kept across re-enrichment."""
    clean = list(dict.fromkeys(n for n in (normalize_tag(t) for t in names) if n))
    await session.execute(delete(ItemTag).where(ItemTag.item_id == item.id))
    for name in clean:
        tag = (await session.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
        session.add(ItemTag(item_id=item.id, tag_id=tag.id, source="user"))
    await session.flush()
    await session.refresh(item, ["tags"])


async def remove(session: AsyncSession, item: Item) -> None:
    await session.delete(item)
    await get_storage().delete_prefix(item_prefix(item.id))
