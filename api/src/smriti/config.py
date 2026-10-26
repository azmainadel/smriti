from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMRITI_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smriti"

    # Owner secret: exchanged for per-device API tokens. Required outside dev.
    owner_secret: str = "change-me"
    # Signs short-lived file URLs so <img> tags work without auth headers.
    signing_key: str = "dev-signing-key"
    public_api_url: str = "http://localhost:8000"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Blob storage: "s3" for MinIO/S3, "local" for a directory (dev and tests).
    storage_backend: Literal["s3", "local"] = "local"
    storage_dir: Path = Path(".data/blobs")
    s3_endpoint: str | None = None
    s3_bucket: str = "smriti"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # Models. Each enrichment step can override these from the settings page.
    llm_provider: Literal["none", "ollama", "openai"] = "none"
    llm_model: str = "qwen2.5:3b-instruct"
    embed_provider: Literal["hash", "fastembed", "ollama", "openai"] = "fastembed"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384
    # Cross-modal image search. Text and image models must share one vector space.
    vision_enabled: bool = False
    clip_text_model: str = "Qdrant/clip-ViT-B-32-text"
    clip_image_model: str = "Qdrant/clip-ViT-B-32-vision"
    clip_dim: int = 512
    # Ollama vision model for image captions and alt text; empty disables captions.
    caption_model: str = ""
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    model_timeout_s: float = 60.0

    # Fetching
    user_agent: str = "Mozilla/5.0 (compatible; Smriti/0.1; +https://github.com/azmainadel/smriti)"
    fetch_timeout_s: float = 20.0
    max_fetch_bytes: int = 50 * 1024 * 1024
    browser_enabled: bool = False

    # Worker
    worker_concurrency: int = 4
    poll_interval_s: float = 0.5

    # Inbound email webhook secret, part of the URL path.
    inbound_email_secret: str | None = None

    # Weekly digest over SMTP (opt-in).
    digest_email_to: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "smriti@localhost"

    log_level: str = "INFO"
    log_json: bool = True

    search_rerank_cross_encoder: bool = False
    search_candidates: int = Field(default=200, ge=10, le=2000)


@lru_cache
def get_settings() -> Settings:
    return Settings()
