"""enrichment.py — In-memory enrichment store with compliance-gated queries.

Holds per-article `ArticleEnrichment` plus an entity registry (legal status,
suppression, protected-person flags) and answers the Phase 2 aggregation
endpoints: topics, actors, regions, quotes. Every row is passed through the
`packages.compliance` predicates *at query time* (COMPLIANCE.md §6: the gate runs
inside the serialization path, so a violating row can't be returned even if it
exists). This is the v0.2 backend — process-global, in-memory, mirroring the
article store's dev-scaffold note; a SQL-backed implementation behind the same
`EnrichmentStore` Protocol is a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from packages.compliance.invariants import (
    AttributionStatus,
    EntityView,
    LegalStatus,
    QuoteForm,
    QuoteView,
    is_entity_exposable,
    is_quote_exposable,
)
from packages.nlp.actor import canonical_key
from packages.nlp.enrich import ArticleEnrichment


@dataclass
class EntityRecord:
    """Governed identity for an actor (DESIGN.md §2.4 legal lifecycle)."""

    entity_id: str
    display: str
    kind: str
    legal_status: LegalStatus | None = None
    suppressed: bool = False
    is_minor: bool = False
    is_sensitive_victim: bool = False

    def view(self) -> EntityView:
        return EntityView(
            entity_id=self.entity_id,
            legal_status=self.legal_status,
            suppressed=self.suppressed,
            is_minor=self.is_minor,
            is_sensitive_victim=self.is_sensitive_victim,
        )


@dataclass(frozen=True)
class TopicAgg:
    topic: str
    article_count: int
    avg_confidence: float


@dataclass(frozen=True)
class ActorAgg:
    key: str                 # entity_id, or "key:<canonical>" for NER-only actors
    display: str
    kind: str
    entity_id: str | None
    mention_count: int
    legal_status: str | None


@dataclass(frozen=True)
class RegionAgg:
    region_id: str
    name: str
    region_type: str
    article_count: int
    avg_confidence: float


@dataclass(frozen=True)
class QuoteOut:
    quote_text: str
    speaker_display: str | None
    speaker_entity_id: str | None
    source_paragraph_url: str
    confidence: float
    method: str


class EnrichmentStore(Protocol):
    def save(self, enrichment: ArticleEnrichment) -> None: ...
    def upsert_entity(self, record: EntityRecord) -> None: ...
    def get_entity(self, entity_id: str) -> EntityRecord | None: ...
    def all_enrichments(self) -> list[ArticleEnrichment]: ...
    def topics(self) -> list[TopicAgg]: ...
    def actors(self) -> list[ActorAgg]: ...
    def regions(self) -> list[RegionAgg]: ...
    def quotes(self, actor: str | None = None) -> list[QuoteOut]: ...


@dataclass
class InMemoryEnrichmentStore:
    _by_article: dict[str, ArticleEnrichment] = field(default_factory=dict)
    _entities: dict[str, EntityRecord] = field(default_factory=dict)

    # --- write side ---------------------------------------------------------

    def save(self, enrichment: ArticleEnrichment) -> None:
        self._by_article[enrichment.article_id] = enrichment
        # Auto-register gazetteer-resolved actors so they are governable.
        for a in enrichment.actors:
            if a.entity_id and a.entity_id not in self._entities:
                self._entities[a.entity_id] = EntityRecord(
                    entity_id=a.entity_id, display=a.display, kind=a.kind
                )

    def upsert_entity(self, record: EntityRecord) -> None:
        self._entities[record.entity_id] = record

    def get_entity(self, entity_id: str) -> EntityRecord | None:
        return self._entities.get(entity_id)

    def all_enrichments(self) -> list[ArticleEnrichment]:
        return list(self._by_article.values())

    def _exposable_entity(self, entity_id: str | None) -> bool:
        """An actor row is exposable unless its registry record fails the
        compliance gate (suppressed / minor / sensitive / exonerated label)."""
        if entity_id is None:
            return True  # NER-only actor: no governed record, default exposable
        rec = self._entities.get(entity_id)
        return rec is None or is_entity_exposable(rec.view())

    # --- read side (compliance gate applied here) ---------------------------

    def topics(self) -> list[TopicAgg]:
        counts: dict[str, int] = {}
        conf_sum: dict[str, float] = {}
        for enr in self._by_article.values():
            for t in enr.topics:
                counts[t.topic] = counts.get(t.topic, 0) + 1
                conf_sum[t.topic] = conf_sum.get(t.topic, 0.0) + t.confidence
        aggs = [
            TopicAgg(
                topic=k,
                article_count=counts[k],
                avg_confidence=round(conf_sum[k] / counts[k], 4),
            )
            for k in counts
        ]
        aggs.sort(key=lambda a: (-a.article_count, a.topic))
        return aggs

    def actors(self) -> list[ActorAgg]:
        rows: dict[str, ActorAgg] = {}
        counts: dict[str, int] = {}
        for enr in self._by_article.values():
            for a in enr.actors:
                if not self._exposable_entity(a.entity_id):
                    continue  # P1/P2/P4 — drop suppressed/minor/exonerated actors
                key = a.entity_id or f"key:{a.canonical_key or canonical_key(a.display)}"
                counts[key] = counts.get(key, 0) + 1
                rec = self._entities.get(a.entity_id) if a.entity_id else None
                rows[key] = ActorAgg(
                    key=key,
                    display=a.display,
                    kind=a.kind,
                    entity_id=a.entity_id,
                    mention_count=counts[key],
                    legal_status=(rec.legal_status.value if rec and rec.legal_status else None),
                )
        out = list(rows.values())
        out.sort(key=lambda a: (-a.mention_count, a.display))
        return out

    def regions(self) -> list[RegionAgg]:
        counts: dict[str, int] = {}
        conf_sum: dict[str, float] = {}
        meta: dict[str, tuple[str, str]] = {}
        for enr in self._by_article.values():
            for r in enr.regions:
                counts[r.region_id] = counts.get(r.region_id, 0) + 1
                conf_sum[r.region_id] = conf_sum.get(r.region_id, 0.0) + r.confidence
                meta[r.region_id] = (r.name, r.region_type)
        aggs = [
            RegionAgg(
                region_id=k,
                name=meta[k][0],
                region_type=meta[k][1],
                article_count=counts[k],
                avg_confidence=round(conf_sum[k] / counts[k], 4),
            )
            for k in counts
        ]
        aggs.sort(key=lambda a: (-a.article_count, a.name))
        return aggs

    def quotes(self, actor: str | None = None) -> list[QuoteOut]:
        wanted = canonical_key(actor) if actor else None
        out: list[QuoteOut] = []
        for enr in self._by_article.values():
            for q in enr.quotes:
                # I1/I2/I3 — re-check the compliance predicate at serialization.
                view = QuoteView(
                    quote_id=enr.article_id,
                    confidence=q.confidence,
                    attribution_status=AttributionStatus(q.attribution_status),
                    source_paragraph_url=q.source_paragraph_url,
                    served_as=QuoteForm.VERBATIM,
                )
                if not is_quote_exposable(view):
                    continue
                if not self._exposable_entity(q.speaker_entity_id):
                    continue  # speaker is a suppressed/protected entity
                if wanted is not None:
                    speaker_key = canonical_key(q.speaker_display or "")
                    if wanted not in speaker_key:
                        continue
                out.append(
                    QuoteOut(
                        quote_text=q.quote_text,
                        speaker_display=q.speaker_display,
                        speaker_entity_id=q.speaker_entity_id,
                        source_paragraph_url=q.source_paragraph_url,
                        confidence=q.confidence,
                        method=q.method,
                    )
                )
        out.sort(key=lambda x: (-x.confidence, x.quote_text))
        return out
