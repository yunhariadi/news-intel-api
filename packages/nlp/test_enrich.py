"""Gate for enrich.py — the orchestrator composes the extractors correctly."""

from __future__ import annotations

from packages.nlp.enrich import ArticleEnrichment, build_enricher, enrich_article

_ENR = build_enricher()


def _enrich(title: str, excerpt: str | None, category: str | None = None) -> ArticleEnrichment:
    return enrich_article(
        article_id="a1",
        title=title,
        excerpt=excerpt,
        raw_category=category,
        source_url="https://news.example.id/a/1",
        enricher=_ENR,
    )


def test_full_enrichment_shape() -> None:
    enr = _enrich(
        "Bank Indonesia Tahan Suku Bunga",
        '"Inflasi terkendali," kata Perry Warjiyo di Jakarta.',
        category="Ekonomi",
    )
    assert enr.language == "id"
    assert any(t.topic == "moneter" for t in enr.topics)
    assert any(a.entity_id == "org_bi" for a in enr.actors)
    assert any(a.entity_id == "per_perry" for a in enr.actors)
    assert any(r.region_id == "reg_dki" for r in enr.regions)
    assert enr.quotes and enr.quotes[0].speaker_entity_id == "per_perry"
    assert enr.quotes[0].exposable is True


def test_language_falls_back_to_default_when_unknown() -> None:
    enr = _enrich("Prabowo Jakarta", None, category=None)
    assert enr.language == "id"  # no function words -> default


def test_deterministic() -> None:
    a = _enrich("KPK Periksa Pejabat", "Dugaan korupsi di Surabaya.", "Hukum")
    b = _enrich("KPK Periksa Pejabat", "Dugaan korupsi di Surabaya.", "Hukum")
    assert a == b


def test_no_excerpt_still_enriches_title() -> None:
    enr = _enrich("Pertamina Naikkan Harga BBM", None, "Energi")
    assert any(a.entity_id == "org_pertamina" for a in enr.actors)
    assert any(t.topic == "energi" for t in enr.topics)
