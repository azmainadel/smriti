"""Search evaluation (recall@10, MRR on a fixed query set) and latency benchmarks.

Both can wipe the database they run against, so loading refuses to run unless the
database name contains "test", "eval" or "bench".
"""

import asyncio
import json
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.engine import make_url

from smriti import items as item_service
from smriti.config import get_settings
from smriti.db import asyncpg_dsn, get_engine, get_sessionmaker
from smriti.ml.hashing import hash_embed
from smriti.models import AppSetting
from smriti.schemas import ItemCreate
from smriti.search.service import search
from smriti.worker import run_until_idle

TABLES = "items, tags, entities, events, jobs, app_settings"


def _guard() -> None:
    name = make_url(get_settings().database_url).database or ""
    if not any(w in name for w in ("test", "eval", "bench")):
        raise SystemExit(
            f"refusing to wipe database {name!r}: use one named *test*, *eval* or *bench*"
        )


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


async def load_corpus(path: Path) -> dict[str, str]:
    _guard()
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    keys: dict[str, str] = {}
    async with get_sessionmaker()() as session:
        for line in (await asyncio.to_thread(path.read_text)).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            saved_at = datetime.now(UTC) - timedelta(days=row.get("age_days", 30))
            data = ItemCreate(
                url=row.get("url"),
                text=row.get("text") if not row.get("url") else None,
                html=row.get("html"),
                title=row.get("title"),
                note=row.get("note"),
                capture="extension" if row.get("html") else "cli",
                saved_at=saved_at,
            )
            item = await item_service.save(session, data)
            keys[row["key"]] = str(item.id)
        session.add(AppSetting(key="eval_keys", value=keys))
        await session.commit()
    await run_until_idle(concurrency=8)
    return keys


async def run_eval(dataset: Path, *, load: bool = False, k: int = 10) -> dict[str, Any]:
    if load:
        keys = await load_corpus(dataset / "corpus.jsonl")
    else:
        async with get_sessionmaker()() as session:
            row = await session.get(AppSetting, "eval_keys")
            if row is None:
                raise SystemExit("no eval corpus loaded: run with --load")
            keys = row.value
    by_id = {v: key for key, v in keys.items()}

    results = []
    async with get_sessionmaker()() as session:
        queries = await asyncio.to_thread((dataset / "queries.jsonl").read_text)
        for line in queries.splitlines():
            if not line.strip():
                continue
            q = json.loads(line)
            started = time.perf_counter()
            res = await search(session, q["q"], limit=50, use_llm=False)
            ms = (time.perf_counter() - started) * 1000
            ranked = [by_id.get(str(h.item.id)) for h in res.hits]
            targets = set(q["targets"])
            found = targets & set(ranked[:k])
            first = next((i + 1 for i, key in enumerate(ranked) if key in targets), None)
            results.append(
                {
                    "q": q["q"],
                    "kind": q.get("kind", "other"),
                    "targets": sorted(targets),
                    "top": ranked[:5],
                    "recall": len(found) / len(targets),
                    "rr": 1 / first if first else 0.0,
                    "ms": round(ms, 1),
                }
            )

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "queries": len(rows),
            f"recall@{k}": round(statistics.mean(r["recall"] for r in rows), 3) if rows else 0,
            "mrr": round(statistics.mean(r["rr"] for r in rows), 3) if rows else 0,
            "p50_ms": round(_pct([r["ms"] for r in rows], 50), 1),
            "p95_ms": round(_pct([r["ms"] for r in rows], 95), 1),
        }

    kinds = sorted({r["kind"] for r in results})
    summary = summarize(results) | {
        "by_kind": {kind: summarize([r for r in results if r["kind"] == kind]) for kind in kinds}
    }
    summary["embeddings"] = f"{get_settings().embed_provider}:{get_settings().embed_model}"
    return {
        "summary": summary,
        "misses": [r for r in results if r["recall"] < 1],
        "results": results,
    }


# ---------- latency benchmark ----------

