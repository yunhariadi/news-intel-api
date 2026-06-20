"""Application settings, loaded from the environment (see `.env.example`).

Phase 0: only the keys the running skeleton needs are typed here. Add more as
the phases that use them land. `extra="ignore"` means the many forward-looking
keys in `.env.example` (trending knobs, compliance floors, …) don't break boot
before the code that reads them exists.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "local"
    app_name: str = "news-intel-api"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Storage (used from Phase 1 onward; typed now so config validates early).
    # store_backend selects the Store implementation: "memory" for local/CI,
    # "sql" to use Postgres at database_url (set in docker-compose).
    store_backend: Literal["memory", "sql"] = "memory"
    database_url: str = "postgresql+psycopg://news:news@postgres:5432/news_intel"
    redis_url: str = "redis://redis:6379/0"

    # Worker / ingestion
    fetch_interval_seconds: int = 300
    fetch_timeout_seconds: int = 15
    user_agent: str = "NewsIntelBot/0.1 (+https://example.com/bot-info)"

    # Compliance (C1 excerpt cap — read at write time in Phase 1+).
    max_excerpt_chars: int = 300

    # Trending (Phase 3). Cold-start reference scale before a rolling P95 exists.
    trend_reference_scale_fallback: float = 12.0

    # Commercial API (Phase 5). Auth is off by default so the local/CI scaffold
    # is open; deployments set REQUIRE_API_KEY=true.
    require_api_key: bool = False

    # Dev convenience: when true, the API seeds demo data through the full
    # pipeline on startup so endpoints return real results locally.
    dev_seed: bool = False

    # All-in-one mode: when true, the API runs real-feed ingestion in-process on
    # startup and on a schedule, so a single deployment serves real news without
    # a separate worker (the stores are shared within the process).
    enable_scheduler: bool = False


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so settings parse once per process."""
    return Settings()
