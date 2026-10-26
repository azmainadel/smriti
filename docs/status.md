# Status against the spec

What is built, what is partial and what is missing, as of October 2026. "Verified" means covered by an automated test or checked by hand against real pages.

## Milestones

| # | Milestone | State |
| --- | --- | --- |
| 1 | Core loop: save, extract articles, grid, keyword search | Done, tested end to end |
| 2 | Capture everywhere: extension, share target, email, bookmark import | Done. Extension tested in Chromium; Firefox load untested. Android share target and iOS Shortcut untested on devices |
| 3 | Enrichment on the workflow runner, cost per item logged | Done. LLM steps tested only through the no-LLM fallbacks and the cache; no Ollama run in CI |
| 4 | Hybrid search: parsing, four retrievers, fusion, eval in CI | Done. Seed eval set has 70 queries, not 200 real ones. p95 85 ms at 50k synthetic items |
| 5 | Rich types: transcripts, PDFs, tweet threads | Partial. Extractors exist and work on real samples; there are no 20-sample test sets per type |
| 6 | Resurfacing: scoring, home strip, rail, digest, reasons | Done in code. The 25% open-rate exit needs four weeks of use |
| 7 | Release: docs, demo video, one-command install, benchmarks | Docs and compose file done. No demo video. Docker images not built in this environment |

## Gaps worth knowing

- **Job runner.** A Postgres `SKIP LOCKED` queue, as the spec allows until lazarus exists. All queue access is in `api/src/smriti/jobs/queue.py`.
- **PDF parsing.** pypdf in layout mode with OCR for scanned pages, behind a `PdfParser` protocol. Two-column papers keep pypdf's reading order, which is often wrong. Project #4 replaces it.
- **Vector index.** pgvector HNSW only. The `VectorIndex` protocol is ready for the custom index from project #5; no comparison is published yet.
- **Embedding model switch.** Needs a migration and a full re-embed with search degraded meanwhile. The spec's new-column-then-swap approach is not built.
- **Tweet threads.** Walks self-replies above the saved tweet. Replies below it (the rest of a thread saved from its first post) are only captured when saved from the page with the extension.
- **Whisper.** Optional extra; YouTube uses captions and falls back to no transcript, not to Whisper, because downloading YouTube audio needs yt-dlp.
- **Image captions.** Only with a vision model configured (`SMRITI_CAPTION_MODEL`). Without one, images get OCR, colors and CLIP vectors but no alt text.
- **Cross-encoder re-rank.** Behind a flag and untested against the eval set.
- **Multi-user.** Not built. The open question in the spec stands: adding `owner_id` now is cheap, later it is a migration of every table.
- **Railway or Fly template.** Not built.

## Open questions from the spec

- *Default local embedding model for 4 GB:* bge-small-en-v1.5 via fastembed (ONNX, no PyTorch). Measured: API 635 MB and worker 845 MB resident with CLIP loaded, 4 ms per query embedding.
- *Is a cross-encoder worth it:* the flag exists; run `smriti eval` with `SMRITI_SEARCH_RERANK_CROSS_ENCODER=true` on a real query set to decide.
- *Multi-user:* undecided.
- *Links between notes:* notes are plain text.
