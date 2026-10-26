"""Notes, quotes, palettes and images: little to extract, mostly stored as is."""

import re

from smriti.models import ItemType
from smriti.pipeline.classify import palette_codes
from smriti.pipeline.extractors import html as h
from smriti.pipeline.extractors.base import Extraction, Image

_QUOTE_MARKS = "\"'“”‘’"


def extract_note(text: str, item_type: str) -> Extraction:
    text = text.strip()
    if item_type == ItemType.palette and (codes := palette_codes(text)):
        return extract_palette(codes)
    meta = {}
    if item_type == ItemType.quote:
        if m := re.search(r"\n\s*[—–-]\s*(.+)$", text):
            meta["attribution"] = m.group(1).strip()
            text_only = text[: m.start()]
        else:
            text_only = text
        meta["quote"] = text_only.strip().strip(_QUOTE_MARKS).strip()
    first_line = text.splitlines()[0] if text else ""
    return Extraction(
        title=first_line[:120] if item_type == ItemType.note else None,
        text=text,
        html=h.text_to_html(text),
        meta=meta,
    )


def _hex(code: str) -> str:
    c = code.lstrip("#").lower()
    return "#" + ("".join(ch * 2 for ch in c) if len(c) == 3 else c)


def extract_palette(codes: list[str]) -> Extraction:
    hexes = [_hex(c) for c in codes]
    return Extraction(
        title="Palette " + " ".join(hexes),
        text=" ".join(hexes),
        type=ItemType.palette,
        palette=hexes,
        meta={"colors": hexes},
    )


def palette_from_url(url: str) -> Extraction | None:
    if m := re.search(r"coolors\.co/(?:palette/)?([0-9a-f]{6}(?:-[0-9a-f]{6})+)", url, re.I):
        return extract_palette(m.group(1).split("-"))
    return None


def extract_image(data: bytes, title: str | None) -> Extraction:
    # OCR, caption, colors and hashes run in enrichment on the stored asset.
    return Extraction(title=title, type=ItemType.image, images=[Image(data, kind="image")])
