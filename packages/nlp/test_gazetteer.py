"""Gate for gazetteer.py — precision-tuned entity matching + the seed loads."""

from __future__ import annotations

from packages.nlp.gazetteer import Gazetteer, load_organizations

_ENTRIES: list[dict[str, object]] = [
    {"entity_id": "org_bi", "canonical_name": "Bank Indonesia",
     "entity_type": "REGULATOR", "acronyms": ["BI"], "aliases": ["bank sentral"]},
    {"entity_id": "org_ojk", "canonical_name": "Otoritas Jasa Keuangan",
     "entity_type": "REGULATOR", "acronyms": ["OJK"], "aliases": []},
    {"entity_id": "org_kpk", "canonical_name": "Komisi Pemberantasan Korupsi",
     "entity_type": "AGENCY", "acronyms": ["KPK"], "aliases": []},
]


def _gz() -> Gazetteer:
    return Gazetteer(_ENTRIES)


def test_matches_full_name() -> None:
    men = _gz().find_mentions("Bank Indonesia menahan suku bunga.")
    assert [m.entity_id for m in men] == ["org_bi"]
    assert men[0].surface == "Bank Indonesia"


def test_matches_acronym_uppercase() -> None:
    men = _gz().find_mentions("Keputusan OJK dan KPK hari ini.")
    assert {m.entity_id for m in men} == {"org_ojk", "org_kpk"}


def test_acronym_not_matched_in_lowercase_prose() -> None:
    # "bi" appears lowercased inside ordinary words; must not fire org_bi.
    men = _gz().find_mentions("kebijakan itu bias dan biasa saja")
    assert men == []


def test_alias_matches_case_insensitively() -> None:
    men = _gz().find_mentions("Sebagai bank sentral, otoritas itu bertindak.")
    assert [m.entity_id for m in men] == ["org_bi"]


def test_longest_match_wins_on_overlap() -> None:
    # "Bank Indonesia" (name) should win over a hypothetical inner token.
    men = _gz().find_mentions("Bank Indonesia")
    assert len(men) == 1
    assert men[0].surface == "Bank Indonesia"


def test_ambiguous_surface_is_dropped() -> None:
    entries: list[dict[str, object]] = [
        {"entity_id": "a", "canonical_name": "Alpha", "entity_type": "PARTY",
         "acronyms": ["XX"], "aliases": []},
        {"entity_id": "b", "canonical_name": "Beta", "entity_type": "PARTY",
         "acronyms": ["XX"], "aliases": []},
    ]
    men = Gazetteer(entries).find_mentions("Partai XX menang.")
    # "XX" resolves to two entities -> ambiguous -> not emitted.
    assert men == []


def test_word_boundary_prevents_substring_acronym() -> None:
    men = _gz().find_mentions("BIBIT tanaman tumbuh subur")  # contains "BI" as substring
    assert men == []


def test_mentions_sorted_by_position() -> None:
    men = _gz().find_mentions("KPK lalu OJK lalu Bank Indonesia")
    assert [m.start for m in men] == sorted(m.start for m in men)


def test_seed_file_loads_and_matches() -> None:
    gz = load_organizations()
    men = gz.find_mentions("Pertamina dan PLN melapor ke Kementerian Keuangan.")
    ids = {m.entity_id for m in men}
    assert {"org_pertamina", "org_pln", "org_kemenkeu"} <= ids
