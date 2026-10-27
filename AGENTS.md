# AGENTS.md

Guidance for coding agents working in this repo. The README covers what Smriti is. `docs/architecture.md` explains how it works.

## Layout

```
api/         FastAPI app, workflow runner, CLI (`smriti`), Alembic migrations, tests
web/         Next.js 15 app and PWA
extension/   MV3 browser extension for Chrome and Firefox (plain JS, no build step)
docs/        Architecture, models, capture, deployment, benchmarks, status
```

Key places in `api/src/smriti/`:

- `pipeline/workflow.py`: the step chain (classify → fetch → extract → snapshot → enrich → index).
- `pipeline/extractors/`: one module per content type.
- `pipeline/enrich.py`: summary, tags, entities, embeddings and images, each run as a versioned enricher.
- `jobs/queue.py`: a Postgres `SKIP LOCKED` job queue.
- `search/`: query parser and fusion.
- `resurface.py`: home strip, digest, on-this-day and serendipity.
- `ml/`: the model adapter (fastembed, Ollama, OpenAI-compatible) and the no-LLM heuristics.

## Setup

You need Postgres 16+ with the `vector` extension, Python 3.12 with `uv`, and Node 22.

```sh
createdb smriti && createdb smriti_test
cd api && uv sync --extra ocr && uv run smriti migrate
uv run smriti serve --reload    # API on :8000
uv run smriti work              # worker
cd web && npm install && npm run dev   # web on :3000
```

The API reads `SMRITI_*` environment variables (see `.env.example` and `api/src/smriti/config.py`). Locally you need at least `SMRITI_DATABASE_URL`, `SMRITI_OWNER_SECRET` and `SMRITI_STORAGE_DIR`.

## Checks to run before pushing

These are the same checks CI runs (`.github/workflows/ci.yml`):

```sh
# api/
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q                   # uses SMRITI_TEST_DATABASE_URL, default .../smriti_test

# web/
npm run typecheck
npm run build
```

If you change an API route or schema, regenerate the client types and commit both files. CI fails if they drift:

```sh
cd api && uv run python scripts/export_openapi.py ../web/src/lib/openapi.json
cd web && npm run gen:api
```

CI also runs the search eval (`smriti eval`, which must keep recall@10 ≥ 0.95 and MRR ≥ 0.75). Run it if you touch ranking, the query parser or embeddings.

## Rules that are easy to break

- **Steps are versioned and idempotent.** Job keys are `item:step:vN`. When you change what a step or enricher produces, bump its `version` so old items can be re-run (`/admin/reindex`). A step must be safe to run twice. Re-running `extract` replaces what the previous run extracted and keeps existing images if every download fails. Keep it that way.
- **Reassign JSONB, don't mutate it.** `item.meta = {**item.meta, ...}`. SQLAlchemy does not track in-place edits.
- **Schema changes go through Alembic** (`api/migrations/versions/`). Never edit an applied migration.
- **The app must work with no LLM.** Every enricher has a heuristic fallback in `ml/heuristics.py`. Steps that can send data off the machine are labelled in Settings.
- **The web client is typed from OpenAPI.** Use `api` from `web/src/lib/api.ts`, not raw `fetch` (file uploads and export are the exceptions).
- **Design tokens live in `web/src/app/globals.css`** (`@theme`, with a dark override under `[data-theme="dark"]`). Use the tokens (`bg-card`, `text-ink`, `text-muted`, `text-accent`, `text-brand`) instead of raw colors, and check every UI change in both themes and at phone width (390px).
- **Fonts:** Fraunces is self-hosted as a subset (`web/src/fonts/`). Don't swap it for the Google Fonts version.
- **Don't cache pages in the service worker** (`web/public/sw.js`). It only handles the share target.

## Conventions

- Match the surrounding code: comment density, naming and idiom. Add a comment only when the reason for a choice isn't obvious.
- Keep commits small and focused, with a plain-English imperative subject ("Keep tweet authors out of their tags").
- Don't add AI co-author trailers or attribution to commits or PRs.
- Work on `develop` and open PRs into `main`.
- Write user-facing copy in plain words: short sentences, no em dashes, no marketing tone.
