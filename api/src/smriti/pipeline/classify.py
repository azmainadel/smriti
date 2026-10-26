"""Step 1: decide what kind of thing was saved, from URL patterns, MIME type and a HEAD request."""

import re
from urllib.parse import urlsplit

import httpx

from smriti.config import get_settings
from smriti.models import ItemType
from smriti.pipeline.context import StepContext

HEX_COLOR = re.compile(r"#?\b([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")

_URL_RULES: list[tuple[re.Pattern[str], ItemType]] = [
    (re.compile(r"^https?://(www\.|mobile\.)?(twitter|x)\.com/[^/]+/status/\d+", re.I), ItemType.tweet),
    (re.compile(r"^https?://(www\.|m\.|music\.)?youtube\.com/(watch|shorts/|live/)", re.I), ItemType.video),
    (re.compile(r"^https?://youtu\.be/", re.I), ItemType.video),
    (re.compile(r"^https?://(www\.)?vimeo\.com/\d+", re.I), ItemType.video),
    (re.compile(r"^https?://(www\.)?coolors\.co/(palette/)?[0-9a-f]{6}(-[0-9a-f]{6})+", re.I), ItemType.palette),
    (re.compile(r"\.pdf(\?.*)?$", re.I), ItemType.pdf),
    (re.compile(r"^https?://arxiv\.org/pdf/", re.I), ItemType.pdf),
    (re.compile(r"\.(png|jpe?g|gif|webp|avif|bmp|tiff?)(\?.*)?$", re.I), ItemType.image),
    (re.compile(r"\.(mp3|m4a|ogg|opus|wav|flac)(\?.*)?$", re.I), ItemType.audio),
    (re.compile(r"\.(mp4|webm|mov|mkv)(\?.*)?$", re.I), ItemType.video),
]


def type_from_url(url: str) -> ItemType | None:
    for pattern, item_type in _URL_RULES:
        if pattern.search(url):
            return item_type
    return None


def type_from_mime(mime: str | None) -> ItemType | None:
    if not mime:
        return None
    mime = mime.split(";")[0].strip().lower()
    if mime == "application/pdf":
        return ItemType.pdf
    if mime.startswith("image/"):
        return ItemType.image
    if mime.startswith("audio/"):
        return ItemType.audio
    if mime.startswith("video/"):
        return ItemType.video
    if mime in ("text/html", "application/xhtml+xml"):
        return ItemType.article
    return None


def palette_codes(text: str) -> list[str] | None:
    """A note made only of 2 to 10 hex colors is a palette."""
    stripped = re.sub(r"[\s,;|-]+", " ", text).strip()
    codes = HEX_COLOR.findall(stripped)
    leftover = HEX_COLOR.sub("", stripped).replace("#", "").strip()
    return codes if 2 <= len(codes) <= 10 and not leftover else None


def type_from_text(text: str) -> ItemType:
    if palette_codes(text):
        return ItemType.palette
    stripped = text.strip()
    # Quotes are short and usually wrapped in quote marks or attributed with a dash.
    if len(stripped) < 600 and (
        stripped[:1] in "\"“'‘" or re.search(r"\n\s*[—–-]\s*\S+", stripped)
    ):
        return ItemType.quote
    return ItemType.note


async def head_mime(url: str) -> str | None:
    s = get_settings()
    try:
        async with httpx.AsyncClient(
            timeout=8, follow_redirects=True, headers={"User-Agent": s.user_agent}
        ) as client:
            r = await client.head(url)
            if r.status_code in (403, 405, 501):
                # Some servers reject HEAD; a ranged GET costs one byte.
                r = await client.get(url, headers={"Range": "bytes=0-0"})
            return r.headers.get("content-type")
    except httpx.HTTPError:
        return None


async def classify(ctx: StepContext) -> None:
    item = ctx.item
    if item.original_key:  # uploaded file: type came from its MIME at save time
        return
    if not item.source_url:
        text = (item.content.text if item.content else None) or item.note or ""
        item.type = type_from_text(text)
        return
    if t := type_from_url(item.source_url):
        item.type = t
        return
    if item.raw_html_key:  # the extension sent rendered HTML, so it is a web page
        item.type = ItemType.article
        return
    host = urlsplit(item.source_url).hostname or ""
    mime = await head_mime(item.source_url)
    item.meta = {**item.meta, "mime": mime} if mime else item.meta
    item.type = type_from_mime(mime) or (ItemType.article if host else ItemType.link)
