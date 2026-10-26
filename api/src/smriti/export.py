"""Full export: a zip of JSON plus every stored file, so the user is never locked in."""

import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from smriti.models import Enrichment, Entity, Event, Item, ItemEntity
from smriti.storage import get_storage, item_prefix


def _item_record(item: Item, entities: list[dict], enrichments: list[dict]) -> dict:
    content = item.content
    return {
        "id": str(item.id),
        "type": item.type,
        "status": item.status,
        "source_url": item.source_url,
        "canonical_url": item.canonical_url,
        "title": item.title,
        "note": item.note,
        "summary": item.summary,
        "site_name": item.site_name,
        "saved_at": item.saved_at.isoformat(),
        "last_opened_at": item.last_opened_at.isoformat() if item.last_opened_at else None,
        "open_count": item.open_count,
        "capture": item.capture,
        "duplicate_of": str(item.duplicate_of) if item.duplicate_of else None,
        "meta": item.meta,
        "palette": item.palette,
        "tags": sorted(t.name for t in item.tags),
        "entities": entities,
        "content": {
            "text": content.text,
            "html": content.html,
            "ocr_text": content.ocr_text,
            "lang": content.lang,
        }
        if content
        else None,
        "enrichments": enrichments,
        "files": f"files/{item_prefix(item.id)}",
    }


async def build_export(session: AsyncSession) -> Path:
    out = Path(tempfile.mkstemp(prefix="smriti-export-", suffix=".zip")[1])
    storage = get_storage()
    items = (
        (
            await session.execute(
                select(Item).options(selectinload(Item.content)).order_by(Item.saved_at)
            )
        )
        .scalars()
        .all()
    )
    entity_rows = await session.execute(
        select(ItemEntity.item_id, Entity.name, Entity.kind).join(Entity)
    )
    entities: dict = {}
    for item_id, name, kind in entity_rows:
        entities.setdefault(item_id, []).append({"name": name, "kind": kind})
    enrichment_rows = (await session.execute(select(Enrichment))).scalars()
    enrichments: dict = {}
    for e in enrichment_rows:
        enrichments.setdefault(e.item_id, []).append(
            {
                "step": e.step,
                "version": e.version,
                "output": e.output,
                "model": e.model,
                "created_at": e.created_at.isoformat(),
            }
        )
    events = (await session.execute(select(Event).order_by(Event.at))).scalars()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "README.txt",
            "Smriti export. items.jsonl has one item per line; files/ holds originals, archives and images.\n",
        )
        z.writestr(
            "manifest.json",
            json.dumps({"exported_at": datetime.now(UTC).isoformat(), "items": len(items)}),
        )
        z.writestr(
            "items.jsonl",
            "\n".join(
                json.dumps(
                    _item_record(i, entities.get(i.id, []), enrichments.get(i.id, [])), default=str
                )
                for i in items
            ),
        )
        z.writestr(
            "events.jsonl",
            "\n".join(
                json.dumps(
                    {
                        "item_id": str(e.item_id),
                        "kind": e.kind,
                        "at": e.at.isoformat(),
                        "context": e.context,
                    }
                )
                for e in events
            ),
        )
        for item in items:
            async for key in storage.iter_keys(item_prefix(item.id)):
                z.writestr(f"files/{key}", await storage.get(key))
    return out
