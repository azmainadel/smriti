"""OCR with a local Tesseract. Optional: returns None when it is not installed."""

import io
import logging
import shutil

from PIL import Image

log = logging.getLogger(__name__)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def ocr_image(data: bytes, min_confidence: int = 55) -> str | None:
    if not ocr_available():
        return None
    import pytesseract

    img = Image.open(io.BytesIO(data)).convert("L")
    # Upscale small screenshots; Tesseract does poorly below ~20px glyphs.
    if img.width < 1000:
        factor = 1000 / img.width
        img = img.resize((1000, int(img.height * factor)))
    data_out = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data_out["text"]):
        if word.strip() and float(data_out["conf"][i]) >= min_confidence:
            key = (data_out["block_num"][i], data_out["par_num"][i], data_out["line_num"][i])
            lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    return text or None
