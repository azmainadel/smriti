import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from smriti.models import Item
from smriti.storage import signed_url

Capture = Literal["web", "extension", "selection", "share", "email", "cli", "import"]


class ItemCreate(BaseModel):
    """Save a URL, a note, a text selection or an image. `html` is the page as the user saw it."""

    url: HttpUrl | None = None
    text: str | None = Field(default=None, max_length=200_000)
    note: str | None = Field(default=None, max_length=20_000)
    title: str | None = Field(default=None, max_length=500)
    html: str | None = Field(default=None, max_length=20_000_000)
    # Saving a highlighted passage: stored as a quote that links back to `url`.
    selection: str | None = Field(default=None, max_length=50_000)
    # Saving one image from a page (context menu): the image URL, with `url` as its page.
    image_url: HttpUrl | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    capture: Capture = "web"
    saved_at: datetime | None = None

    @model_validator(mode="after")
    def _something_to_save(self) -> "ItemCreate":
        if not (self.url or self.text or self.selection or self.image_url):
            raise ValueError("send a url, text, selection or image_url")
        return self


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=20_000)
    tags: list[str] | None = Field(default=None, max_length=30)


class ItemOut(BaseModel):
    """What a card needs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    title: str | None
    url: str | None
    domain: str | None
    site_name: str | None
    note: str | None
    summary: str | None
    saved_at: datetime
    last_opened_at: datetime | None
    open_count: int
    lead_image: str | None
    # A card-sized copy of the lead image; falls back to the full one for older items.
    lead_thumb: str | None
    lead_aspect: float | None
    palette: list[dict[str, Any]] | None
    tags: list[str]
    meta: dict[str, Any]
    error: str | None
    duplicate_of: uuid.UUID | None


# Card metadata the client may render; everything else stays server-side.
_CARD_META = {
    "author",
    "handle",
    "avatar",
    "posts",
    "tweet_text",
    "channel",
    "duration",
    "pages",
    "price",
    "currency",
    "brand",
    "colors",
    "quote",
    "attribution",
    "description",
    "words",
    "published",
    "partial",
    "video_id",
    "chapters",
    "transcript",
    "filename",
}


def item_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        type=item.type,
        status=item.status,
        title=item.title,
        url=item.source_url,
        domain=item.domain,
        site_name=item.site_name,
        note=item.note,
        summary=item.summary,
        saved_at=item.saved_at,
        last_opened_at=item.last_opened_at,
        open_count=item.open_count,
        lead_image=signed_url(item.lead_image_key),
        lead_thumb=signed_url(item.meta.get("card_key") or item.lead_image_key),
        lead_aspect=item.meta.get("lead_aspect"),
        palette=item.palette,
        tags=sorted(t.name for t in item.tags),
        meta={k: v for k, v in item.meta.items() if k in _CARD_META},
        error=item.error,
        duplicate_of=item.duplicate_of,
    )


class AssetOut(BaseModel):
    id: uuid.UUID
    kind: str
    url: str
    width: int | None
    height: int | None
    caption: str | None
    ocr_text: str | None
    colors: list[dict[str, Any]] | None


class EnrichmentOut(BaseModel):
    step: str
    version: int
    output: dict[str, Any]
    model: str | None
    tokens: int
    cost: float
    ms: int
    created_at: datetime


class EntityOut(BaseModel):
    name: str
    kind: str


class Resurfaced(BaseModel):
    item: ItemOut
    reason: str
    score: float


class ItemDetail(ItemOut):
    content_html: str | None
    text_length: int
    lang: str | None
    key_points: list[str]
    archive_url: str | None
    screenshot_url: str | None
    original_url: str | None
    assets: list[AssetOut]
    entities: list[EntityOut]
    enrichments: list[EnrichmentOut]
    related: list[Resurfaced]
    duplicates: list[uuid.UUID]


class ItemPage(BaseModel):
    items: list[ItemOut]
    next_cursor: str | None


class ChipOut(BaseModel):
    kind: str
    label: str
    value: str
    start: int
    end: int


class SearchHitOut(BaseModel):
    item: ItemOut
    score: float
    sources: list[str]
    highlight: str | None


class SearchOut(BaseModel):
    query: str
    text: str
    chips: list[ChipOut]
    hits: list[SearchHitOut]
    took_ms: int
    timings: dict[str, int]
    fallback: bool


class ResurfaceOut(BaseModel):
    surface: str
    items: list[Resurfaced]


class EventIn(BaseModel):
    item_id: uuid.UUID
    kind: Literal["open", "dismiss", "more_like_this"]
    context: dict[str, Any] = Field(default_factory=dict)


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    secret: str


class TokenOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str


class ReindexIn(BaseModel):
    step: str
    version: int | None = None
    force: bool = False


class ReindexOut(BaseModel):
    step: str
    version: int
    enqueued: int


class ModelChoiceIn(BaseModel):
    provider: Literal["none", "ollama", "openai"]
    model: str
    price_per_1k: float = 0.0


class DigestSettings(BaseModel):
    email: bool = False
    web_url: str = "http://localhost:3000"
    last_sent: str | None = None


class ImportOut(BaseModel):
    format: str
    found: int
    created: int
    skipped: int
