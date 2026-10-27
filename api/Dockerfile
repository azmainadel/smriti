# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm AS base

ARG WITH_BROWSER=0
ARG WITH_WHISPER=0
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/models \
    FASTEMBED_CACHE_PATH=/models/fastembed

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    extras="--extra ocr --extra otel" \
    && if [ "$WITH_BROWSER" = "1" ]; then extras="$extras --extra browser"; fi \
    && if [ "$WITH_WHISPER" = "1" ]; then extras="$extras --extra audio"; fi \
    && uv sync --frozen --no-dev --no-install-project $extras

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra ocr --extra otel \
      $( [ "$WITH_BROWSER" = "1" ] && echo --extra browser ) $( [ "$WITH_WHISPER" = "1" ] && echo --extra audio ) \
    && if [ "$WITH_BROWSER" = "1" ]; then playwright install --with-deps chromium; fi

RUN useradd --create-home --uid 1000 smriti && mkdir -p /models /data && chown smriti /models /data
USER smriti
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s CMD curl -fs http://localhost:8000/health || exit 1
CMD ["sh", "-c", "smriti migrate && smriti serve"]
