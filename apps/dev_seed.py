"""dev_seed.py — Populate the in-memory stores with demo data for local play.

Runs a small, embedded set of Indonesian articles through the *real* pipeline
(ingest → dedup → content-cluster → enrich → event-cluster) into the same
process-global stores the API serves from, so `/v1/news`, `/v1/trending`,
`/v1/events`, `/v1/quotes`, `/v1/actors`, … return real results.

Two ways to use it:
- set `DEV_SEED=true` and start the API — the startup hook seeds on boot;
- run `python3 -m apps.dev_seed` to seed + print a summary (useful in a shell
  that already holds the same process, e.g. an embedded run).

The feed XML is embedded here (not read from tests/fixtures/, which is excluded
from the image) and includes a syndicated wire story, a multi-source event, and
several quotes so every endpoint has something to show.
"""

from __future__ import annotations

from collections.abc import Callable

from packages.access.tiers import Tier
from packages.db.store import wall_clock_hours
from packages.schemas.article import SourceConfig

from apps.access_store import InMemoryAccessStore
from apps.ingest import IngestReport, run_ingestion
from apps.repository import (
    EnrichmentStore,
    EventClusterer,
    Store,
    get_default_access_store,
    get_default_enricher,
    get_default_enrichment_store,
    get_default_event_clusterer,
    get_default_store,
)
from apps.sources import RegisteredSource

# A fixed demo key so docs/auth flows are reproducible (enterprise + admin so it
# can also exercise /v1/admin/dsr). Only meaningful when REQUIRE_API_KEY=true.
DEMO_API_KEY = "nik_dev_demo_0000000000000000000000000000"


def _rss(items: list[tuple[str, str, str]]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{d}</description></item>"
        for t, d, u in items
    )
    return f'<?xml version="1.0"?><rss><channel>{body}</channel></rss>'.encode()


# Embedded demo feeds keyed by the registry's feed_url.
_DEV_FEEDS: dict[str, bytes] = {
    "antara": _rss([
        ("KPK Tetapkan Tersangka Baru Kasus Korupsi",
         '"Kami akan usut tuntas kasus ini," kata Ketua KPK.',
         "https://antara.dev/korupsi-1"),
        ("Bank Indonesia Tahan Suku Bunga Acuan",
         '"Inflasi tetap terkendali," kata Perry Warjiyo.',
         "https://antara.dev/bi-rate"),
    ]),
    "kompas": _rss([
        ("KPK Periksa Pejabat soal Dugaan Korupsi",
         "Penyidik KPK memeriksa pejabat terkait dugaan korupsi di Jakarta.",
         "https://kompas.dev/korupsi-2"),
        # Syndicated carry of the ANTARA wire story: same title + lede, different
        # URL -> one content cluster, origin resolves to the ANTARA wire.
        ("Bank Indonesia Tahan Suku Bunga Acuan",
         '"Inflasi tetap terkendali," kata Perry Warjiyo.',
         "https://kompas.dev/bi-rate-carry"),
    ]),
    "cnbc": _rss([
        ("Sri Mulyani Paparkan Realisasi APBN",
         '"Belanja negara efisien," kata Sri Mulyani Indrawati di DPR.',
         "https://cnbc.dev/apbn"),
        ("Banjir Melanda Surabaya",
         "Ribuan rumah terendam banjir di Surabaya akibat hujan deras.",
         "https://cnbc.dev/banjir"),
    ]),
    "detik": _rss([
        ("KPK Dalami Aliran Dana Kasus Korupsi",
         "KPK menelusuri aliran dana dalam kasus korupsi yang sedang diusut.",
         "https://detik.dev/korupsi-3"),
    ]),
}

_DEV_REGISTRY: list[RegisteredSource] = [
    RegisteredSource(SourceConfig(source_id="antara", name="ANTARA", is_wire=True), "antara"),
    RegisteredSource(SourceConfig(source_id="kompas", name="Kompas"), "kompas"),
    RegisteredSource(SourceConfig(source_id="cnbc", name="CNBC Indonesia"), "cnbc"),
    RegisteredSource(SourceConfig(source_id="detik", name="detikcom"), "detik"),
]


def _fetcher(url: str) -> bytes | None:
    return _DEV_FEEDS.get(url)


def seed_stores(
    store: Store,
    enrichment_store: EnrichmentStore,
    event_clusterer: EventClusterer,
    *,
    access_store: InMemoryAccessStore | None = None,
    now_hours: Callable[[], float] = wall_clock_hours,
) -> IngestReport:
    """Run the demo feeds through the full pipeline into the given stores."""
    report = run_ingestion(
        _DEV_REGISTRY,
        _fetcher,
        store,
        now_hours=now_hours,
        enrichment_store=enrichment_store,
        enricher=get_default_enricher(),
        event_clusterer=event_clusterer,
    )
    if access_store is not None:
        # Register the demo key (idempotent) so authed flows are reproducible.
        access_store.register_plaintext(
            DEMO_API_KEY, "dev-demo", Tier.ENTERPRISE, is_admin=True
        )
    return report


def seed_default_stores() -> IngestReport:
    """Seed the process-global stores the API serves from."""
    return seed_stores(
        get_default_store(),
        get_default_enrichment_store(),
        get_default_event_clusterer(),
        access_store=get_default_access_store(),
    )


def main() -> None:
    report = seed_default_stores()
    print("dev seed complete:")
    print(f"  articles ingested : {report.new}")
    print(f"  content clusters  : {report.clusters}")
    print(f"  source errors     : {report.source_errors}")
    print(f"  demo API key      : {DEMO_API_KEY}")
    print("Try: curl localhost:8000/v1/trending?type=topic")


if __name__ == "__main__":
    main()
