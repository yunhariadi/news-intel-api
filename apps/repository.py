"""repository.py — App-level store wiring.

Re-exports the storage contract from `packages.db` and selects a backend from
settings. `make_store` returns Postgres-backed `SqlStore` when
`store_backend == "sql"`, else `InMemoryStore`. The default store is built
lazily (and cached) so importing the app never opens a DB connection — tests and
CI run on the in-memory backend and override the dependency anyway.
"""

from __future__ import annotations

from functools import lru_cache

from packages.clustering.event_clusterer import EventClusterer
from packages.db.enrichment import EnrichmentStore, InMemoryEnrichmentStore
from packages.db.memory import InMemoryStore
from packages.db.store import (
    NewsPage,
    SourceStatus,
    Store,
    StoredArticle,
    wall_clock_hours,
)
from packages.nlp.enrich import Enricher, build_enricher

from apps.access_store import InMemoryAccessStore
from apps.api.config import Settings, get_settings

__all__ = [
    "EnrichmentStore",
    "EventClusterer",
    "InMemoryAccessStore",
    "InMemoryEnrichmentStore",
    "InMemoryStore",
    "NewsPage",
    "SourceStatus",
    "Store",
    "StoredArticle",
    "get_default_access_store",
    "get_default_enricher",
    "get_default_enrichment_store",
    "get_default_event_clusterer",
    "get_default_store",
    "make_store",
    "wall_clock_hours",
]


def make_store(settings: Settings) -> Store:
    """Select a storage backend from settings."""
    if settings.store_backend == "sql":
        from packages.db.sql import make_sql_store

        return make_sql_store(settings.database_url)
    return InMemoryStore()


@lru_cache
def get_default_store() -> Store:
    """Process-global store, built once from settings on first use."""
    return make_store(get_settings())


@lru_cache
def get_default_enrichment_store() -> EnrichmentStore:
    """Process-global enrichment store (in-memory v0.2 backend)."""
    return InMemoryEnrichmentStore()


@lru_cache
def get_default_enricher() -> Enricher:
    """Process-global enricher, gazetteers loaded once on first use."""
    return build_enricher()


@lru_cache
def get_default_event_clusterer() -> EventClusterer:
    """Process-global event clusterer (holds stable-ID event state)."""
    return EventClusterer()


@lru_cache
def get_default_access_store() -> InMemoryAccessStore:
    """Process-global access store (keys, usage, webhooks, saved queries).

    `enforce` follows the `require_api_key` setting, so the open dev scaffold
    stays open by default while deployments turn auth on."""
    return InMemoryAccessStore(enforce=get_settings().require_api_key)
