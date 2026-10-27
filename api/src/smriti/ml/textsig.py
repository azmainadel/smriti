"""SimHash for near-duplicate text detection."""

import hashlib
import re

_TOKEN = re.compile(r"\w+", re.UNICODE)
MASK = (1 << 64) - 1


def _signed(value: int) -> int:
    """Postgres BIGINT is signed; store the 64-bit fingerprint in two's complement."""
    return value - (1 << 64) if value >= 1 << 63 else value


def simhash(text: str, shingle: int = 3) -> int | None:
    tokens = _TOKEN.findall(text.lower())
    if len(tokens) < shingle * 4:
        return None
    weights = [0] * 64
    for i in range(len(tokens) - shingle + 1):
        gram = " ".join(tokens[i : i + shingle])
        h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "little")
        for bit in range(64):
            weights[bit] += 1 if (h >> bit) & 1 else -1
    value = sum(1 << bit for bit, w in enumerate(weights) if w > 0)
    return _signed(value)


def hamming(a: int, b: int) -> int:
    return ((a & MASK) ^ (b & MASK)).bit_count()
