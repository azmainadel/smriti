"""The ingestion workflow: an ordered chain of idempotent, versioned steps.

Bump a step's version to re-run only that step for old items (`smriti backfill`).
Job idempotency keys are item_id + step + version, so retries and duplicate enqueues
never produce a half-saved item or a duplicate.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from smriti.jobs import queue
from smriti.models import Job
from smriti.pipeline.classify import classify
from smriti.pipeline.context import Step, StepContext
from smriti.pipeline.enrich import ENRICHERS, enrich_all, run_enricher
from smriti.pipeline.extract import extract
from smriti.pipeline.fetch import fetch
from smriti.pipeline.index import index
from smriti.pipeline.snapshot import snapshot


class EnrichmentIncomplete(Exception):
    pass


async def _enrich(ctx: StepContext) -> None:
    # Sub-steps use their own sessions; commit what this step loaded so they see it.
    await ctx.session.commit()
    if errors := await enrich_all(ctx.item.id):
        raise EnrichmentIncomplete("; ".join(errors))


STEPS: list[Step] = [
    Step("classify", 1, classify, timeout_s=20),
    Step("fetch", 1, fetch, timeout_s=90),
    Step("extract", 1, extract, timeout_s=600),
    Step("snapshot", 1, snapshot, timeout_s=120, max_attempts=2, optional=True),
    Step("enrich", 1, _enrich, timeout_s=900, optional=True),
    Step("index", 1, index, timeout_s=30),
]
BY_NAME = {s.name: s for s in STEPS}


def enricher_step(name: str) -> Step:
    """A single enrichment sub-step as a job, used by bulk re-runs."""
    enricher = ENRICHERS[name]

    async def _run(ctx: StepContext) -> None:
        await ctx.session.commit()
        if error := await run_enricher(ctx.item.id, enricher, force=True):
            raise EnrichmentIncomplete(error)

    return Step(f"enrich.{name}", enricher.version, _run, timeout_s=600)


def get_step(name: str) -> Step | None:
    if name.startswith("enrich."):
        sub = name.removeprefix("enrich.")
        return enricher_step(sub) if sub in ENRICHERS else None
    return BY_NAME.get(name)


def next_step(name: str) -> Step | None:
    i = [s.name for s in STEPS].index(name)
    return STEPS[i + 1] if i + 1 < len(STEPS) else None


async def start(session: AsyncSession, item_id: uuid.UUID) -> None:
    first = STEPS[0]
    await queue.enqueue(
        session, item_id, first.name, first.version, max_attempts=first.max_attempts
    )


async def advance(session: AsyncSession, job: Job) -> None:
    """Enqueue what follows a finished job.

    A chained job continues the workflow. An unchained one (a backfill of one step, or a
    re-enrichment) only refreshes the search fields: index is cheap and derived, so it
    re-runs under a fresh key.
    """
    if job.item_id is None:
        return
    if job.chain:
        step = next_step(job.step)
        if step:
            await queue.enqueue(
                session, job.item_id, step.name, step.version, max_attempts=step.max_attempts
            )
    elif job.step != "index":
        step = BY_NAME["index"]
        await queue.enqueue(
            session, job.item_id, step.name, step.version, key_suffix=f"after-{job.id}"
        )
