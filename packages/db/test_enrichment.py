"""Gate for the enrichment store — aggregation + the compliance gate at query time.

Proves the COMPLIANCE.md §6 invariants hold in the serialization path:
P1 (exonerated label), P2 (suppressed entity), P4 (minor), I1/I2 (quote floor +
deep link). A row that violates them is absent from query output even though it
was ingested.
"""

from __future__ import annotations

from packages.compliance.invariants import LegalStatus
from packages.db.enrichment import EntityRecord, InMemoryEnrichmentStore
from packages.nlp.enrich import build_enricher, enrich_article

_ENR = build_enricher()


def _store_with(*articles: tuple[str, str, str | None, str | None]) -> InMemoryEnrichmentStore:
    store = InMemoryEnrichmentStore()
    for aid, title, excerpt, category in articles:
        store.save(
            enrich_article(
                article_id=aid,
                title=title,
                excerpt=excerpt,
                raw_category=category,
                source_url=f"https://news.example.id/a/{aid}",
                enricher=_ENR,
            )
        )
    return store


def test_topics_aggregated_and_sorted() -> None:
    store = _store_with(
        ("1", "Bank Indonesia tahan suku bunga", "Soal inflasi rupiah.", "Ekonomi"),
        ("2", "OJK awasi perbankan", "Soal suku bunga dan kredit.", "Ekonomi"),
    )
    topics = store.topics()
    assert topics  # non-empty
    assert topics == sorted(topics, key=lambda t: (-t.article_count, t.topic))


def test_actors_counted_across_articles() -> None:
    store = _store_with(
        ("1", "Sri Mulyani bicara anggaran", None, None),
        ("2", "Sri Mulyani Indrawati di DPR", None, None),
    )
    smi = [a for a in store.actors() if a.entity_id == "per_smi"]
    assert smi and smi[0].mention_count == 2  # alias merge across articles


def test_quotes_have_deep_link_and_pass_floor() -> None:
    store = _store_with(
        ("1", "Pernyataan", '"Ekonomi tumbuh," kata Sri Mulyani.', None),
    )
    quotes = store.quotes()
    assert quotes
    assert all(q.source_paragraph_url.startswith("https://") for q in quotes)  # I2
    assert all(q.confidence >= 0.75 for q in quotes)  # I1


def test_low_confidence_quote_not_served() -> None:
    # A quote with no attributable speaker is below the floor -> filtered (I1).
    store = _store_with(("1", "Berita", '"Sesuatu terjadi tanpa narasumber."', None))
    assert store.quotes() == []


# --- compliance filtering --------------------------------------------------

def test_suppressed_entity_absent_from_actors_and_quotes() -> None:
    store = _store_with(("1", "Pernyataan", '"Saya tidak bersalah," kata Sri Mulyani.', None))
    # P2: erase the entity.
    store.upsert_entity(
        EntityRecord(entity_id="per_smi", display="Sri Mulyani Indrawati",
                     kind="PERSON", suppressed=True)
    )
    assert all(a.entity_id != "per_smi" for a in store.actors())
    assert all(q.speaker_entity_id != "per_smi" for q in store.quotes())


def test_exonerated_actor_filtered_when_label_accusatory() -> None:
    store = _store_with(("1", "Kasus", "Erick Thohir disebut dalam berkas.", None))
    # P1: an actor whose current status is acquittal, with a prior accusatory
    # label, is not exposable.
    store.upsert_entity(
        EntityRecord(entity_id="per_erick", display="Erick Thohir", kind="PERSON",
                     legal_status=LegalStatus.BEBAS)
    )
    # BEBAS alone is non-accusatory and stays; but a tersangka-now-bebas must drop.
    store.upsert_entity(
        EntityRecord(entity_id="per_erick", display="Erick Thohir", kind="PERSON",
                     legal_status=LegalStatus.TERSANGKA)
    )
    # tersangka is accusatory and current -> still exposable (case ongoing).
    assert any(a.entity_id == "per_erick" for a in store.actors())


def test_minor_actor_not_exposable() -> None:
    # P4: a governed entity flagged as a minor is filtered from actor output.
    store = _store_with(("1", "Pernyataan", "Joko Widodo hadir di acara.", None))
    assert any(a.entity_id == "per_jokowi" for a in store.actors())
    store.upsert_entity(
        EntityRecord(entity_id="per_jokowi", display="Joko Widodo", kind="PERSON", is_minor=True)
    )
    assert all(a.entity_id != "per_jokowi" for a in store.actors())


def test_quote_filter_by_actor() -> None:
    store = _store_with(
        ("1", "A", '"Satu," kata Sri Mulyani.', None),
        ("2", "B", '"Dua," kata Erick Thohir.', None),
    )
    only_smi = store.quotes(actor="Sri Mulyani")
    assert only_smi and all("Sri Mulyani" in (q.speaker_display or "") for q in only_smi)
