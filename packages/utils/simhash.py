"""simhash.py — 64-bit SimHash + Hamming distance (Layer A).

SimHash maps a token bag to a 64-bit fingerprint where *similar* token bags
produce fingerprints with small Hamming distance — the basis for near-duplicate
detection across carriers (DESIGN.md §3).

Determinism is load-bearing: Python's builtin `hash()` is salted per process, so
feature hashing uses BLAKE2b (stable across runs/machines). Same tokens in, same
fingerprint out — always. This is a Prime Directive #4 (pure, deterministic)
module and ships with its own pytest gate.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

BITS = 64
_MASK = (1 << BITS) - 1


def _feature_hash(token: str) -> int:
    """Stable 64-bit hash of a single token (BLAKE2b, not salted builtin hash)."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")


def simhash64(tokens: Iterable[str]) -> int:
    """64-bit SimHash of a token iterable. Empty input -> 0.

    Repeated tokens add weight naturally (each occurrence votes), so a phrase
    that dominates the text dominates the fingerprint.
    """
    counters = [0] * BITS
    seen = False
    for token in tokens:
        seen = True
        h = _feature_hash(token)
        for i in range(BITS):
            if (h >> i) & 1:
                counters[i] += 1
            else:
                counters[i] -= 1
    if not seen:
        return 0
    out = 0
    for i in range(BITS):
        if counters[i] > 0:
            out |= 1 << i
    return out


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit fingerprints."""
    return ((a ^ b) & _MASK).bit_count()
