"""Shared HTML helpers: metadata, JSON-LD, lazy images, plain text to structured HTML."""

import html as htmllib
import json
import re
from typing import Any
from urllib.parse import urljoin

from lxml import html as lxml_html

_LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-lazy", "data-url")


def parse(doc: str) -> Any:
    return lxml_html.fromstring(doc or "<html></html>")


def meta(tree: Any) -> dict[str, str]:
    """OpenGraph, Twitter card and standard meta tags, first value wins."""
    out: dict[str, str] = {}
    for el in tree.iterfind(".//meta"):
        key = (el.get("property") or el.get("name") or el.get("itemprop") or "").strip().lower()
        value = (el.get("content") or "").strip()
        if key and value and key not in out:
            out[key] = value
    return out


def canonical_link(tree: Any, base: str) -> str | None:
    for el in tree.iterfind(".//link"):
        if (el.get("rel") or "").lower() == "canonical" and el.get("href"):
            return urljoin(base, el.get("href"))
    return None


def json_ld(tree: Any) -> list[dict[str, Any]]:
    """Every JSON-LD object on the page, with @graph containers flattened."""
    found: list[dict[str, Any]] = []
    for el in tree.iterfind('.//script[@type="application/ld+json"]'):
        try:
            data = json.loads(el.text or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop(0)
            if isinstance(node, dict):
                found.append(node)
                if isinstance(node.get("@graph"), list):
                    stack.extend(node["@graph"])
            elif isinstance(node, list):
                stack.extend(node)
    return found


def ld_type(node: dict[str, Any]) -> set[str]:
    t = node.get("@type", [])
    return {str(x).lower() for x in (t if isinstance(t, list) else [t])}


def fix_lazy_images(doc: str) -> str:
    """Promote lazy-load attributes to src so extractors see the real images."""
    tree = parse(doc)
    for img in tree.iterfind(".//img"):
        src = img.get("src") or ""
        if not src or src.startswith("data:") or "placeholder" in src or "blank" in src:
            for attr in _LAZY_ATTRS:
                if img.get(attr):
                    img.set("src", img.get(attr))
                    break
            else:
                if srcset := img.get("srcset") or img.get("data-srcset"):
                    img.set("src", srcset.split(",")[-1].strip().split(" ")[0])
    for noscript in tree.iterfind(".//noscript"):
        noscript.drop_tag()
    return lxml_html.tostring(tree, encoding="unicode")


def text_to_html(text: str, heading: str | None = None) -> str:
    parts = [f"<h2>{htmllib.escape(heading)}</h2>"] if heading else []
    for para in re.split(r"\n\s*\n", text.strip()):
        if para.strip():
            parts.append(f"<p>{htmllib.escape(para.strip()).replace(chr(10), '<br>')}</p>")
    return "\n".join(parts)


def html_to_text(doc: str) -> str:
    tree = parse(doc)
    for el in tree.iterfind(".//br"):
        el.tail = "\n" + (el.tail or "")
    tags = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "figcaption", "td")
    blocks = []
    for el in tree.iter(*tags):
        # Take the innermost blocks only: a table cell or list item that wraps paragraphs
        # would otherwise glue them together ("July 2023If you...") and repeat them.
        if any(d.tag in tags for d in el.iterdescendants()):
            continue
        text = el.text_content().strip()
        if text:
            blocks.append(text)
    return "\n\n".join(blocks) if blocks else tree.text_content().strip()


def image_srcs(doc: str, base: str, limit: int = 12) -> list[str]:
    tree = parse(doc)
    out: list[str] = []
    for img in tree.iterfind(".//img"):
        src = img.get("src")
        if src and not src.startswith("data:"):
            url = urljoin(base, src)
            if url not in out:
                out.append(url)
        if len(out) >= limit:
            break
    return out
