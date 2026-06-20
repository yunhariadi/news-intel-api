"""Gate for quote.py — pattern coverage, pronoun continuation, compliance fields."""

from __future__ import annotations

from packages.nlp.clean import clean_text
from packages.nlp.gazetteer import load_entities
from packages.nlp.quote import Quote, extract_quotes

_GZ = load_entities()
_URL = "https://news.example.id/a/123"


def _q(text: str) -> list[Quote]:
    return extract_quotes(clean_text(text), _URL, _GZ)


def test_trailing_attribution_named_speaker() -> None:
    quotes = _q('"Ekonomi tumbuh kuat," kata Sri Mulyani.')
    assert len(quotes) == 1
    q = quotes[0]
    assert q.quote_text == "Ekonomi tumbuh kuat"
    assert q.speaker_entity_id == "per_smi"
    assert q.speaker_display == "Sri Mulyani Indrawati"
    assert q.method == "trailing"
    assert q.exposable is True


def test_leading_attribution_bahwa() -> None:
    quotes = _q('Perry Warjiyo menegaskan bahwa "suku bunga tetap."')
    assert len(quotes) == 1
    assert quotes[0].method == "leading"
    assert quotes[0].speaker_entity_id == "per_perry"
    assert quotes[0].quote_text == "suku bunga tetap."


def test_split_quote_rejoins_fragments() -> None:
    quotes = _q('"Kami optimistis," kata Erick Thohir, "target tercapai."')
    assert len(quotes) == 1
    q = quotes[0]
    assert q.method == "split"
    assert q.quote_text == "Kami optimistis target tercapai."
    assert q.speaker_entity_id == "per_erick"


def test_pronoun_continuation_resolves_to_last_speaker() -> None:
    text = '"Pertumbuhan stabil," kata Sri Mulyani. "Inflasi terkendali," katanya.'
    quotes = _q(text)
    assert len(quotes) == 2
    cont = quotes[1]
    assert cont.method == "continuation"
    assert cont.speaker_inferred is True
    assert cont.speaker_display == "Sri Mulyani Indrawati"  # inherited
    assert cont.confidence < quotes[0].confidence


def test_pronoun_ia_leading_continuation() -> None:
    text = 'Sri Mulyani mengatakan "anggaran aman." Ia menambahkan, "belanja efisien."'
    quotes = _q(text)
    assert len(quotes) == 2
    assert quotes[1].speaker_inferred is True
    assert quotes[1].speaker_display == "Sri Mulyani Indrawati"


def test_every_quote_has_source_paragraph_url() -> None:
    quotes = _q('"Halo dunia," kata Erick Thohir.')
    assert all(q.source_paragraph_url.startswith(_URL + "#:~:text=") for q in quotes)


def test_unknown_speaker_below_floor_not_exposable() -> None:
    # A bare quote with no attribution -> low confidence -> not exposable (I1).
    quotes = _q('"Sesuatu terjadi."')
    assert len(quotes) == 1
    assert quotes[0].speaker_display is None
    assert quotes[0].confidence < 0.75
    assert quotes[0].exposable is False


def test_inferred_continuation_with_no_prior_speaker_not_exposable() -> None:
    quotes = _q('"Tanpa rujukan," katanya.')
    assert quotes[0].speaker_inferred is True
    assert quotes[0].speaker_display is None
    assert quotes[0].exposable is False  # no speaker to inherit


def test_attribution_status_always_as_published() -> None:
    # The extractor only emits verbatim text (I3): never 'inferred' verbatim.
    quotes = _q('"Verbatim," kata Joko Widodo. "Lanjutan," katanya.')
    assert all(q.attribution_status == "as_published" for q in quotes)


def test_gazetteer_resolved_speaker_scores_higher_than_unknown_name() -> None:
    known = _q('"A," kata Joko Widodo.')[0]
    unknown = _q('"A," kata Bambang Sutrisno.')[0]
    assert known.confidence >= unknown.confidence
    assert unknown.exposable is True  # named, above floor, just no entity id


def test_deterministic_and_empty() -> None:
    assert _q("Tidak ada kutipan di sini.") == []
    a = _q('"X," kata Erick Thohir.')
    b = _q('"X," kata Erick Thohir.')
    assert a == b
