"""test_hashing.py — CI gate for the two article hashes + SimHash primitives.

Pins the dedup correctness the spec got wrong (CLAUDE.md "Do Not"): the content
fingerprint must be SOURCE-INDEPENDENT so the same story across carriers collides,
and the dedup key must be URL-based so exact refetch is idempotent.
"""

from __future__ import annotations

from packages.utils.hashing import content_fingerprint, dedup_key
from packages.utils.simhash import hamming_distance, simhash64
from packages.utils.text import normalize_for_fingerprint, tokenize

# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def test_normalize_strips_case_and_punctuation() -> None:
    assert normalize_for_fingerprint("Harga BBM, Naik!!  ") == "harga bbm naik"
    assert normalize_for_fingerprint("  Multiple   spaces\tand\nnewlines ") == (
        "multiple spaces and newlines"
    )


def test_tokenize_empty_is_empty() -> None:
    assert tokenize("") == []
    assert tokenize("   !!! ") == []


# --------------------------------------------------------------------------
# SimHash primitives
# --------------------------------------------------------------------------

def test_simhash_is_deterministic_across_calls() -> None:
    # Not Python's salted hash(): same tokens -> same fingerprint, every run.
    tokens = ["pemerintah", "umumkan", "subsidi", "energi"]
    assert simhash64(tokens) == simhash64(tokens)


def test_simhash_empty_is_zero() -> None:
    assert simhash64([]) == 0
    assert content_fingerprint("", "") == 0


def test_identical_content_zero_distance() -> None:
    a = content_fingerprint("Banjir melanda Jakarta Selatan", "Hujan deras semalam.")
    b = content_fingerprint("Banjir melanda Jakarta Selatan", "Hujan deras semalam.")
    assert hamming_distance(a, b) == 0


def test_minor_edit_closer_than_unrelated_story() -> None:
    base = content_fingerprint("Pemerintah umumkan kebijakan subsidi energi baru hari ini")
    near = content_fingerprint("Pemerintah umumkan kebijakan subsidi energi baru pagi ini")
    far = content_fingerprint("Klub sepak bola lokal menang telak di pertandingan final")
    assert hamming_distance(base, near) < hamming_distance(base, far)


# --------------------------------------------------------------------------
# The headline invariant: fingerprint is source-independent
# --------------------------------------------------------------------------

def test_fingerprint_is_source_independent() -> None:
    """INVARIANT: the same story carried by different outlets has the SAME
    fingerprint — source/date are deliberately not in it."""
    title = "Pemerintah umumkan kebijakan subsidi energi baru"
    lede = "Menteri menyampaikan rincian kebijakan dalam konferensi pers."
    antara = content_fingerprint(title, lede)
    tribun = content_fingerprint(title, lede)
    kompas = content_fingerprint(title, lede)
    assert antara == tribun == kompas
    assert hamming_distance(antara, kompas) == 0


# --------------------------------------------------------------------------
# dedup_key
# --------------------------------------------------------------------------

def test_dedup_key_is_url_based_stable_and_idempotent() -> None:
    assert dedup_key("https://x.id/a") == dedup_key("https://x.id/a")
    assert dedup_key("  https://x.id/a  ") == dedup_key("https://x.id/a")  # trimmed
    assert dedup_key("https://x.id/a") != dedup_key("https://x.id/b")
    assert len(dedup_key("https://x.id/a")) == 64  # sha256 hex digest
