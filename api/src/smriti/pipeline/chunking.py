"""Structure-aware chunks: sections follow the document's headings, not fixed token windows."""

import re
from dataclasses import dataclass

from lxml import html as lxml_html

_BLOCKS = {
    "p",
    "li",
    "blockquote",
    "pre",
    "figcaption",
    "td",
    "dd",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}
_CONTAINERS = {"td", "li", "dd"}
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


@dataclass(frozen=True)
class ChunkSpec:
    kind: str  # section, quote, code, caption
    text: str


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out, buf = [], ""
    for sentence in _SENTENCE.split(text):
        if buf and len(buf) + len(sentence) + 1 > max_chars:
            out.append(buf)
            buf = ""
        buf = f"{buf} {sentence}".strip()
        while len(buf) > max_chars:  # a single run-on "sentence"
            out.append(buf[:max_chars])
            buf = buf[max_chars:]
    if buf:
        out.append(buf)
    return out


def chunk_html(html: str | None, text: str | None = None, max_chars: int = 1200) -> list[ChunkSpec]:
    if not html:
        return chunk_text(text or "", max_chars)
    tree = lxml_html.fromstring(f"<div>{html}</div>")
    chunks: list[ChunkSpec] = []
    heading = ""
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        buf.clear()
        if not body:
            return
        for part in _split_long(body, max_chars):
            chunks.append(ChunkSpec("section", f"{heading}\n{part}" if heading else part))

    for el in tree.iter(*_BLOCKS):
        # Skip blocks nested in another block we already take whole (e.g. p inside blockquote).
        if any(a.tag in _BLOCKS - _CONTAINERS for a in el.iterancestors()):
            continue
        # Cells and list items that wrap paragraphs are containers, not paragraphs.
        if el.tag in _CONTAINERS and any(d.tag in _BLOCKS for d in el.iterdescendants()):
            continue
        content = re.sub(r"[ \t]+", " ", el.text_content()).strip()
        if not content:
            continue
        if el.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            flush()
            heading = content[:200]
        elif el.tag == "blockquote":
            chunks.append(ChunkSpec("quote", content[: max_chars * 2]))
        elif el.tag == "pre":
            chunks.extend(ChunkSpec("code", part) for part in _split_long(content, max_chars))
        elif el.tag == "figcaption":
            chunks.append(ChunkSpec("caption", content[:max_chars]))
        else:
            if sum(len(b) for b in buf) + len(content) > max_chars:
                flush()
            buf.append(content)
    flush()
    return chunks or chunk_text(text or "", max_chars)


def chunk_text(text: str, max_chars: int = 1200) -> list[ChunkSpec]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[ChunkSpec] = []
    buf = ""
    for p in paras:
        if buf and len(buf) + len(p) > max_chars:
            chunks.extend(ChunkSpec("section", s) for s in _split_long(buf, max_chars))
            buf = ""
        buf = f"{buf}\n{p}".strip()
    if buf:
        chunks.extend(ChunkSpec("section", s) for s in _split_long(buf, max_chars))
    return chunks
