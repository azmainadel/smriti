# Architecture

Clients only capture and display. The API answers fast and never does heavy work inline. The worker does fetching, extraction and enrichment in the background, and Postgres holds everything except files.

## Saving

`POST /items` writes an `items` row with `status: pending`, stores any HTML the extension sent, enqueues the first workflow step and returns. That takes a few milliseconds. The same transaction sends a `pg_notify`, so the web app shows the card before the response arrives at the extension.

## The workflow

`api/src/smriti/pipeline/workflow.py` defines six steps. Each is a function of the item, versioned, with its own timeout and retry budget.

| Step | Does | Optional |
| --- | --- | --- |
| `classify` | Type from URL patterns, MIME type and a HEAD request | no |
| `fetch` | Download the page or file to storage; headless Chromium for JS-rendered pages | no |
| `extract` | The type's extractor (see below); downloads up to 8 images as assets | no |
| `snapshot` | Self-contained HTML archive with inlined CSS and images; a screenshot when Chromium is on | yes |
| `enrich` | Summary, tags, entities, image analysis in parallel, then embeddings and dedup | yes |
| `index` | Copies title, note, tags, entities and captions into the weighted search fields; marks the item ready | no |

A failed optional step is logged and the workflow continues. A required step that runs out of retries marks the item `failed` and keeps whatever was saved; the card offers a retry.

### Jobs and idempotency

`jobs` is a plain Postgres queue: workers claim rows with `FOR UPDATE SKIP LOCKED`, a `NOTIFY` wakes idle workers, and a reaper requeues jobs whose worker died. Every job has an idempotency key of `item_id:step:version`, so enqueueing a finished step again does nothing. The runner touches the queue only through `jobs/queue.py`, so moving to lazarus later changes one file.

Bumping a step's version and calling `POST /admin/reindex {"step": "extract"}` re-runs that step for items whose last run used an older version. A re-run continues downstream under a fresh key suffix, so a re-extracted item is also re-enriched and re-indexed.

Each enrichment output stores a fingerprint of its inputs (title, note, text, asset keys). An enricher skips an item when the version and the fingerprint both match, so re-running the workflow costs nothing for unchanged items, and a page whose text changed gets new summaries without a version bump.

### Live updates

The worker publishes `{id, status, step}` on the `smriti_items` channel after every step. One `LISTEN` connection per API process fans out to the `/stream` server-sent events endpoint. The web app refetches the card (`GET /items/{id}/card`) when a step that changes what the card shows lands.

## Extractors

| Type | Source | Notes |
| --- | --- | --- |
| Article | trafilatura on the fetched or extension-sent HTML | Lazy-load attributes are promoted to `src` first; little text plus a description marks the page as partial (paywall) |
| Product | JSON-LD `Product`, then OpenGraph product tags | Checked before article extraction |
| Tweet or thread | The DOM the extension captured, else the fxtwitter mirror | Walks self-replies up to 25 posts; keeps quoted tweets and media |
| YouTube | oEmbed, the watch page's player response, captions | Chapters from the description; transcript grouped into one-minute paragraphs under chapter headings |
| Audio and video files | faster-whisper when installed | Optional `audio` extra |
| PDF | pypdf in layout mode, pdfium for rendering | Pages without a text layer are rendered and OCRed; first page becomes the thumbnail; title guessed from page 1 when metadata has none |
| Image | Stored as is | OCR, caption, colors and hashes happen in enrichment |
| Note, quote, palette | Stored as is | Quotes keep their attribution; a note made only of hex codes is a palette |

PDFs go through a `PdfParser` protocol so the layout-aware parser (project #4) can replace pypdf without touching the pipeline.

## Chunking

Every extractor produces clean structured HTML. Chunks follow its headings: a section is a heading plus the paragraphs under it, split at sentence boundaries past 1,200 characters. Blockquotes, code blocks and figure captions become their own chunks. Each item also gets one "item" vector from its title, note, description and summary, which resurfacing and the related-items rail use.

## Search

`search/service.py` runs up to four retrievers in parallel, each on its own connection, all sharing one filter clause:

1. **Keyword.** Postgres full-text search on a generated `tsvector`: title, note and tags weighted A, body B, OCR text C. The last word is a prefix match, so results update while typing. AND first, OR only when AND finds almost nothing. Ranking reads every matching row, so it stops at 3,000 matches.
2. **Semantic.** Query embedding against chunk embeddings (pgvector HNSW, cosine), collapsed to items.
3. **Visual.** The query's CLIP text embedding against image embeddings, when vision is on.
4. **Color.** CIELAB distance between query colors and item palettes, discounted by swatch weight, when the query names a color.

Lists are fused with reciprocal rank fusion (k = 60), then multiplied by a small boost for recency, how often the user opened the item, an exact phrase match and the presence of a note. A cross-encoder re-rank of the top 50 sits behind `SMRITI_SEARCH_RERANK_CROSS_ENCODER` so its cost can be measured against the eval set. If filters leave nothing, the search runs again without them and says so.

The vector retriever goes through a `VectorIndex` protocol; `PgVectorIndex` is the only implementation today.

### Query parsing

`search/query_parser.py` reads filters out of the query with rules: types ("videos", "papers", "screenshots"), dates ("from March", "last spring", "3 weeks ago", "since 2024"), sources ("on twitter", "from nytimes.com"), colors (lowercase color words only, so "Blue Origin" stays text), tags (`#design`, "tagged design") and "with notes". Each filter comes back as a chip with its character span in the query; removing a chip cuts that span out. When leftover words still look like a date the rules could not read ("around christmas"), the step's LLM gets 400 ms to try.

## Resurfacing

`resurface.py` scores candidates on three signals:

- **Relevance:** cosine similarity to items saved or opened in the last 7 days.
- **Forgetting:** `1 - exp(-days_since_seen / interval)`, where the interval starts at 7 days and grows 2.2x with every open or resurface, like spaced repetition.
- **Importance:** has a note, opened more than once, saved from a highlight.

Score = `(0.5 relevance + 0.3 forgetting + 0.2 importance) x 0.5^dismissals`. Anything shown on an earlier day in the last 14 days is excluded. The digest weights forgetting higher. Picks are diversified so the strip does not show three items for the same reason. Each pick carries a reason built from its strongest signal, for example "Related to the 3 articles on retrieval you saved this week".

Every surface logs a `resurface` event, opens log `open` events, and `GET /admin/status` reports the share of resurfaced items opened within 7 days. That is the number milestone 6 is judged by.

## Data model

See `api/src/smriti/models.py`. The tables follow the spec, plus `api_tokens`, `app_settings` (per-step model choices, digest settings) and `model_cache`. The embedding dimension is fixed per install by `SMRITI_EMBED_DIM` when the first migration runs.

## Auth

One owner. The owner secret only mints per-device tokens (`POST /auth/tokens`); tokens are stored as SHA-256 hashes and can be revoked. Files are served through signed, expiring URLs so `<img>` tags work without headers. Archived pages are served with a sandboxing CSP.
