from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from smriti import resurface
from smriti.auth import Authed
from smriti.config import get_settings
from smriti.db import get_session
from smriti.jobs import queue
from smriti.ml import adapter
from smriti.models import AppSetting, Item, ItemStatus, Job, JobStatus
from smriti.pipeline import workflow
from smriti.pipeline.enrich import ENRICHERS
from smriti.pipeline.extractors.media import whisper_available
from smriti.pipeline.ocr import ocr_available
from smriti.schemas import DigestSettings, ModelChoiceIn, ReindexIn, ReindexOut

router = APIRouter(prefix="/admin", tags=["admin"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/reindex", response_model=ReindexOut)
async def reindex(body: ReindexIn, session: Session, _: Authed) -> ReindexOut:
    """Re-run one step at its current version across all items.

    Enrichment steps (`summary`, `tags`, `entities`, `embeddings`, `images`, `dedup`) re-run
    for every item. Workflow steps (`extract`, `snapshot`...) re-run only for items whose last
    run used an older version, unless `force` is set. Search fields refresh afterwards.
    """
    name = body.step.removeprefix("enrich.")
    if name in ENRICHERS:
        step_name, version = f"enrich.{name}", ENRICHERS[name].version
    elif name in workflow.BY_NAME:
        step_name, version = name, workflow.BY_NAME[name].version
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown step {body.step}")
    if body.version is not None and body.version != version:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{step_name} is at version {version}; this build cannot run {body.version}",
        )

    if body.force:
        await queue.forget(session, step_name, version)
    ids = select(Item.id).where(Item.status != ItemStatus.pending)
    if step_name in workflow.BY_NAME and not body.force:
        current = select(Job.item_id).where(
            Job.step == step_name, Job.version == version, Job.status == JobStatus.done
        )
        ids = ids.where(Item.id.not_in(current))
    enqueued = 0
    for item_id in (await session.execute(ids)).scalars():
        enqueued += await queue.enqueue(session, item_id, step_name, version, chain=False)
    await session.commit()
    return ReindexOut(step=step_name, version=version, enqueued=enqueued)


@router.post("/retry-failed")
async def retry_failed(session: Session, _: Authed) -> dict[str, int]:
    count = await queue.retry_failed(session)
    await session.execute(
        update(Item)
        .where(Item.status == ItemStatus.failed)
        .values(status=ItemStatus.pending, error=None)
    )
    await session.commit()
    return {"requeued": count}


@router.get("/status")
async def status_page(session: Session, _: Authed) -> dict[str, Any]:
    """Queue health, failures with their errors, and cost and time per enrichment step."""
    queue_rows = await session.execute(
        select(Job.step, Job.status, func.count()).group_by(Job.step, Job.status)
    )
    queue_depth: dict[str, dict[str, int]] = {}
    for step, st, n in queue_rows:
        queue_depth.setdefault(step, {})[st] = n

    failed = await session.execute(
        select(
            Job.id,
            Job.item_id,
            Job.step,
            Job.error,
            Job.attempts,
            Job.finished_at,
            Item.title,
            Item.source_url,
        )
        .join(Item, Item.id == Job.item_id, isouter=True)
        .where(Job.status == JobStatus.failed)
        .order_by(Job.finished_at.desc())
        .limit(50)
    )
    costs = await session.execute(
        text(
            "SELECT step, count(*) AS runs, round(avg(ms)) AS avg_ms, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY ms) AS p95_ms, "
            "round(avg(tokens)) AS avg_tokens, sum(cost) AS total_cost, "
            "count(*) FILTER (WHERE output ? 'error') AS errors, "
            "mode() WITHIN GROUP (ORDER BY model) AS model "
            "FROM enrichments WHERE created_at > now() - interval '30 days' GROUP BY step ORDER BY step"
        )
    )
    pipeline = await session.execute(
        text(
            "SELECT step, count(*) AS runs, round(avg(ms)) AS avg_ms, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY ms) AS p95_ms FROM jobs "
            "WHERE status = 'done' AND finished_at > now() - interval '30 days' GROUP BY step ORDER BY step"
        )
    )
    # Save-to-ready time per item: the milestone 3 exit metric (p95 under 30 s).
    ready = (
        await session.execute(
            text(
                "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY s) AS p50, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY s) AS p95 FROM ("
                "SELECT extract(epoch FROM min(j.finished_at) - i.saved_at) AS s FROM items i "
                "JOIN jobs j ON j.item_id = i.id AND j.step = 'index' AND j.status = 'done' "
                "WHERE i.saved_at > now() - interval '30 days' AND i.capture <> 'import' GROUP BY i.id) t"
            )
        )
    ).one()
    counts = await session.execute(
        select(Item.type, Item.status, func.count()).group_by(Item.type, Item.status)
    )
    s = get_settings()
    return {
        "queue": queue_depth,
        "failed": [dict(r._mapping) for r in failed],
        "enrichment": [dict(r._mapping) for r in costs],
        "pipeline": [dict(r._mapping) for r in pipeline],
        "save_to_ready_s": {"p50": ready.p50, "p95": ready.p95},
        "items": [{"type": t, "status": st, "count": n} for t, st, n in counts],
        "resurfacing": await resurface.open_rate(session),
        "capabilities": {
            "llm": f"{s.llm_provider}:{s.llm_model}" if s.llm_provider != "none" else None,
            "embeddings": f"{s.embed_provider}:{s.embed_model}",
            "vision": s.clip_image_model if s.vision_enabled else None,
            "ocr": ocr_available(),
            "whisper": whisper_available(),
            "browser": s.browser_enabled,
            "external_providers": sorted({s.llm_provider, s.embed_provider} & {"openai"}),
        },
    }


@router.get("/settings/models")
async def get_models(session: Session, _: Authed) -> dict[str, Any]:
    """Model per LLM step. Steps without an override use the install defaults."""
    row = await session.get(AppSetting, "models")
    s = get_settings()
    return {
        "defaults": {"provider": s.llm_provider, "model": s.llm_model},
        "steps": ["summary", "tags", "entities", "caption", "query"],
        "overrides": row.value if row else {},
        "embeddings": {"provider": s.embed_provider, "model": s.embed_model, "dim": s.embed_dim},
    }


@router.put("/settings/models/{step}")
async def set_model(
    step: str, choice: ModelChoiceIn, session: Session, _: Authed
) -> dict[str, Any]:
    if step not in {"summary", "tags", "entities", "caption", "query"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown step {step}")
    row = await session.get(AppSetting, "models")
    value = {**(row.value if row else {}), step: choice.model_dump()}
    if row:
        row.value = value
    else:
        session.add(AppSetting(key="models", value=value))
    await session.commit()
    adapter.invalidate_overrides()
    return value


@router.delete("/settings/models/{step}")
async def reset_model(step: str, session: Session, _: Authed) -> dict[str, Any]:
    row = await session.get(AppSetting, "models")
    value = {k: v for k, v in (row.value if row else {}).items() if k != step}
    if row:
        row.value = value
        await session.commit()
    adapter.invalidate_overrides()
    return value


@router.get("/settings/digest", response_model=DigestSettings)
async def get_digest(session: Session, _: Authed) -> DigestSettings:
    row = await session.get(AppSetting, "digest")
    return DigestSettings(**(row.value if row else {}))


@router.put("/settings/digest", response_model=DigestSettings)
async def set_digest(body: DigestSettings, session: Session, _: Authed) -> DigestSettings:
    row = await session.get(AppSetting, "digest")
    value = {**(row.value if row else {}), **body.model_dump(exclude={"last_sent"})}
    if row:
        row.value = value
    else:
        session.add(AppSetting(key="digest", value=value))
    await session.commit()
    return DigestSettings(**value)
