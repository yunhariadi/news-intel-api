"""keys.py — API key generation + hashing (Layer A).

Keys are stored only as SHA-256 hashes (never plaintext), matching CLAUDE.md
"no secrets in code / storage": the plaintext is shown to the client once at
creation and never persisted. Lookup hashes the presented bearer token and
compares. `secrets`-based generation gives a high-entropy token.
"""

from __future__ import annotations

import hashlib
import secrets

_KEY_PREFIX = "nik_"  # news-intel-key, so a leaked token is greppable/identifiable


def generate_key() -> str:
    """A new opaque API key (plaintext, shown to the client once)."""
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(plaintext: str) -> str:
    """Stable SHA-256 hex of a key. Storage + lookup use this, never plaintext."""
    return hashlib.sha256(plaintext.strip().encode("utf-8")).hexdigest()


def looks_like_key(token: str) -> bool:
    """Cheap shape check before hashing (reject obvious non-keys)."""
    return token.startswith(_KEY_PREFIX) and len(token) > len(_KEY_PREFIX) + 8
