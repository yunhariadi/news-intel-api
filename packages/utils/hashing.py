"""hashing.py — The two article hashes (Layer A).

DESIGN.md §3 / CLAUDE.md "Do Not": never a single `sha256(title+source+date)`.
Two independent mechanisms instead:

- `dedup_key`         — sha256 of the canonical URL. Exact-refetch idempotency.
- `content_fingerprint` — source-INDEPENDENT 64-bit SimHash over title+lede.
                          Near-duplicate detection across carriers.

Keeping these separate is what lets the same wire story on 30 carriers dedup to
one content cluster instead of hashing 30 different ways.
"""

from __future__ import annotations

import hashlib

from packages.utils.simhash import simhash64
from packages.utils.text import tokenize


def dedup_key(canonical_url: str) -> str:
    """Exact-refetch key: sha256 hex of the (trimmed) canonical URL.

    URL-based, never content-based — re-ingesting the same URL is a no-op.
    """
    return hashlib.sha256(canonical_url.strip().encode("utf-8")).hexdigest()


def content_fingerprint(title: str, lede: str = "") -> int:
    """Source-independent 64-bit SimHash over normalized title + lede.

    Deliberately excludes source/date so identical content from different
    carriers yields the *same* fingerprint (Hamming distance 0).
    """
    return simhash64(tokenize(f"{title} {lede}"))
