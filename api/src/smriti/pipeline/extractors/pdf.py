"""PDFs. A stand-in for the layout-aware parser (project #4) behind the same interface:
pypdf in layout mode for reading order, pdfium to render pages, OCR for scanned pages."""

import html as htmllib
import io
import re
from typing import Protocol

from smriti.models import ItemType
from smriti.pipeline.extractors.base import Extraction, Image
from smriti.pipeline.ocr import ocr_image

MAX_OCR_PAGES = 30


class PdfParser(Protocol):
    def __call__(self, data: bytes) -> Extraction: ...


def _render(pdf, index: int, scale: float = 1.0) -> bytes:  # noqa: ANN001
    page = pdf[index]
    img = page.render(scale=scale).to_pil()
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=80)
    return out.getvalue()


def _paragraphs(page_text: str) -> list[str]:
    # Join hard-wrapped lines; keep blank-line paragraph breaks. Undo end-of-line hyphenation.
    text = re.sub(r"-\n(?=[a-z])", "", page_text)
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [re.sub(r" {2,}", " ", p) for p in paras if p]


_BOILERPLATE = re.compile(
    r"arxiv|licen[cs]e|permission|copyright|attribution|preprint|proceedings|conference|journal|"
    r"doi|vol\.|issn|https?://|@|university|abstract|submitted|accepted",
    re.I,
)


def guess_title(reader) -> str | None:  # noqa: ANN001
    """Papers rarely set /Title. Take the first title-like line on page 1: a few words,
    mostly capitalized, not a license or venue line."""
    try:
        lines = (reader.pages[0].extract_text() or "").splitlines()
    except Exception:  # noqa: BLE001
        return None
    for line in lines[:40]:
        line = re.sub(r"\s+", " ", line).strip()
        words = line.split()
        if not 2 <= len(words) <= 20 or _BOILERPLATE.search(line) or line.endswith("."):
            continue
        caps = sum(w[0].isupper() for w in words if w[0].isalpha())
        if caps >= max(2, len(words) // 2):
            return line
    return None


def parse_pdf(data: bytes) -> Extraction:
    import pypdfium2
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pdf = pypdfium2.PdfDocument(data)
    info = reader.metadata or {}
    html_parts: list[str] = []
    text_parts: list[str] = []
    ocr_pages = 0

    for i, page in enumerate(reader.pages):
        try:
            raw = page.extract_text(extraction_mode="layout") or ""
        except Exception:  # noqa: BLE001 - malformed content streams are common
            raw = page.extract_text() or ""
        if len(raw.strip()) < 40 and ocr_pages < MAX_OCR_PAGES:
            # Scanned page: render and OCR it.
            raw = ocr_image(_render(pdf, i, scale=2.0)) or ""
            ocr_pages += 1
        paras = _paragraphs(raw)
        if not paras:
            continue
        html_parts.append(f'<h2 data-page="{i + 1}">Page {i + 1}</h2>')
        html_parts += [f"<p>{htmllib.escape(p)}</p>" for p in paras]
        text_parts += paras

    title = (info.get("/Title") or "").strip() or guess_title(reader)
    return Extraction(
        title=title,
        text="\n\n".join(text_parts),
        html="\n".join(html_parts),
        type=ItemType.pdf,
        images=[Image(_render(pdf, 0, scale=1.0), kind="thumbnail")] if len(pdf) else [],
        meta={
            k: v
            for k, v in {
                "pages": len(reader.pages),
                "author": (info.get("/Author") or "").strip() or None,
                "ocr_pages": ocr_pages or None,
            }.items()
            if v
        },
    )
