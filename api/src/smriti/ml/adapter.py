"""One interface over every model Smriti calls.

Each call goes through a cache keyed by a hash of (provider, model, kind, input), so
re-indexing unchanged content costs nothing. Every call reports tokens and time so
enrichment rows can record real cost numbers.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import httpx
import numpy as np
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from smriti.config import get_settings
from smriti.db import get_sessionmaker
from smriti.ml.hashing import hash_embed
from smriti.models import AppSetting, ModelCache

log = logging.getLogger(__name__)

Provider = Literal["none", "hash", "fastembed", "ollama", "openai"]


@dataclass(frozen=True)
class ModelChoice:
    provider: Provider
    model: str
    # USD per 1k tokens, for API providers. Local models cost 0.
    price_per_1k: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class CallResult[T]:
    output: T
    model: str
    tokens: int = 0
    ms: int = 0
    cost: float = 0.0
    cached: bool = False


class ModelError(RuntimeError):
    pass


def _cache_key(choice: ModelChoice, kind: str, payload: Any) -> str:
    blob = json.dumps([choice.provider, choice.model, kind, payload], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


async def _cache_get(keys: list[str]) -> dict[str, Any]:
    async with get_sessionmaker()() as s:
        rows = await s.execute(
            select(ModelCache.key, ModelCache.output).where(ModelCache.key.in_(keys))
        )
        return {k: v for k, v in rows.all()}


async def _cache_put(entries: dict[str, Any]) -> None:
    if not entries:
        return
    async with get_sessionmaker()() as s:
        stmt = insert(ModelCache).values([{"key": k, "output": v} for k, v in entries.items()])
        await s.execute(stmt.on_conflict_do_nothing())
        await s.commit()


_overrides: tuple[float, dict[str, Any]] = (0.0, {})


async def _step_overrides() -> dict[str, Any]:
    """Per-step model choices saved from the settings page, cached for 15 s."""
    global _overrides
    stamp, value = _overrides
    if time.monotonic() - stamp < 15:
        return value
    async with get_sessionmaker()() as s:
        row = await s.get(AppSetting, "models")
        value = row.value if row else {}
    _overrides = (time.monotonic(), value)
    return value


def invalidate_overrides() -> None:
    global _overrides
    _overrides = (0.0, {})


async def choice_for(step: str, kind: Literal["llm", "embed"]) -> ModelChoice:
    s = get_settings()
    override = (await _step_overrides()).get(step) or {}
    if kind == "embed":
        # The embedding model is install-wide: vectors from different models are not comparable.
        return ModelChoice(s.embed_provider, s.embed_model)
    return ModelChoice(
        override.get("provider", s.llm_provider),
        override.get("model", s.llm_model),
        float(override.get("price_per_1k", 0.0)),
    )


# ---------- LLM ----------


async def complete_json[M: BaseModel](
    step: str, system: str, prompt: str, schema: type[M]
) -> CallResult[M] | None:
    """Structured output from the step's LLM. Returns None when no LLM is configured,
    so callers fall back to a heuristic."""
    choice = await choice_for(step, "llm")
    if choice.provider == "none":
        return None

    payload = {"system": system, "prompt": prompt, "schema": schema.model_json_schema()}
    key = _cache_key(choice, "json", payload)
    if hit := (await _cache_get([key])).get(key):
        return CallResult(
            schema.model_validate(hit["output"]), choice.label, hit["tokens"], 0, 0.0, True
        )

    started = time.perf_counter()
    raw, tokens = await _chat(choice, system, prompt, schema.model_json_schema())
    ms = int((time.perf_counter() - started) * 1000)
    try:
        output = schema.model_validate_json(_strip_fences(raw))
    except ValidationError as e:
        raise ModelError(f"{choice.label} returned invalid JSON for {step}: {e}") from e

    await _cache_put({key: {"output": output.model_dump(mode="json"), "tokens": tokens}})
    cost = tokens / 1000 * choice.price_per_1k
    return CallResult(output, choice.label, tokens, ms, cost)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return raw


async def _chat(
    choice: ModelChoice,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    images: list[str] | None = None,
) -> tuple[str, int]:
    s = get_settings()
    async with httpx.AsyncClient(timeout=s.model_timeout_s) as client:
        if choice.provider == "ollama":
            user: dict[str, Any] = {"role": "user", "content": prompt}
            if images:
                user["images"] = images
            r = await client.post(
                f"{s.ollama_url}/api/chat",
                json={
                    "model": choice.model,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": 0},
                    "messages": [{"role": "system", "content": system}, user],
                },
            )
            r.raise_for_status()
            body = r.json()
            return body["message"]["content"], body.get("prompt_eval_count", 0) + body.get(
                "eval_count", 0
            )

        if choice.provider == "openai":
            content: Any = prompt
            if images:
                content = [{"type": "text", "text": prompt}] + [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    for b64 in images
                ]
            r = await client.post(
                f"{s.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {s.openai_api_key}"},
                json={
                    "model": choice.model,
                    "temperature": 0,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {"name": "output", "schema": schema},
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                },
            )
            r.raise_for_status()
            body = r.json()
            return body["choices"][0]["message"]["content"], body.get("usage", {}).get(
                "total_tokens", 0
            )

    raise ModelError(f"provider {choice.provider} cannot chat")


async def describe_image(step: str, image_b64: str, prompt: str) -> CallResult[str] | None:
    """Caption an image with the configured vision model (Ollama or an OpenAI-compatible API)."""
    s = get_settings()
    base = await choice_for(step, "llm")
    model = s.caption_model or (base.model if base.provider == "openai" else "")
    if base.provider == "none" or not model:
        return None
    choice = ModelChoice(base.provider, model, base.price_per_1k)

    class Caption(BaseModel):
        caption: str

    key = _cache_key(choice, "caption", [prompt, hashlib.sha256(image_b64.encode()).hexdigest()])
    if hit := (await _cache_get([key])).get(key):
        return CallResult(hit["output"], choice.label, hit["tokens"], 0, 0.0, True)
    started = time.perf_counter()
    raw, tokens = await _chat(
        choice,
        "You describe images for search and alt text.",
        prompt,
        Caption.model_json_schema(),
        images=[image_b64],
    )
    caption = Caption.model_validate_json(_strip_fences(raw)).caption.strip()
    await _cache_put({key: {"output": caption, "tokens": tokens}})
    ms = int((time.perf_counter() - started) * 1000)
    return CallResult(caption, choice.label, tokens, ms, tokens / 1000 * choice.price_per_1k)


# ---------- Embeddings ----------


@lru_cache(maxsize=4)
def _fastembed_text(model: str):  # noqa: ANN202 - fastembed types are optional
    from fastembed import TextEmbedding

    return TextEmbedding(model)


@lru_cache(maxsize=2)
def _fastembed_image(model: str):  # noqa: ANN202
    from fastembed import ImageEmbedding

    return ImageEmbedding(model)


def _normalize(vectors: np.ndarray) -> list[list[float]]:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (vectors / norms).astype(np.float32).tolist()


async def _embed_uncached(
    choice: ModelChoice, texts: list[str], dim: int
) -> tuple[list[list[float]], int]:
    s = get_settings()
    match choice.provider:
        case "hash":
            return [hash_embed(t, dim) for t in texts], 0
        case "fastembed":
            model = _fastembed_text(choice.model)
            vecs = await asyncio.to_thread(lambda: np.array(list(model.embed(texts))))
            return _normalize(vecs), 0
        case "ollama":
            async with httpx.AsyncClient(timeout=s.model_timeout_s) as client:
                r = await client.post(
                    f"{s.ollama_url}/api/embed", json={"model": choice.model, "input": texts}
                )
                r.raise_for_status()
                body = r.json()
                return _normalize(np.array(body["embeddings"])), body.get("prompt_eval_count", 0)
        case "openai":
            async with httpx.AsyncClient(timeout=s.model_timeout_s) as client:
                r = await client.post(
                    f"{s.openai_base_url}/embeddings",
                    headers={"Authorization": f"Bearer {s.openai_api_key}"},
                    json={"model": choice.model, "input": texts, "dimensions": dim},
                )
                r.raise_for_status()
                body = r.json()
                vecs = [d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"])]
                return _normalize(np.array(vecs)), body.get("usage", {}).get("total_tokens", 0)
    raise ModelError(f"provider {choice.provider} cannot embed")


async def _embed_cached(
    choice: ModelChoice, kind: str, texts: list[str], dim: int, batch: int = 64
) -> CallResult[list[list[float]]]:
    started = time.perf_counter()
    keys = [_cache_key(choice, kind, t) for t in texts]
    cached = await _cache_get(list(set(keys))) if choice.provider != "hash" else {}
    missing = [i for i, k in enumerate(keys) if k not in cached]
    tokens = 0
    fresh: dict[str, Any] = {}
    for start in range(0, len(missing), batch):
        idx = missing[start : start + batch]
        vectors, used = await _embed_uncached(choice, [texts[i] for i in idx], dim)
        tokens += used
        for i, v in zip(idx, vectors, strict=True):
            fresh[keys[i]] = v
    if choice.provider != "hash":
        await _cache_put(fresh)
    lookup = {**cached, **fresh}
    ms = int((time.perf_counter() - started) * 1000)
    return CallResult([lookup[k] for k in keys], choice.label, tokens, ms, cached=not missing)


async def embed_texts(texts: list[str], *, query: bool = False) -> CallResult[list[list[float]]]:
    choice = await choice_for("embeddings", "embed")
    dim = get_settings().embed_dim
    if query and choice.provider == "fastembed" and "bge" in choice.model:
        # BGE models expect this instruction on queries, not on passages.
        texts = [f"Represent this sentence for searching relevant passages: {t}" for t in texts]
    return await _embed_cached(choice, "text", texts, dim)


async def embed_query(text: str) -> list[float]:
    return (await embed_texts([text], query=True)).output[0]


def vision_enabled() -> bool:
    return get_settings().vision_enabled


async def clip_embed_text(text: str) -> list[float] | None:
    if not vision_enabled():
        return None
    s = get_settings()
    choice = ModelChoice("fastembed", s.clip_text_model)
    return (await _embed_cached(choice, "clip-text", [text], s.clip_dim)).output[0]


async def clip_embed_images(images: list[bytes]) -> list[list[float]] | None:
    if not vision_enabled() or not images:
        return None
    import io

    from PIL import Image

    model = _fastembed_image(get_settings().clip_image_model)

    def _run() -> np.ndarray:
        pil = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
        return np.array(list(model.embed(pil)))

    return _normalize(await asyncio.to_thread(_run))
