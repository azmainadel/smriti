"""Step 2: download the page or file into object storage."""

import mimetypes
import re

import httpx

from smriti.config import get_settings
from smriti.models import ItemType
from smriti.pipeline import browser
from smriti.pipeline.context import PermanentError, StepContext

# Types whose extractors talk to their own APIs instead of a downloaded page.
_API_TYPES = {ItemType.tweet, ItemType.palette, ItemType.note, ItemType.quote}
_BINARY_TYPES = {ItemType.pdf, ItemType.image, ItemType.audio}
_JS_SHELL = re.compile(r"<noscript>[^<]*(enable|requires?) javascript", re.I)


def looks_js_rendered(html: str) -> bool:
    """A page with little visible text but a JS app shell needs a real browser."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    visible = re.sub(r"<[^>]+>|\s+", " ", body)
    return len(visible.strip()) < 600 or bool(_JS_SHELL.search(html))


async def download(url: str) -> tuple[bytes, str | None, str]:
    """Returns (body, content type, final url). Streams so huge files stop at the size cap."""
    s = get_settings()
    headers = {"User-Agent": s.user_agent, "Accept-Language": "en;q=0.9,*;q=0.5"}
    async with (
        httpx.AsyncClient(timeout=s.fetch_timeout_s, follow_redirects=True, headers=headers) as client,
        client.stream("GET", url) as r,
    ):
        if r.status_code in (404, 410, 451):
            raise PermanentError(f"{url} returned {r.status_code}")
        r.raise_for_status()
        chunks, size = [], 0
        async for chunk in r.aiter_bytes():
            size += len(chunk)
            if size > s.max_fetch_bytes:
                raise PermanentError(f"{url} is larger than {s.max_fetch_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks), r.headers.get("content-type"), str(r.url)


async def fetch(ctx: StepContext) -> None:
    item = ctx.item
    if item.type in _API_TYPES or not item.source_url or item.original_key:
        return
    if item.type == ItemType.video and "youtube.com" in (item.canonical_url or ""):
        return
    if item.raw_html_key and item.type not in _BINARY_TYPES:
        return  # the extension already sent the page as the user saw it

    body, mime, final_url = await download(item.source_url)
    item.meta = {**item.meta, "mime": mime, "final_url": final_url, "bytes": len(body)}

    if item.type in _BINARY_TYPES or (mime and not mime.startswith(("text/", "application/xhtml"))):
        ext = mimetypes.guess_extension((mime or "").split(";")[0]) or ""
        item.original_key = await ctx.put(f"original{ext}", body, mime)
        return

    html = body.decode(_charset(mime) or "utf-8", errors="replace")
    if browser.available() and looks_js_rendered(html):
        html, _ = await browser.render(final_url)
        item.meta = {**item.meta, "rendered": True}
    item.raw_html_key = await ctx.put("page.html", html.encode(), "text/html; charset=utf-8")


def _charset(mime: str | None) -> str | None:
    if mime and (m := re.search(r"charset=([\w-]+)", mime)):
        return m.group(1)
    return None
