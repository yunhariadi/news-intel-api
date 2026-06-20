"""article.py — Typed contracts for ingestion (pydantic v2).

These are the boundary types between source adapters and the rest of the
pipeline. Layer A hot-path code (clustering, ranking) uses frozen dataclasses;
this is where feed data is validated into a clean, typed shape first.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceConfig(BaseModel):
    """Static configuration for one source, used by its adapter."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    name: str
    is_wire: bool = False
    # Indonesia spans WIB/WITA/WIT — each source declares its local zone so
    # naive feed timestamps can be interpreted correctly (DESIGN.md §7).
    default_tz: str = "Asia/Jakarta"
    language: str = "id"


class NormalizedArticle(BaseModel):
    """One article's metadata after adapter normalization.

    Metadata only — never a full body (Prime Directive #6). `excerpt` is
    hard-capped at write time (compliance C1). `published_at` is stored in UTC;
    `published_tz` records the source-local zone it was interpreted in.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    url: str
    canonical_url: str
    title: str
    excerpt: str | None = None
    published_at: datetime | None = None  # tz-aware UTC
    published_tz: str
    language: str = "id"
    raw_category: str | None = None
