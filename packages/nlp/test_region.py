"""Gate for region.py — gazetteer regions + title/incident confidence boosts."""

from __future__ import annotations

from packages.nlp.region import RegionScore, extract_regions, load_regions

_RG = load_regions()


def _by_id(scores: list[RegionScore]) -> dict[str, float]:
    return {s.region_id: s.confidence for s in scores}


def test_basic_body_mention() -> None:
    scores = extract_regions("", "Banjir melanda kawasan permukiman.", _RG)
    # no region named -> none
    assert scores == []


def test_alias_resolves_to_province() -> None:
    scores = extract_regions("", "Peristiwa terjadi di Jabar pekan ini.", _RG)
    assert "reg_jabar" in _by_id(scores)


def test_title_mention_outscores_body_mention() -> None:
    in_title = extract_regions("Banjir Besar di Surabaya", "Laporan singkat.", _RG)
    in_body = extract_regions("Laporan singkat", "Banjir terjadi. Surabaya tergenang.", _RG)
    assert _by_id(in_title)["reg_surabaya"] > _by_id(in_body)["reg_surabaya"]


def test_incident_cue_boosts_confidence() -> None:
    with_cue = extract_regions("", "Kebakaran terjadi di Medan tadi malam.", _RG)
    without_cue = extract_regions("", "Tim Medan memenangi laga.", _RG)
    assert _by_id(with_cue)["reg_medan"] > _by_id(without_cue)["reg_medan"]


def test_confidence_bounded() -> None:
    scores = extract_regions(
        "Bencana di Jakarta", "Jakarta terdampak. Wilayah Jakarta lumpuh. di Jakarta.", _RG
    )
    assert all(0.0 <= s.confidence <= 1.0 for s in scores)
    assert _by_id(scores)["reg_dki"] <= 1.0


def test_repeat_body_mentions_add_bounded_bonus() -> None:
    once = extract_regions("", "Kejadian di Bandung.", _RG)
    twice = extract_regions("", "Kejadian di Bandung. Bandung ramai.", _RG)
    assert _by_id(twice)["reg_bandung"] >= _by_id(once)["reg_bandung"]


def test_sorted_desc_and_deterministic() -> None:
    text_title = "Gempa di Bali"
    text_body = "Terasa hingga Surabaya."
    a = extract_regions(text_title, text_body, _RG)
    b = extract_regions(text_title, text_body, _RG)
    assert a == b
    confs = [s.confidence for s in a]
    assert confs == sorted(confs, reverse=True)


def test_country_level_alias() -> None:
    scores = extract_regions("", "Kebijakan berlaku di seluruh NKRI.", _RG)
    assert "reg_id" in _by_id(scores)
