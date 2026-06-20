"""enrich.py — Enrichment orchestrator (Layer A).

Composes the pure extractors (clean → language → topic → actor → region → quote)
into one `ArticleEnrichment` per article. Still Layer A: the gazetteers are
loaded once by the worker (`build_enricher`) and passed in, so `enrich_article`
itself does no I/O and is deterministic.

It runs over *metadata we already hold* (title + capped excerpt), never a full
body (Prime Directive #6). Layer B narration (summaries) happens later and may
not feed back into these results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.nlp.actor import ActorMention, extract_actors
from packages.nlp.clean import clean_text, detect_language
from packages.nlp.gazetteer import Gazetteer, load_entities
from packages.nlp.quote import Quote, extract_quotes
from packages.nlp.region import RegionScore, extract_regions, load_regions
from packages.nlp.topic import TopicScore, classify_topics


@dataclass(frozen=True)
class Enricher:
    """The loaded gazetteers the pure pipeline needs (built once at startup)."""

    entity_gz: Gazetteer
    region_gz: Gazetteer


@dataclass(frozen=True)
class ArticleEnrichment:
    article_id: str
    language: str
    topics: tuple[TopicScore, ...]
    actors: tuple[ActorMention, ...]
    regions: tuple[RegionScore, ...]
    quotes: tuple[Quote, ...]


def build_enricher(gazetteer_dir: Path | None = None) -> Enricher:
    """Load the entity + region gazetteers (I/O — worker startup boundary)."""
    return Enricher(entity_gz=load_entities(gazetteer_dir), region_gz=load_regions())


def enrich_article(
    *,
    article_id: str,
    title: str,
    excerpt: str | None,
    raw_category: str | None,
    source_url: str,
    enricher: Enricher,
    default_language: str = "id",
) -> ArticleEnrichment:
    """Run the full deterministic enrichment over one article's metadata."""
    clean_title = clean_text(title)
    clean_excerpt = clean_text(excerpt) if excerpt else ""
    blob = f"{clean_title}. {clean_excerpt}".strip()

    language = detect_language(blob)
    if language == "unknown":
        language = default_language

    topics = classify_topics(blob, raw_category)
    actors = extract_actors(blob, enricher.entity_gz)
    regions = extract_regions(clean_title, clean_excerpt, enricher.region_gz)
    quotes = extract_quotes(blob, source_url, enricher.entity_gz)

    return ArticleEnrichment(
        article_id=article_id,
        language=language,
        topics=tuple(topics),
        actors=tuple(actors),
        regions=tuple(regions),
        quotes=tuple(quotes),
    )
