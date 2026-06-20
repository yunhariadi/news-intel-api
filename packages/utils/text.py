"""text.py — Text normalization for fingerprinting (Layer A).

Pure helpers used to produce the *source-independent* token stream that feeds
the content fingerprint. Normalization is intentionally aggressive and
carrier-agnostic: the same story carried by ANTARA, Tribun, and Kompas must
reduce to the same tokens so their fingerprints collide (DESIGN.md §3).
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^0-9a-z\s]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_for_fingerprint(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Source-independent."""
    lowered = text.lower()
    stripped = _NON_ALNUM.sub(" ", lowered)
    return _WHITESPACE.sub(" ", stripped).strip()


def tokenize(text: str) -> list[str]:
    """Whitespace tokens over the normalized text. Empty input -> empty list."""
    norm = normalize_for_fingerprint(text)
    return norm.split() if norm else []
