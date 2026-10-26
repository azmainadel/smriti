import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from smriti.config import get_settings

_settings = get_settings()
EMBED_DIM = _settings.embed_dim
CLIP_DIM = _settings.clip_dim


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class ItemType(enum.StrEnum):
    article = "article"
    tweet = "tweet"
    video = "video"
    audio = "audio"
    pdf = "pdf"
    image = "image"
    note = "note"
    quote = "quote"
    product = "product"
    palette = "palette"
    link = "link"


class ItemStatus(enum.StrEnum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Item(Base):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String(16), default=ItemType.link)
    status: Mapped[str] = mapped_column(String(16), default=ItemStatus.pending)
    source_url: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    # Short summary shown on cards; the full enrichment output lives in `enrichments`.
    summary: Mapped[str | None] = mapped_column(Text)
    site_name: Mapped[str | None] = mapped_column(Text)
    lead_image_key: Mapped[str | None] = mapped_column(Text)
    # Type-specific card data: duration, price, author, page_count, quote text...
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # Up to 5 {hex, lab: [L, a, b], weight} entries.
    palette: Mapped[list[Any] | None] = mapped_column()
    simhash: Mapped[int | None] = mapped_column(BigInteger)
    capture: Mapped[str] = mapped_column(String(16), default="web")
    # Raw HTML sent by the extension, so the server can skip fetching.
    raw_html_key: Mapped[str | None] = mapped_column(Text)
    original_key: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL")
    )

    content: Mapped["ItemContent | None"] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(secondary="item_tags", lazy="selectin")

    __table_args__ = (
        Index("ix_items_saved_at_id", saved_at.desc(), id.desc()),
        Index("ix_items_type", "type"),
    )


class ItemContent(Base):
    __tablename__ = "item_content"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    # Copies of title, note and tags kept here so the tsvector can weight them.
    title: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    html_archive_key: Mapped[str | None] = mapped_column(Text)
    screenshot_key: Mapped[str | None] = mapped_column(Text)
    lang: Mapped[str | None] = mapped_column(String(16))
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(extra, '')), 'A')"
            " || setweight(to_tsvector('english', left(coalesce(text, ''), 400000)), 'B')"
            " || setweight(to_tsvector('english', left(coalesce(ocr_text, ''), 100000)), 'C')",
            persisted=True,
        ),
    )

    item: Mapped[Item] = relationship(back_populates="content")

    __table_args__ = (Index("ix_item_content_tsv", "tsv", postgresql_using="gin"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    # "item" is the whole-item vector (title + summary); others follow document structure.
    kind: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM))
    embed_model: Mapped[str] = mapped_column(String(128))

    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # image, keyframe, figure, thumbnail
    storage_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str | None] = mapped_column(String(127))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    phash: Mapped[int | None] = mapped_column(BigInteger)
    clip_embedding: Mapped[Any | None] = mapped_column(Vector(CLIP_DIM))
    colors: Mapped[list[Any] | None] = mapped_column()
    caption: Mapped[str | None] = mapped_column(Text)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[Item] = relationship(back_populates="assets")

    __table_args__ = (
        Index(
            "ix_assets_clip_hnsw",
            "clip_embedding",
            postgresql_using="hnsw",
            postgresql_ops={"clip_embedding": "vector_cosine_ops"},
        ),
    )


class Enrichment(Base):
    __tablename__ = "enrichments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    output: Mapped[dict[str, Any]] = mapped_column(default=dict)
    model: Mapped[str | None] = mapped_column(String(128))
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("item_id", "step", "version"),)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBED_DIM))


class ItemTag(Base):
    __tablename__ = "item_tags"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    # "auto" from enrichment, "user" from PATCH. Re-enrichment never removes user tags.
    source: Mapped[str] = mapped_column(String(8), default="auto")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))  # person, place, product, org, topic

    __table_args__ = (UniqueConstraint("name", "kind"),)


class ItemEntity(Base):
    __tablename__ = "item_entities"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16))  # open, dismiss, resurface, save, search
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)

    __table_args__ = (Index("ix_events_item_kind_at", "item_id", "kind", "at"),)


class Job(Base):
    """Workflow step queue. Owned by the runner; app code only enqueues."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(48))
    version: Mapped[int] = mapped_column(Integer)
    # item_id + step + version: re-enqueueing a finished step is a no-op.
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    # Run the rest of the workflow after this step succeeds.
    chain: Mapped[bool] = mapped_column(Boolean, default=True)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_jobs_ready",
            "run_after",
            postgresql_where=(status == JobStatus.queued),
        ),
    )


class ModelCache(Base):
    __tablename__ = "model_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    output: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    """Runtime settings edited from the UI, e.g. the model used per enrichment step."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column()
