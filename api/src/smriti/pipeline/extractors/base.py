from dataclasses import dataclass, field
from typing import Any

from smriti.models import ItemType


@dataclass
class Image:
    data: bytes
    kind: str = "image"  # image, keyframe, figure, thumbnail
    caption: str | None = None


@dataclass
class Extraction:
    title: str | None = None
    text: str = ""
    # Clean, structured HTML: headings, paragraphs, figures. Chunking follows its structure.
    html: str | None = None
    lang: str | None = None
    site_name: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    # Set when extraction learns more than classify did, e.g. an article that is a product.
    type: ItemType | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    # Remote images to download; the first is the lead image.
    image_urls: list[str] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    palette: list[str] | None = None
