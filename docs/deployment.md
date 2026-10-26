# Deployment

The target is a 2 vCPU, 4 GB VPS or a home server. `docker compose up -d` starts:

| Service | Image | Resident memory, measured |
| --- | --- | --- |
| `postgres` | pgvector/pgvector:pg17 | depends on `shared_buffers`; defaults are fine to 50k items |
| `minio` | minio/minio | not measured |
| `api` | built from `api/` | 635 MB with bge-small and the CLIP text model loaded |
| `worker` | same image, `smriti work` | 845 MB with bge-small and both CLIP models loaded |
| `web` | built from `web/` | 185 MB |
| `ollama` | profile `ollama`, optional | depends on the model; a 3B model at Q4 needs about 2.5 GB |

With `SMRITI_VISION_ENABLED=false` the API and worker each drop the CLIP models.

Local LLMs need more RAM than the core. On a 4 GB machine, run the core locally and point the LLM steps at an API, or skip LLMs: the heuristics cover summaries and tags.

## Settings

Copy `.env.example` to `.env`. Required: `SMRITI_OWNER_SECRET` and `SMRITI_SIGNING_KEY`. Set `SMRITI_PUBLIC_API_URL` and `SMRITI_WEB_URL` to the addresses browsers use; the web image bakes the API URL in at build time.

Optional features with bigger images:

```sh
WITH_BROWSER=1 SMRITI_BROWSER_ENABLED=true   # headless Chromium for JS pages and screenshots
WITH_WHISPER=1                               # podcast and video transcription
```

## Behind a reverse proxy

Serve the web app and the API on their own hostnames, for example `smriti.example.com` and `api.smriti.example.com`. `/stream` is a long-lived server-sent events response: disable proxy buffering for it (`proxy_buffering off;` in nginx, nothing to do in Caddy).

## Backups

`GET /export` (Settings → Export everything, or `smriti export`) writes a zip with one JSON line per item, all events, and every stored file. For point-in-time backups, back up the Postgres volume and the MinIO bucket together.

## Observability

- Logs are JSON lines with `item_id` and `step` on every line that has them.
- Set `OTEL_EXPORTER_OTLP_ENDPOINT` to trace API requests, workflow steps and model calls.
- Settings → Queue and health shows queue depth, failed steps with their errors, cost and time per enrichment step, save-to-ready time and the resurfacing open rate. The same data is at `GET /admin/status`.
