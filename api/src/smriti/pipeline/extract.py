"""Step 3: pull the real content out with the extractor for the item's type."""

import asyncio
import logging
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete

from smriti.config import get_settings
from smriti.ml.imaging import open_image, thumbnail
from smriti.models import Asset, ItemType
from smriti.pipeline.context import PermanentError, StepContext
from smriti.pipeline.extractors.article import extract_article
from smriti.pipeline.extractors.base import Extraction, Image
from smriti.pipeline.extractors.html import clean_layout
from smriti.pipeline.extractors.media import extract_audio, extract_youtube, youtube_id
from smriti.pipeline.extractors.pdf import parse_pdf
from smriti.pipeline.extractors.simple import extract_image, extract_note, palette_from_url
from smriti.pipeline.extractors.tweet import extract_tweet
from smriti.pipeline.index import index
from smriti.urls import canonicalize, domain_of

log = logging.getLogger(__name__)
MAX_TEXT = 2_000_000
MAX_IMAGES = 8
MIN_IMAGE_SIDE = 100  # smaller is an icon, a button or a spacer, not content
MAX_IMAGE_ASPECT = 5  # wider than this is a banner or a rule
CARD_SIZE = 720


async def run_extractor(ctx: StepContext) -> Extraction:
    item, storage = ctx.item, ctx.storage
    url = item.source_url or ""
    page = (
        (await storage.get(item.raw_html_key)).decode("utf-8", "replace")
        if item.raw_html_key
        else None
    )
    original = await storage.get(item.original_key) if item.original_key else None
    filename = PurePosixPath(urlsplit(url).path).name or item.meta.get("filename")

    match item.type:
        case ItemType.tweet:
            return await extract_tweet(url, page)
        case ItemType.video if youtube_id(url):
            return await extract_youtube(url)
        case ItemType.video | ItemType.audio if original:
            suffix = PurePosixPath(item.original_key or "").suffix or ".mp3"
            return await extract_audio(original, suffix, item.title or filename)
        case ItemType.pdf if original:
            return await asyncio.to_thread(parse_pdf, original)
        case ItemType.image if original:
            return extract_image(original, item.title or filename)
        case ItemType.palette:
            text = item.content.text if item.content else ""
            if url and (ex := palette_from_url(url)):
                return ex
            return extract_note(text or "", item.type)
        case ItemType.note | ItemType.quote:
            return extract_note((item.content.text if item.content else None) or "", item.type)
        case _ if page:
            return await asyncio.to_thread(extract_article, page, url)
    raise PermanentError(f"nothing to extract for {item.type} item")


async def _download_image(client: httpx.AsyncClient, url: str) -> bytes | None:
    try:
        r = await client.get(url)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            return None
        if len(r.content) > 15 * 1024 * 1024:
            return None
        w, h = open_image(r.content).size
        if min(w, h) < MIN_IMAGE_SIDE or max(w, h) / max(min(w, h), 1) > MAX_IMAGE_ASPECT:
            return None
        return r.content
    except Exception as e:  # noqa: BLE001 - a broken image never fails the item
        log.debug("image %s skipped: %s", url, e)
        return None


async def _collect_images(ex: Extraction) -> tuple[list[Image], set[str], str | None]:
    """Download candidate images. Returns the keepers, the URLs that turned out to be icons,
    spacers, banners or broken (so the article HTML can drop them too), and the lead's URL."""
    images = list(ex.images)
    rejected: set[str] = set()
    lead_url = None
    if ex.image_urls:
        s = get_settings()
        urls = ex.image_urls[: MAX_IMAGES * 2]
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True, headers={"User-Agent": s.user_agent}
        ) as client:
            downloaded = await asyncio.gather(*(_download_image(client, u) for u in urls))
        kind = "keyframe" if ex.type == ItemType.video else "image"
        images += [Image(d, kind=kind) for d in downloaded if d]
        rejected = {u for u, d in zip(urls, downloaded, strict=True) if not d}
        if not ex.images:
            lead_url = next((u for u, d in zip(urls, downloaded, strict=True) if d), None)
    return images[:MAX_IMAGES], rejected, lead_url


async def extract(ctx: StepContext) -> None:
    item = ctx.item
    ex = await run_extractor(ctx)

    if ex.type:
        item.type = ex.type
    if ex.title and item.meta.get("title_source") != "user":
        item.title = ex.title.strip()[:500]
    if ex.canonical_url and domain_of(ex.canonical_url) == item.domain:
        item.canonical_url = canonicalize(ex.canonical_url)
    item.site_name = ex.site_name or item.site_name
    item.meta = {
        **item.meta,
        **ex.meta,
        **({"description": ex.description[:1000]} if ex.description else {}),
        **({"colors": ex.palette} if ex.palette else {}),
    }

    content = ctx.content()
    content.text = ex.text[:MAX_TEXT] if ex.text else content.text
    content.html = ex.html or content.html
    content.lang = ex.lang

    # Re-running extract replaces the asset set; storage keys are positional so blobs are overwritten.
    await ctx.session.execute(delete(Asset).where(Asset.item_id == item.id))
    item.assets = []
    images, rejected, lead_url = await _collect_images(ex)
    if content.html:
        content.html = clean_layout(
            content.html,
            item.source_url or "",
            drop_images=rejected,
            title=item.title,
            lead=lead_url,
        )
    item.lead_image_key = None
    for i, img in enumerate(images):
        data = await asyncio.to_thread(thumbnail, img.data, 1600)
        key = await ctx.put(f"assets/{i}.webp", data, "image/webp")
        decoded = await asyncio.to_thread(open_image, data)
        item.assets.append(
            Asset(
                item_id=item.id,
                kind=img.kind,
                storage_key=key,
                mime="image/webp",
                width=decoded.width,
                height=decoded.height,
                caption=img.caption,
                position=i,
            )
        )
        if i == 0:
            item.lead_image_key = key
            # Grid cards are ~300 px wide; a 720 px copy covers 2x screens at a fraction of the bytes.
            card = await asyncio.to_thread(thumbnail, img.data, CARD_SIZE)
            # Reassign rather than mutate: SQLAlchemy does not track in-place JSONB edits.
            item.meta = {
                **item.meta,
                "lead_aspect": round(decoded.width / max(decoded.height, 1), 3),
                "card_key": await ctx.put("assets/0.card.webp", card, "image/webp"),
            }

    # Readable now: make it searchable by its title and text before the slow enrichment runs.
    # The final index step refreshes these fields with tags, entities and summaries.
    await index(ctx)
