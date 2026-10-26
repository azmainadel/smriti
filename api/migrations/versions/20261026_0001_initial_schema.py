"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-26 11:36:35.420100
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from smriti.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed per install: the embedding model is chosen before the first migration.
# Switching models later adds a new column and backfills (see docs/models.md).
EMBED_DIM = get_settings().embed_dim
CLIP_DIM = get_settings().clip_dim


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "kind"),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("site_name", sa.Text(), nullable=True),
        sa.Column("lead_image_key", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("palette", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("simhash", sa.BigInteger(), nullable=True),
        sa.Column("capture", sa.String(length=16), nullable=False),
        sa.Column("raw_html_key", sa.Text(), nullable=True),
        sa.Column("original_key", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "saved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_of", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["duplicate_of"], ["items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_items_canonical_url"), "items", ["canonical_url"], unique=False)
    op.create_index(op.f("ix_items_domain"), "items", ["domain"], unique=False)
    op.create_index(
        "ix_items_saved_at_id",
        "items",
        [sa.literal_column("saved_at DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    op.create_index("ix_items_type", "items", ["type"], unique=False)
    op.create_table(
        "model_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(length=127), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("phash", sa.BigInteger(), nullable=True),
        sa.Column("clip_embedding", Vector(CLIP_DIM), nullable=True),
        sa.Column("colors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assets_clip_hnsw",
        "assets",
        ["clip_embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"clip_embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_assets_item_id"), "assets", ["item_id"], unique=False)
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=False),
        sa.Column("embed_model", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_chunks_item_id"), "chunks", ["item_id"], unique=False)
    op.create_table(
        "enrichments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("step", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "step", "version"),
    )
    op.create_index(op.f("ix_enrichments_item_id"), "enrichments", ["item_id"], unique=False)
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_item_kind_at", "events", ["item_id", "kind", "at"], unique=False)
    op.create_table(
        "item_content",
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("extra", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("html_archive_key", sa.Text(), nullable=True),
        sa.Column("screenshot_key", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=16), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(extra, '')), 'A') || setweight(to_tsvector('english', left(coalesce(text, ''), 400000)), 'B') || setweight(to_tsvector('english', left(coalesce(ocr_text, ''), 100000)), 'C')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id"),
    )
    op.create_index(
        "ix_item_content_tsv", "item_content", ["tsv"], unique=False, postgresql_using="gin"
    )
    op.create_table(
        "item_entities",
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id", "entity_id"),
    )
    op.create_index(
        op.f("ix_item_entities_entity_id"), "item_entities", ["entity_id"], unique=False
    )
    op.create_table(
        "item_tags",
        sa.Column("item_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("item_id", "tag_id"),
    )
    op.create_index(op.f("ix_item_tags_tag_id"), "item_tags", ["tag_id"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("step", sa.String(length=48), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("chain", sa.Boolean(), nullable=False),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_jobs_item_id"), "jobs", ["item_id"], unique=False)
    op.create_index(
        "ix_jobs_ready",
        "jobs",
        ["run_after"],
        unique=False,
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_ready", table_name="jobs", postgresql_where=sa.text("status = 'queued'"))
    op.drop_index(op.f("ix_jobs_item_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_item_tags_tag_id"), table_name="item_tags")
    op.drop_table("item_tags")
    op.drop_index(op.f("ix_item_entities_entity_id"), table_name="item_entities")
    op.drop_table("item_entities")
    op.drop_index("ix_item_content_tsv", table_name="item_content", postgresql_using="gin")
    op.drop_table("item_content")
    op.drop_index("ix_events_item_kind_at", table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_enrichments_item_id"), table_name="enrichments")
    op.drop_table("enrichments")
    op.drop_index(op.f("ix_chunks_item_id"), table_name="chunks")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("chunks")
    op.drop_index(op.f("ix_assets_item_id"), table_name="assets")
    op.drop_index(
        "ix_assets_clip_hnsw",
        table_name="assets",
        postgresql_using="hnsw",
        postgresql_ops={"clip_embedding": "vector_cosine_ops"},
    )
    op.drop_table("assets")
    op.drop_table("tags")
    op.drop_table("model_cache")
    op.drop_index("ix_items_type", table_name="items")
    op.drop_index("ix_items_saved_at_id", table_name="items")
    op.drop_index(op.f("ix_items_domain"), table_name="items")
    op.drop_index(op.f("ix_items_canonical_url"), table_name="items")
    op.drop_table("items")
    op.drop_table("entities")
    op.drop_table("app_settings")
    op.drop_table("api_tokens")
