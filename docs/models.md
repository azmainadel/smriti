# Models

Every model call goes through `api/src/smriti/ml/adapter.py`. It speaks to Ollama, any OpenAI-compatible API and local ONNX models through fastembed. Calls are cached in `model_cache` by a hash of provider, model and input, so re-indexing unchanged content is free. Each enrichment row records the model, tokens, cost and milliseconds; Settings → Queue and health shows the totals per step.

## Defaults

| Step | Default | Without a model |
| --- | --- | --- |
| Text embeddings | `fastembed:BAAI/bge-small-en-v1.5`, 384 dims, about 130 MB on disk | `hash` provider: feature hashing, lexical only, for tests |
| Image embeddings | `Qdrant/clip-ViT-B-32` text and vision, 512 dims | Visual search is off |
| Summary, tags, entities | none | Extractive summary, keyword tags, proper-noun entities |
| Captions and alt text | none | No captions |
| Query parsing fallback | same as the LLM default | Rules only |

bge-small answers the open question in the spec about a default for 4 GB machines: the API and worker together measured 1.5 GB resident with it and CLIP loaded, and a query embedding takes about 4 ms.

## Choosing per step

Settings → Models sets the provider and model for `summary`, `tags`, `entities`, `caption` and `query`. An OpenAI-compatible provider is labelled "sends data off this machine". "Re-run all" queues that step for every item.

Environment variables set the defaults:

```sh
SMRITI_LLM_PROVIDER=ollama          # none | ollama | openai
SMRITI_LLM_MODEL=qwen2.5:3b-instruct
SMRITI_CAPTION_MODEL=moondream      # an Ollama vision model
SMRITI_OPENAI_BASE_URL=https://api.openai.com/v1
SMRITI_OPENAI_API_KEY=...
```

Anything that serves the OpenAI chat completions API works as `openai`: OpenAI, Anthropic's compatibility endpoint, OpenRouter, llama.cpp's server, vLLM.

## Changing the embedding model

Vectors from different models are not comparable, so the embedding model is fixed per install and every item must be re-embedded after a change. Today that means:

1. Set `SMRITI_EMBED_MODEL` and `SMRITI_EMBED_DIM`.
2. Add a migration that changes `chunks.embedding` and `tags.embedding` to the new dimension (or adds new columns).
3. `smriti reindex embeddings --force`.

Search is degraded until the backfill finishes. The spec asks for a zero-downtime switch (write to a new column, backfill, then swap); that is not built yet.
