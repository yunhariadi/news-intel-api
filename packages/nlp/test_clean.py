"""Gate for clean.py — boilerplate stripping + language detection."""

from __future__ import annotations

from packages.nlp.clean import (
    clean_text,
    detect_language,
    normalize_quotes,
    strip_dateline,
    strip_html,
)


def test_strip_html_collapses_whitespace() -> None:
    assert strip_html("<p>Halo   <b>dunia</b></p>") == "Halo dunia"


def test_normalize_quotes_maps_typographic_to_ascii() -> None:
    assert normalize_quotes("“Halo,” ujarnya") == '"Halo," ujarnya'
    assert normalize_quotes("’Ia’") == "'Ia'"


def test_strip_dateline_antara_parenthetical() -> None:
    assert strip_dateline("JAKARTA (ANTARA) - Pemerintah menaikkan subsidi.") == (
        "Pemerintah menaikkan subsidi."
    )


def test_strip_dateline_outlet_dotcom() -> None:
    assert strip_dateline("JAKARTA, KOMPAS.com - Bank Indonesia menahan suku bunga.") == (
        "Bank Indonesia menahan suku bunga."
    )


def test_strip_dateline_is_idempotent_and_safe_on_plain_text() -> None:
    plain = "Sri Mulyani mengatakan ekonomi tumbuh."
    assert strip_dateline(plain) == plain
    once = strip_dateline("MEDAN - Banjir melanda kota.")
    assert strip_dateline(once) == once == "Banjir melanda kota."


def test_strip_dateline_does_not_eat_a_normal_capitalized_sentence() -> None:
    # "Presiden" is title-case but not an all-caps dateline — must survive.
    text = "Presiden Prabowo - dalam pidatonya - menegaskan hal itu."
    assert strip_dateline(text) == text


def test_clean_text_full_pipeline() -> None:
    raw = "<p>JAKARTA (ANTARA) - “Subsidi naik,” kata Menteri.</p>"
    assert clean_text(raw) == '"Subsidi naik," kata Menteri.'


def test_detect_language_indonesian() -> None:
    assert detect_language("Pemerintah akan menaikkan subsidi untuk masyarakat") == "id"


def test_detect_language_english() -> None:
    assert detect_language("The government is going to raise the subsidy for the people") == "en"


def test_detect_language_unknown_when_no_function_words() -> None:
    assert detect_language("Prabowo Subianto Jakarta") == "unknown"
    assert detect_language("") == "unknown"
    assert detect_language("12345 !!!") == "unknown"


def test_detect_language_tie_favours_indonesian() -> None:
    # one id stopword, zero en -> id; balanced handled by >.
    assert detect_language("di Jakarta") == "id"
