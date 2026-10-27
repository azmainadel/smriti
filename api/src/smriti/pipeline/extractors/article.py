"""Articles: boilerplate removal that keeps headings, figures and captions."""

import re
from urllib.parse import urlsplit

import trafilatura

from smriti.models import ItemType
from smriti.pipeline.extractors import html as h
from smriti.pipeline.extractors.base import Extraction
from smriti.pipeline.extractors.product import product_from_tree


def extract_article(doc: str, url: str) -> Extraction:
    doc = h.fix_lazy_images(doc)
    tree = h.parse(doc)
    tags = h.meta(tree)

    if product := product_from_tree(tree, tags, url):
        return product

    body_html = trafilatura.extract(
        doc,
        url=url,
        output_format="html",
        include_images=True,
        include_formatting=True,
        include_tables=True,
        include_links=False,
        favor_recall=True,
    )
    meta = trafilatura.extract_metadata(doc, default_url=url)
    text = h.html_to_text(body_html) if body_html else ""

    site_name = tags.get("og:site_name") or (meta.sitename if meta else None)
    title = (meta.title if meta else None) or tags.get("og:title") or _title_tag(tree)
    title = title and strip_site_suffix(title, site_name, url)
    description = (
        tags.get("og:description")
        or tags.get("description")
        or (meta.description if meta else None)
    )
    lead = tags.get("og:image") or tags.get("twitter:image") or (meta.image if meta else None)
    images = ([lead] if lead else []) + (h.image_srcs(body_html, url) if body_html else [])

    extraction = Extraction(
        title=title,
        text=text,
        html=body_html,
        lang=(tree.get("lang") or "").split("-")[0] or None,
        site_name=site_name,
        description=description,
        canonical_url=h.canonical_link(tree, url) or tags.get("og:url"),
        type=ItemType.article if text else ItemType.link,
        image_urls=list(dict.fromkeys(images)),
        meta={
            k: v
            for k, v in {
                "author": _author(tags, meta),
                "published": meta.date if meta else None,
                "words": len(text.split()),
                # Little text but a description usually means a paywall or cookie wall.
                "partial": bool(description) and len(text) < 400 or None,
            }.items()
            if v
        },
    )
    if not text and description:
        extraction.text = description
        extraction.html = h.text_to_html(description)
    return extraction


def _title_tag(tree) -> str | None:  # noqa: ANN001
    el = tree.find(".//title")
    return el.text_content().strip() if el is not None and el.text_content() else None


_SUFFIX = re.compile(r"\s+[-|–—·:]\s+([^-|–—·:]{2,40})$")


def strip_site_suffix(title: str, site_name: str | None, url: str) -> str:
    """Drop a trailing " - Wikipedia" or " | The Verge" when it only names the site."""
    m = _SUFFIX.search(title)
    if not m or m.start() < 3:
        return title
    suffix = _squash(m.group(1))
    if suffix and (
        suffix == _squash(site_name or "") or suffix in _squash(urlsplit(url).hostname or "")
    ):
        return title[: m.start()]
    return title


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _author(tags: dict[str, str], meta) -> str | None:  # noqa: ANN001
    """A byline from the page's own tags, else trafilatura's guess if it reads like a name.

    The guess sometimes picks up navigation text ("Authority control databases National").
    """
    if author := tags.get("author") or tags.get("article:author"):
        return author
    guess = meta.author if meta else None
    return guess if guess and len(guess.split()) <= 4 and not guess.startswith("http") else None
