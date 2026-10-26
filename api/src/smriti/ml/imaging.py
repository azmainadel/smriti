"""Image features: perceptual hash, colors, thumbnails."""

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps

from smriti.ml.colors import dominant_colors
from smriti.ml.textsig import _signed

_N = 32
_DCT = np.array(
    [[np.cos(np.pi * (2 * x + 1) * u / (2 * _N)) for x in range(_N)] for u in range(_N)]
)


@dataclass
class ImageInfo:
    width: int
    height: int
    mime: str
    phash: int
    colors: list[dict]


def open_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[3])
        img = background
    return img.convert("RGB")


def phash(img: Image.Image) -> int:
    gray = np.asarray(img.convert("L").resize((_N, _N), Image.Resampling.LANCZOS), dtype=np.float64)
    dct = _DCT @ gray @ _DCT.T
    low = dct[:8, :8].flatten()[1:]  # drop the DC term
    bits = low > np.median(low)
    return _signed(sum(1 << i for i, b in enumerate(bits) if b))


def analyze(data: bytes) -> ImageInfo:
    raw = Image.open(io.BytesIO(data))
    mime = Image.MIME.get(raw.format or "", "image/jpeg")
    img = open_image(data)
    small = img.copy()
    small.thumbnail((96, 96))
    pixels = np.asarray(small).reshape(-1, 3)
    return ImageInfo(img.width, img.height, mime, phash(img), dominant_colors(pixels))


def thumbnail(data: bytes, max_side: int = 800) -> bytes:
    img = open_image(data)
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=82)
    return out.getvalue()
