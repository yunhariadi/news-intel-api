"""Gate for actor.py — gelar stripping, alias merge, NER fallback, precision."""

from __future__ import annotations

from packages.nlp.actor import (
    ActorMention,
    canonical_key,
    extract_actors,
    strip_gelar,
    strip_role_prefix,
)
from packages.nlp.gazetteer import Gazetteer, load_entities

_GZ = load_entities()


def _displays(ms: list[ActorMention]) -> list[str]:
    return [m.display for m in ms]


# --- gelar / role normalization -------------------------------------------

def test_strip_leading_titles() -> None:
    assert strip_gelar("Dr. Sri Mulyani Indrawati") == "Sri Mulyani Indrawati"
    assert strip_gelar("H. Joko Widodo") == "Joko Widodo"
    assert strip_gelar("Ir. Prof. Dr. Bambang") == "Bambang"


def test_strip_trailing_degrees() -> None:
    assert strip_gelar("Sri Mulyani Indrawati, S.E., M.Sc.") == "Sri Mulyani Indrawati"
    assert strip_gelar("Mahfud MD, S.H.") == "Mahfud MD"


def test_strip_gelar_is_idempotent() -> None:
    once = strip_gelar("Dr. Sri Mulyani, S.E.")
    assert strip_gelar(once) == once == "Sri Mulyani"


def test_strip_role_prefix() -> None:
    assert strip_role_prefix("Menteri Keuangan Sri Mulyani") == "Sri Mulyani"
    assert strip_role_prefix("Presiden Prabowo Subianto") == "Prabowo Subianto"


def test_canonical_key_merges_aliases() -> None:
    assert canonical_key("Dr. Sri Mulyani Indrawati, S.E.") == "sri mulyani indrawati"
    assert canonical_key("Menteri Sri Mulyani Indrawati") == "sri mulyani indrawati"


# --- gazetteer-backed resolution ------------------------------------------

def test_known_person_alias_resolves_to_entity() -> None:
    ms = extract_actors("Menurut Sri Mulyani, ekonomi tumbuh.", _GZ)
    smi = [m for m in ms if m.entity_id == "per_smi"]
    assert smi and smi[0].display == "Sri Mulyani Indrawati"


def test_same_actor_two_aliases_dedupe_to_one() -> None:
    text = "Sri Mulyani Indrawati hadir. Sri Mulyani memberi sambutan."
    ms = extract_actors(text, _GZ)
    assert sum(m.entity_id == "per_smi" for m in ms) == 1


def test_organization_actor_resolved_with_type() -> None:
    ms = extract_actors("Bank Indonesia dan OJK menggelar rapat.", _GZ)
    kinds = {m.entity_id: m.kind for m in ms}
    assert kinds.get("org_bi") == "REGULATOR"
    assert kinds.get("org_ojk") == "REGULATOR"


# --- NER fallback (unknown names) -----------------------------------------

def test_ner_fallback_detects_unknown_person() -> None:
    ms = extract_actors("Pengusaha Budi Hartono memberi keterangan.", _GZ)
    budi = [m for m in ms if m.canonical_key == "budi hartono"]
    assert budi and budi[0].entity_id is None and budi[0].kind == "PERSON"


def test_ner_fallback_strips_role_prefix() -> None:
    ms = extract_actors("Gubernur Anies Baswedan berbicara.", _GZ)
    keys = {m.canonical_key for m in ms}
    assert "anies baswedan" in keys


def test_single_capitalized_word_is_not_a_person() -> None:
    # Sentence-initial lone capitals are too noisy to emit.
    ms = extract_actors("Kemarin terjadi sesuatu.", _GZ)
    assert ms == []


def test_month_and_place_words_not_actors() -> None:
    ms = extract_actors("Pada Januari, Jakarta diguyur hujan.", _GZ)
    assert all(m.kind != "PERSON" for m in ms)


def test_output_sorted_and_deterministic() -> None:
    text = "OJK memanggil Erick Thohir dan Sri Mulyani."
    a = extract_actors(text, _GZ)
    b = extract_actors(text, _GZ)
    assert a == b
    assert [m.start for m in a] == sorted(m.start for m in a)


def test_empty_text() -> None:
    assert extract_actors("", _GZ) == []


def test_repeated_calls_are_pure_and_stable() -> None:
    text = "Bank Indonesia bertindak; Erick Thohir hadir."
    first = extract_actors(text, _GZ)
    second = extract_actors(text, _GZ)
    assert first == second  # no hidden state / mutation between calls


def test_construct_actor_from_small_gazetteer() -> None:
    gz = Gazetteer([
        {"entity_id": "x", "canonical_name": "Contoh Orang", "entity_type": "PERSON",
         "acronyms": [], "aliases": []},
    ])
    ms = extract_actors("Contoh Orang hadir.", gz)
    assert ms[0].entity_id == "x"
