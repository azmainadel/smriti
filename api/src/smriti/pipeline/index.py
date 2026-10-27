"""Step 6: write the search fields, then mark the item ready."""

from sqlalchemy import select

from smriti.models import Entity, ItemEntity, ItemStatus
from smriti.pipeline.context import StepContext


async def index(ctx: StepContext) -> None:
    item = ctx.item
    entities = (
        await ctx.session.execute(
            select(Entity.name).join(ItemEntity).where(ItemEntity.item_id == item.id)
        )
    ).scalars()
    content = ctx.content()
    content.title = item.title or item.source_url
    # Weighted with the title: things the user wrote or that name the item.
    content.extra = " ".join(
        filter(
            None,
            [
                item.note,
                " ".join(t.name.replace("-", " ") for t in item.tags),
                item.site_name,
                item.domain,
                item.meta.get("author"),
                item.meta.get("channel"),
                item.summary,
                " ".join(entities),
                *(a.caption for a in item.assets if a.caption),
            ],
        )
    )
    item.status = ItemStatus.ready
    item.error = None
