"""Gate for topic.py — keyword classification + category override + bounds."""

from __future__ import annotations

from packages.nlp.topic import DEFAULT_MAX_TOPICS, TopicScore, classify_topics


def _topics(scores: list[TopicScore]) -> list[str]:
    return [s.topic for s in scores]


def test_moneter_story_classified() -> None:
    scores = classify_topics(
        "Bank Indonesia menahan suku bunga acuan untuk menjaga nilai tukar rupiah."
    )
    assert "moneter" in _topics(scores)
    assert scores[0].topic == "moneter"


def test_korupsi_story_classified() -> None:
    scores = classify_topics("KPK menetapkan tersangka baru dalam dugaan korupsi dan suap.")
    assert "korupsi" in _topics(scores)


def test_confidence_is_bounded_0_1() -> None:
    text = "korupsi suap gratifikasi tipikor kpk ott pencucian uang dugaan korupsi"
    scores = classify_topics(text)
    assert all(0.0 < s.confidence < 1.0 for s in scores)


def test_phrase_outweighs_bare_word() -> None:
    # "bank indonesia" (phrase, moneter) should beat a lone "bank" (perbankan).
    scores = classify_topics("Bank Indonesia mengumumkan kebijakan baru.")
    assert scores[0].topic == "moneter"


def test_repetition_does_not_inflate_confidence() -> None:
    once = classify_topics("Terjadi banjir di kota.")
    many = classify_topics("banjir banjir banjir banjir banjir")
    by_topic_once = {s.topic: s.confidence for s in once}
    by_topic_many = {s.topic: s.confidence for s in many}
    # Same single distinct keyword -> identical confidence regardless of count.
    assert by_topic_once["bencana"] == by_topic_many["bencana"]


def test_category_override_seeds_topic_when_text_silent() -> None:
    # Text has no olahraga keywords; the source category should still seed it.
    scores = classify_topics("Pertandingan tadi malam berlangsung seru.", raw_category="Bola")
    assert "olahraga" in _topics(scores)


def test_override_does_not_lower_a_strong_text_signal() -> None:
    scores = classify_topics(
        "KPK menetapkan tersangka korupsi suap gratifikasi.", raw_category="Hukum"
    )
    by_topic = {s.topic: s.confidence for s in scores}
    # korupsi from strong text signal stays above the override floor.
    assert by_topic["korupsi"] > 0.55


def test_max_topics_capped_and_sorted_desc() -> None:
    text = "ekonomi pajak bank saham listrik tambang korupsi pengadilan banjir"
    scores = classify_topics(text, max_topics=DEFAULT_MAX_TOPICS)
    assert len(scores) <= DEFAULT_MAX_TOPICS
    confs = [s.confidence for s in scores]
    assert confs == sorted(confs, reverse=True)


def test_deterministic_and_empty_input() -> None:
    assert classify_topics("") == []
    a = classify_topics("Investasi dan ekspor mendorong pertumbuhan ekonomi.")
    b = classify_topics("Investasi dan ekspor mendorong pertumbuhan ekonomi.")
    assert a == b


def test_word_boundary_prevents_false_match() -> None:
    # "ai" (teknologi) must not fire inside "pandai" / "santai".
    scores = classify_topics("Dia pandai dan santai menghadapi situasi.")
    assert "teknologi" not in _topics(scores)
