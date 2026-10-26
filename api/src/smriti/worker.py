"""The workflow runner: claims jobs, runs steps with timeouts and retries, chains the next step."""

import asyncio
import contextlib
import logging
import signal
import time
from datetime import timedelta

import asyncpg

from smriti.config import get_settings
from smriti.db import asyncpg_dsn, get_sessionmaker
from smriti.jobs import queue
from smriti.logs import current_item_id, current_step, setup_logging
from smriti.models import Item, ItemStatus, Job
from smriti.notify import publish
from smriti.pipeline import workflow
from smriti.pipeline.context import PermanentError, StepContext, StepSkipped
from smriti.telemetry import setup_tracing, span

log = logging.getLogger("smriti.worker")
STALE_AFTER = timedelta(minutes=20)


async def run_job(job: Job) -> None:
    current_item_id.set(str(job.item_id) if job.item_id else None)
    current_step.set(job.step)
    step = workflow.get_step(job.step)
    maker = get_sessionmaker()
    started = time.perf_counter()
    error: str | None = None
    permanent = False

    if step is None:
        error, permanent = f"unknown step {job.step}", True
    else:
        async with maker() as session:
            ctx: StepContext | None = None
            try:
                ctx = await StepContext.load(session, job.item_id) if job.item_id else None
                if ctx is None:
                    raise StepSkipped("item was deleted")
                with span(f"step.{job.step}", item_id=str(job.item_id), version=job.version):
                    async with asyncio.timeout(step.timeout_s):
                        await step.run(ctx)
            except StepSkipped as e:
                log.info("skipped: %s", e)
                if ctx is None:  # deleted item: finish the job, nothing to chain
                    await queue.complete(session, job.id, 0)
                    await session.commit()
                    return
            except Exception as e:  # noqa: BLE001 - every failure is recorded on the job
                await session.rollback()
                permanent = isinstance(e, PermanentError)
                error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                log.warning("step failed: %s", error, exc_info=not permanent)

            if error is None:
                ms = int((time.perf_counter() - started) * 1000)
                await queue.complete(session, job.id, ms)
                await workflow.advance(session, job)
                await publish(session, job.item_id, ctx.item.status, step=job.step)
                await session.commit()
                log.info("step done", extra={"data": {"ms": ms}})
                return

    async with maker() as session:
        if permanent:
            job.attempts = job.max_attempts
        final = await queue.fail(session, job, error)
        if final and step and step.optional:
            # The item is still useful without this step; carry on with the workflow.
            await workflow.advance(session, job)
        elif final and job.item_id and (item := await session.get(Item, job.item_id)):
            item.status = ItemStatus.failed
            item.error = f"{job.step}: {error}"[:2000]
            await publish(session, item.id, item.status, step=job.step, error=item.error)
        await session.commit()


async def run_until_idle(concurrency: int = 4) -> int:
    """Process jobs until the queue is empty. Used by tests and `smriti work --once`."""
    processed = 0
    while True:
        async with get_sessionmaker()() as session:
            jobs = await queue.claim(session, concurrency)
        if not jobs:
            return processed
        await asyncio.gather(*(run_job(j) for j in jobs))
        processed += len(jobs)


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.wake = asyncio.Event()
        self.stopping = asyncio.Event()
        self.running: set[asyncio.Task[None]] = set()

    async def _listen(self) -> None:
        while not self.stopping.is_set():
            try:
                conn = await asyncpg.connect(asyncpg_dsn())
                await conn.add_listener(queue.JOBS_CHANNEL, lambda *_: self.wake.set())
                await self.stopping.wait()
                await conn.close()
            except (OSError, asyncpg.PostgresError) as e:
                log.warning("job listener reconnecting: %s", e)
                await asyncio.sleep(2)

    async def _housekeeping(self) -> None:
        from smriti.resurface import maybe_send_digest

        while not self.stopping.is_set():
            async with get_sessionmaker()() as session:
                if reaped := await queue.reap(session, STALE_AFTER):
                    log.warning("requeued %d stale jobs", reaped)
            try:
                await maybe_send_digest()
            except Exception:
                log.exception("digest failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stopping.wait(), 300)

    async def run(self) -> None:
        concurrency = self.settings.worker_concurrency
        background = [
            asyncio.create_task(self._listen()),
            asyncio.create_task(self._housekeeping()),
        ]
        log.info("worker started", extra={"data": {"concurrency": concurrency}})
        while not self.stopping.is_set():
            free = concurrency - len(self.running)
            jobs: list[Job] = []
            if free > 0:
                async with get_sessionmaker()() as session:
                    jobs = await queue.claim(session, free)
                for job in jobs:
                    task = asyncio.create_task(run_job(job))
                    self.running.add(task)
                    task.add_done_callback(self._finished)
            if not jobs:
                self.wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), self.settings.poll_interval_s * 10)
        if self.running:
            await asyncio.wait(self.running, timeout=60)
        for task in background:
            task.cancel()

    def _finished(self, task: asyncio.Task[None]) -> None:
        self.running.discard(task)
        self.wake.set()
        if not task.cancelled() and (exc := task.exception()):
            log.error("job crashed", exc_info=exc)


def main() -> None:
    setup_logging()
    setup_tracing("smriti-worker")
    worker = Worker()

    async def _main() -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, worker.stopping.set)
        await worker.run()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