_SYLLABLES = [
    "ka",
    "ri",
    "to",
    "na",
    "mi",
    "su",
    "re",
    "lo",
    "ve",
    "da",
    "shi",
    "po",
    "mu",
    "te",
    "ga",
    "ni",
    "yo",
    "ra",
    "be",
    "ku",
    "zo",
    "fe",
    "li",
    "an",
    "or",
]


def _vocabulary(n: int, rng: random.Random) -> list[str]:
    words: set[str] = set()
    while len(words) < n:
        words.add("".join(rng.choice(_SYLLABLES) for _ in range(rng.randint(2, 4))))
    return sorted(words)


async def seed_synthetic(n: int, seed: int = 7) -> list[str]:
    """Bulk-insert n synthetic items with content and vectors, bypassing the workflow."""
    _guard()
    rng = random.Random(seed)
    vocab = _vocabulary(5000, rng)
    dim = get_settings().embed_dim
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    conn = await asyncpg.connect(asyncpg_dsn())
    try:
        now = datetime.now(UTC)
        types = ["article", "article", "article", "note", "tweet", "video", "pdf", "image"]
        for start in range(0, n, 2000):
            batch = range(start, min(n, start + 2000))
            items, contents, chunks = [], [], []
            for _ in batch:
                item_id = uuid.uuid4()
                # Zipf-ish topic words make some terms common and most rare, like real text.
                words = [
                    vocab[min(int(rng.paretovariate(1.1)) * 7 + rng.randint(0, 6), len(vocab) - 1)]
                    for _ in range(120)
                ]
                title = " ".join(words[:6])
                body = " ".join(words)
                saved = now - timedelta(days=rng.uniform(0, 1500))
                items.append(
                    (
                        item_id,
                        rng.choice(types),
                        "ready",
                        title,
                        saved,
                        saved,
                        json.dumps({}),
                        0,
                        "web",
                    )
                )
                contents.append((item_id, title, "", body))
                chunks.append((item_id, 0, "item", title, str(hash_embed(title, dim)), "hash"))
                chunks.append((item_id, 1, "section", body, str(hash_embed(body, dim)), "hash"))
            await conn.executemany(
                "INSERT INTO items (id, type, status, title, saved_at, updated_at, meta, open_count, capture) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)",
                items,
            )
            await conn.executemany(
                "INSERT INTO item_content (item_id, title, extra, text) VALUES ($1, $2, $3, $4)",
                contents,
            )
            await conn.executemany(
                "INSERT INTO chunks (item_id, ordinal, kind, text, embedding, embed_model) VALUES ($1, $2, $3, $4, $5::vector, $6)",
                chunks,
            )
        await conn.execute("ANALYZE")
    finally:
        await conn.close()
    return vocab


async def run_bench(n_items: int, n_queries: int, seed_db: bool) -> dict[str, Any]:
    rng = random.Random(11)
    vocab = await seed_synthetic(n_items) if seed_db else _vocabulary(5000, random.Random(7))
    total, retrieval = [], []
    async with get_sessionmaker()() as session:
        for _ in range(5):  # warm caches and the connection pool
            await search(session, rng.choice(vocab), use_llm=False)
        for _ in range(n_queries):
            q = " ".join(
                vocab[min(int(rng.paretovariate(1.1)) * 7, len(vocab) - 1)]
                for _ in range(rng.randint(1, 3))
            )
            started = time.perf_counter()
            res = await search(session, q, use_llm=False)
            ms = (time.perf_counter() - started) * 1000
            total.append(ms)
            retrieval.append(ms - res.timings.get("embed", 0))
    return {
        "items": n_items,
        "queries": n_queries,
        "embeddings": f"{get_settings().embed_provider}:{get_settings().embed_model}",
        "p50_ms": round(_pct(total, 50), 1),
        "p95_ms": round(_pct(total, 95), 1),
        "p95_ms_excluding_query_embedding": round(_pct(retrieval, 95), 1),
    }
