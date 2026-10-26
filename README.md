# Smriti

স্মৃতি means "memory". Smriti is a self-hosted, single-user library for everything you save: links, articles, tweets, videos, PDFs, images, quotes and notes. You find things again by what they were about, not by which folder you put them in.

- **Save in one action.** Browser extension, phone share sheet, email, drag and drop, or the CLI. A card shows up at once and fills in over the next few seconds.
- **Keeps the real content.** Every save is fetched, extracted and archived, so a dead link loses nothing.
- **Finds vague things.** "that blue chart about retention" works: keyword, semantic, visual and color search run together, and filters like "videos", "from March" or "on twitter" are read out of the query.
- **Brings things back.** A "from your past" strip, related items in the reader, and a weekly digest, each with the reason the item came back.
- **Runs on one machine.** `docker compose up`. Nothing leaves it unless you point a step at an external model.

## Quick start

```sh
cp .env.example .env
# set SMRITI_OWNER_SECRET and SMRITI_SIGNING_KEY, e.g. with: openssl rand -hex 32
docker compose up -d
```

Open http://localhost:3000 and enter the owner secret. The first screen offers to import browser bookmarks, Pocket or Raindrop.

Local LLMs for summaries, tags and entities are optional:

```sh
docker compose --profile ollama up -d
docker compose exec ollama ollama pull qwen2.5:3b-instruct
# then set SMRITI_LLM_PROVIDER=ollama in .env and restart api and worker
```

Without an LLM, Smriti uses extractive summaries and keyword tags, so a fresh install still works.

## How it fits together

```
 extension ─┐
 share sheet┤                 ┌──────────────┐     ┌──────────────────┐
 email ─────┼──► FastAPI ────►│  Postgres 17 │◄────│ workflow runner  │──► fetch, extract,
 CLI ───────┤    (saves in    │  + pgvector  │     │ (SKIP LOCKED     │    snapshot, enrich,
 web app ◄──┘     <1 s)       │  jobs table  │     │  queue)          │    index
     ▲                        └──────────────┘     └──────────────────┘
     └──── server-sent events: cards fill in live        │
                                files ◄───────────────────┘ originals, archives, images
```

The API never does heavy work inline. Saving writes a row and enqueues a workflow; the worker runs six idempotent steps (`classify`, `fetch`, `extract`, `snapshot`, `enrich`, `index`) and the API pushes each status change to the browser. More in [docs/architecture.md](docs/architecture.md).

| Part | Stack |
| --- | --- |
| Web | Next.js 15, TypeScript, Ark UI, Tailwind v4, Motion, TanStack Query, installable PWA |
| API and worker | FastAPI, Python 3.12, Pydantic v2, SQLAlchemy 2, Alembic |
| Storage | Postgres 17 with pgvector; files on a volume or any S3-compatible store |
| Models | One adapter over Ollama, any OpenAI-compatible API and local ONNX models (fastembed), cached by input hash |
| Capture | MV3 extension (Chrome, Firefox), PWA share target, iOS Shortcut, inbound email, CLI |

## Numbers

Measured on a 4 vCPU cloud container, October 2026. Reproduce with the commands in [docs/benchmarks.md](docs/benchmarks.md).

| What | Result |
| --- | --- |
| Search latency, 50,000 items | p50 56 ms, p95 85 ms (retrieval only; a bge-small query embedding adds about 4 ms) |
| Seed eval set, 70 queries over 36 items, bge-small | recall@10 1.00, MRR 0.83 (paraphrases: MRR 0.66) |
| Save to ready, 17 real saves, no LLM, CLIP on | p50 7 s, p95 52 s (the tail is the worker's first run loading the image model) |

The seed eval set is small and synthetic, so recall@10 is close to meaningless at this size. It exists to catch ranking regressions in CI. The target in the spec is 200 real queries from personal use; `smriti eval` runs any set in the same format.

## Repository

```
api/         FastAPI app, workflow runner, CLI, migrations, tests, eval set
web/         Next.js app (grid, search, reader, digest, settings, share target)
extension/   Browser extension
docs/        Architecture, models, capture, deployment, benchmarks, status against the spec
```

## Development

```sh
# API: needs Postgres with pgvector
cd api
uv sync --extra ocr
createdb smriti && createdb smriti_test
uv run smriti migrate
uv run smriti serve --reload      # http://localhost:8000/docs
uv run smriti work                # the workflow runner
uv run pytest

# Web
cd web
npm install
npm run dev                       # http://localhost:3000
npm run gen:api                   # after API changes: regenerate types from the OpenAPI schema
```

`api/scripts/export_openapi.py` writes the schema the web app's types come from. CI fails if either is stale.

## Status

Milestones 1 to 4 of the spec are built, with parts of 5 and 6. [docs/status.md](docs/status.md) lists what is done, what is partial and what is missing, item by item.

## License

MIT
