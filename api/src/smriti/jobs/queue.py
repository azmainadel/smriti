"""A Postgres job queue on `FOR UPDATE SKIP LOCKED`.

This stands in for lazarus until it exists; the runner only uses `enqueue`, `claim`,
`complete`, `fail` and `reap`, so swapping the backend touches this file alone.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from smriti.models import Job, JobStatus

JOBS_CHANNEL = "smriti_jobs"


def idempotency_key(item_id: uuid.UUID | None, step: str, version: int, suffix: str = "") -> str:
    key = f"{item_id or '-'}:{step}:v{version}"
    return f"{key}:{suffix}" if suffix else key


async def enqueue(
    session: AsyncSession,
    item_id: uuid.UUID | None,
    step: str,
    version: int,
    *,
    chain: bool = True,
    max_attempts: int = 3,
    key_suffix: str = "",
    run_after: datetime | None = None,
) -> bool:
    """Add a step to the queue. Returns False if a job with the same key already exists."""
    values = {
        "item_id": item_id,
        "step": step,
        "version": version,
        "idempotency_key": idempotency_key(item_id, step, version, key_suffix),
        "chain": chain,
        "max_attempts": max_attempts,
    }
    if run_after:
        values["run_after"] = run_after
    result = await session.execute(
        insert(Job).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    await session.execute(text(f"NOTIFY {JOBS_CHANNEL}"))
    return bool(result.rowcount)


async def claim(session: AsyncSession, limit: int) -> list[Job]:
    ready = (
        select(Job.id)
        .where(Job.status == JobStatus.queued, Job.run_after <= func.now())
        .order_by(Job.run_after, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(
        update(Job)
        .where(Job.id.in_(ready.scalar_subquery()))
        .values(status=JobStatus.running, locked_at=func.now(), attempts=Job.attempts + 1)
        .returning(Job)
    )
    jobs = list(result.scalars())
    await session.commit()
    return jobs


async def complete(session: AsyncSession, job_id: int, ms: int) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.done, finished_at=func.now(), ms=ms, error=None, locked_at=None)
    )


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(5 * 2 ** (attempt - 1), 600))


async def fail(session: AsyncSession, job: Job, error: str) -> bool:
    """Record a failure. Returns True if the job is out of retries."""
    final = job.attempts >= job.max_attempts
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status=JobStatus.failed if final else JobStatus.queued,
            error=error[:4000],
            locked_at=None,
            finished_at=func.now() if final else None,
            run_after=datetime.now(UTC) + backoff(job.attempts),
        )
    )
    return final


async def reap(session: AsyncSession, stale_after: timedelta) -> int:
    """Requeue jobs whose worker died mid-step."""
    result = await session.execute(
        update(Job)
        .where(Job.status == JobStatus.running, Job.locked_at < func.now() - stale_after)
        .values(status=JobStatus.queued, locked_at=None)
    )
    await session.commit()
    return result.rowcount


async def retry_failed(session: AsyncSession, item_id: uuid.UUID | None = None) -> int:
    where = [Job.status == JobStatus.failed]
    if item_id:
        where.append(Job.item_id == item_id)
    result = await session.execute(
        update(Job)
        .where(and_(*where))
        .values(status=JobStatus.queued, attempts=0, run_after=func.now(), error=None)
    )
    await session.execute(text(f"NOTIFY {JOBS_CHANNEL}"))
    return result.rowcount


async def forget(session: AsyncSession, step: str, version: int) -> None:
    """Drop finished jobs for a step+version so a forced re-run can enqueue them again."""
    await session.execute(
        delete(Job).where(Job.step == step, Job.version == version, Job.status != JobStatus.running)
    )
