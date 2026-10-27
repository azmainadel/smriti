"""Offline embedding by feature hashing. Lexical, not semantic, but deterministic and
dependency-free: it keeps tests hermetic and the app usable with no model installed."""

import hashlib
import math
import re

_WORD = re.compile(r"[a-z0-9]+")


def _bucket(token: str, dim: int) -> tuple[int, float]:
    h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little")
    return h % dim, 1.0 if (h >> 63) & 1 else -1.0


def _stem(word: str) -> str:
    for suffix in ("ing", "ers", "er", "es", "ed", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    words = [_stem(w) for w in _WORD.findall(text.lower())]
    for w in words:
        i, sign = _bucket("w:" + w, dim)
        vec[i] += sign * 2.0
        padded = f"#{w}#"
        for j in range(len(padded) - 2):
            i, sign = _bucket("c:" + padded[j : j + 3], dim)
            vec[i] += sign * 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
