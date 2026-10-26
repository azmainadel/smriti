"""Step 4: archive a self-contained copy of the page, so dead links lose nothing."""

import asyncio
import base64
import logging
from urllib.parse import urljoin

import httpx
from lxml import etree
from lxml import html as lxml_html

from smriti.config import get_settings
from smriti.pipeline import browser
from smriti.pipeline.context import StepContext, StepSkipped

log = logging.getLogger(__name__)
MAX_INLINE_ASSETS = 40
MAX_ASSET_BYTES = 2 * 1024 * 1024


async def _fetch_data_uri(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or len(r.content) > MAX_ASSET_BYTES:
        return None
    mime = r.headers.get("content-type", "application/octet-stream").split(";")[0]
    return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"


async def archive_html(page: str, base_url: str) -> str:
    """Strip scripts and inline stylesheets and images as data URIs."""
    tree = lxml_html.fromstring(page)
    for el in tree.xpath(
        "//script|//iframe|//object|//embed|//link[@rel='preload' or @rel='prefetch']"
    ):
        el.drop_tree()
    for el in tree.xpath("//*[@*[starts-with(name(), 'on')]]"):
        for attr in [a for a in el.attrib if a.startswith("on")]:
            del el.attrib[attr]

    s = get_settings()
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, headers={"User-Agent": s.user_agent}
    ) as client:
        sheets = tree.xpath("//link[@rel='stylesheet'][@href]")[:15]
        css = await asyncio.gather(
            *(client.get(urljoin(base_url, l.get("href"))) for l in sheets), return_exceptions=True
        )
        for link, resp in zip(sheets, css, strict=True):
            if isinstance(resp, httpx.Response) and resp.status_code == 200:
                style = etree.Element("style")
                style.text = resp.text
                link.addprevious(style)
            link.drop_tree()

        imgs = [i for i in tree.xpath("//img[@src]") if not i.get("src").startswith("data:")]
        imgs = imgs[:MAX_INLINE_ASSETS]
        uris = await asyncio.gather(
            *(_fetch_data_uri(client, urljoin(base_url, i.get("src"))) for i in imgs)
        )
        for img, uri in zip(imgs, uris, strict=True):
            if uri:
                img.set("src", uri)
            img.attrib.pop("srcset", None)

    head = tree.find("head")
    if head is not None:
        base = etree.SubElement(head, "base", href=base_url)
        head.insert(0, base)
        meta = etree.Element("meta", name="smriti-archived-from", content=base_url)
        head.insert(0, meta)
    return lxml_html.tostring(tree, encoding="unicode", doctype="<!DOCTYPE html>")


async def snapshot(ctx: StepContext) -> None:
    item = ctx.item
    if not item.raw_html_key or not item.source_url:
        raise StepSkipped("no page to archive")
    page = (await ctx.storage.get(item.raw_html_key)).decode("utf-8", "replace")
    content = ctx.content()

    archived = await archive_html(page, item.meta.get("final_url") or item.source_url)
    content.html_archive_key = await ctx.put(
        "archive.html", archived.encode(), "text/html; charset=utf-8"
    )

    if browser.available():
        try:
            _, shot = await browser.render(html=archived, screenshot=True)
            if shot:
                content.screenshot_key = await ctx.put("screenshot.jpg", shot, "image/jpeg")
        except Exception as e:  # noqa: BLE001 - the archive is enough on its own
            log.warning("screenshot failed: %s", e)
