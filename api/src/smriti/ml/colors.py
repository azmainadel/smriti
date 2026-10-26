"""Dominant colors by k-means in CIELAB, so "blue" means what people see as blue."""

import numpy as np

# sRGB anchors for color words in queries. Picked by eye, not from a standard.
NAMED_COLORS: dict[str, str] = {
    "red": "#d32f2f",
    "crimson": "#b71c1c",
    "maroon": "#7b1f1f",
    "orange": "#f57c00",
    "coral": "#ff7f50",
    "yellow": "#fbc02d",
    "gold": "#d4a017",
    "beige": "#e8dcc0",
    "cream": "#f6efdc",
    "brown": "#795548",
    "olive": "#7a7a2a",
    "green": "#388e3c",
    "lime": "#9ccc3c",
    "teal": "#00897b",
    "turquoise": "#2ec4b6",
    "cyan": "#00bcd4",
    "blue": "#1e63d0",
    "navy": "#1a2a5e",
    "purple": "#7b3fa0",
    "violet": "#8f5bd6",
    "magenta": "#d81b8c",
    "pink": "#f48fb1",
    "black": "#111111",
    "white": "#fafafa",
    "gray": "#8a8a8a",
    "grey": "#8a8a8a",
}
NEUTRALS = {"black", "white", "gray", "grey", "beige", "cream"}


def hex_to_rgb(hex_code: str) -> tuple[int, int, int]:
    h = hex_code.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: np.ndarray | tuple[int, int, int]) -> str:
    r, g, b = (int(round(float(c))) for c in rgb)
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """(N, 3) uint8 sRGB to (N, 3) CIELAB under D65."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
         [0.0193339, 0.1191920, 0.9503041]]
    )
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1
    )


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[:, 0] + 16) / 116
    fx = fy + lab[:, 1] / 500
    fz = fy - lab[:, 2] / 200
    f = np.stack([fx, fy, fz], axis=1)
    xyz = np.where(f > 6 / 29, f**3, 3 * (6 / 29) ** 2 * (f - 4 / 29))
    xyz *= np.array([0.95047, 1.0, 1.08883])
    m_inv = np.array(
        [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560],
         [0.0556434, -0.2040259, 1.0572252]]
    )
    c = np.clip(xyz @ m_inv.T, 0, 1)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
    return c * 255


def name_to_lab(name: str) -> list[float]:
    return srgb_to_lab(np.array([hex_to_rgb(NAMED_COLORS[name])]))[0].round(2).tolist()


def _kmeans(points: np.ndarray, k: int, iterations: int = 12, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    # k-means++ seeding
    centers = [points[rng.integers(len(points))]]
    for _ in range(1, k):
        d = np.min(((points[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        if d.sum() == 0:
            break
        centers.append(points[rng.choice(len(points), p=d / d.sum())])
    c = np.array(centers)
    for _ in range(iterations):
        labels = ((points[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
        new = np.array([points[labels == j].mean(0) if (labels == j).any() else c[j] for j in range(len(c))])
        if np.allclose(new, c, atol=0.1):
            break
        c = new
    labels = ((points[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
    return c, np.bincount(labels, minlength=len(c)) / len(labels)


def dominant_colors(pixels: np.ndarray, k: int = 6, max_colors: int = 5) -> list[dict]:
    """pixels: (N, 3) uint8 sRGB. Returns up to `max_colors` {hex, lab, weight}, heaviest first."""
    if len(pixels) == 0:
        return []
    if len(pixels) > 4096:
        pixels = pixels[np.random.default_rng(0).choice(len(pixels), 4096, replace=False)]
    lab = srgb_to_lab(pixels)
    centers, weights = _kmeans(lab, min(k, len(np.unique(pixels, axis=0))))

    # Merge clusters closer than a just-noticeable-ish difference.
    merged: list[tuple[np.ndarray, float]] = []
    for c, w in sorted(zip(centers, weights, strict=True), key=lambda x: -x[1]):
        for i, (mc, mw) in enumerate(merged):
            if np.linalg.norm(mc - c) < 12:
                merged[i] = ((mc * mw + c * w) / (mw + w), mw + w)
                break
        else:
            merged.append((c, float(w)))
    rgb = lab_to_srgb(np.array([c for c, _ in merged]))
    return [
        {"hex": rgb_to_hex(rgb[i]), "lab": [round(float(x), 2) for x in c], "weight": round(w, 3)}
        for i, (c, w) in enumerate(merged)
        if w >= 0.03
    ][:max_colors]


def palette_from_hex(codes: list[str]) -> list[dict]:
    rgb = np.array([hex_to_rgb(c) for c in codes])
    lab = srgb_to_lab(rgb)
    w = round(1 / len(codes), 3)
    return [
        {"hex": "#" + c.lstrip("#").lower(), "lab": [round(float(x), 2) for x in lab[i]], "weight": w}
        for i, c in enumerate(codes)
    ]
