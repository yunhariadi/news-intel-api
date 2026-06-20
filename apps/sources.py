"""sources.py — Source registry for v0.1+.

Real Indonesian news RSS feeds. ANTARA is a wire agency (`is_wire=True`), so it
wins carrier→origin resolution when its copy is republished. A source may list
several section feeds (same `source_id`, different `feed_url`) for volume.

Feed URLs are best-effort: a feed that 404s or changes shape is handled
gracefully (the ingestion loop marks the source errored and continues — see
`run_ingestion`), so an occasionally-broken feed never stalls the pool. Verify /
extend this list for your deployment.
"""

from __future__ import annotations

from dataclasses import dataclass

from packages.schemas.article import SourceConfig

_JKT = "Asia/Jakarta"


@dataclass(frozen=True)
class RegisteredSource:
    config: SourceConfig
    feed_url: str


_ANTARA = SourceConfig(source_id="antara", name="ANTARA", is_wire=True, default_tz=_JKT)
_KOMPAS = SourceConfig(source_id="kompas", name="Kompas", default_tz=_JKT)
_CNBC = SourceConfig(source_id="cnbc", name="CNBC Indonesia", default_tz=_JKT)
_CNN = SourceConfig(source_id="cnnid", name="CNN Indonesia", default_tz=_JKT)
_TEMPO = SourceConfig(source_id="tempo", name="Tempo", default_tz=_JKT)

SOURCE_REGISTRY: list[RegisteredSource] = [
    # ANTARA (wire) — section feeds for volume.
    RegisteredSource(_ANTARA, "https://www.antaranews.com/rss/terkini.xml"),
    RegisteredSource(_ANTARA, "https://www.antaranews.com/rss/ekonomi.xml"),
    RegisteredSource(_ANTARA, "https://www.antaranews.com/rss/politik.xml"),
    RegisteredSource(_ANTARA, "https://www.antaranews.com/rss/hukum.xml"),
    # CNN Indonesia.
    RegisteredSource(_CNN, "https://www.cnnindonesia.com/nasional/rss"),
    RegisteredSource(_CNN, "https://www.cnnindonesia.com/ekonomi/rss"),
    # Tempo.
    RegisteredSource(_TEMPO, "https://rss.tempo.co/nasional"),
    RegisteredSource(_TEMPO, "https://rss.tempo.co/ekbis"),
    # Best-effort (verify for your deployment).
    RegisteredSource(_KOMPAS, "https://www.kompas.com/rss"),
    RegisteredSource(_CNBC, "https://www.cnbcindonesia.com/rss"),
]
