"""topic.py — Hybrid topic classifier (Layer A).

A keyword-map classifier over the Indonesian taxonomy (SPEC §10.8) plus a
manual **override** from the source's own `raw_category`. DESIGN.md §5 calls for
"rule-based keyword map + ML + manual override"; the ML stage is a later drop-in
behind the same typed contract — the rules give a strong, deterministic,
test-pinnable baseline and the override lets a source that self-labels "Bola"
seed `olahraga` even when the lede is keyword-thin.

Pure: text in, ranked `TopicScore`s out. Confidence is bounded [0,1] via a
saturating transform so a keyword-stuffed article can't exceed a focused one.
Multi-word phrases weigh more than bare words (they are more specific and less
ambiguous: "bank indonesia" is a stronger moneter signal than "bank").
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Saturation constant: total matched weight at which confidence ≈ 0.86. Tunable
# calibration knob (kept here, not inlined, per CLAUDE.md §4).
_SATURATION: float = 3.0
_PHRASE_WEIGHT: float = 2.0
_WORD_WEIGHT: float = 1.0
DEFAULT_MAX_TOPICS: int = 3
# Confidence a source-category override is seeded with when the text is silent.
_OVERRIDE_FLOOR: float = 0.55


@dataclass(frozen=True)
class TopicScore:
    topic: str
    confidence: float


# Curated keyword map. Values may be single words or multi-word phrases; phrases
# are matched as contiguous substrings (word-bounded), words as whole tokens.
TOPIC_KEYWORDS: dict[str, frozenset[str]] = {
    "politik": frozenset({
        "presiden", "menteri", "dpr", "partai", "pemilu", "koalisi", "kabinet",
        "gubernur", "pilkada", "oposisi", "istana",
    }),
    "ekonomi": frozenset({
        "ekonomi", "pertumbuhan ekonomi", "investasi", "ekspor", "impor",
        "pdb", "neraca dagang", "daya beli",
    }),
    "moneter": frozenset({
        "bank indonesia", "bi rate", "suku bunga", "inflasi", "rupiah",
        "nilai tukar", "kebijakan moneter",
    }),
    "fiskal": frozenset({"apbn", "subsidi", "belanja negara", "defisit anggaran"}),
    "pajak": frozenset({"pajak", "ppn", "djp", "wajib pajak", "tax amnesty"}),
    "perbankan": frozenset({"bank", "kredit", "perbankan", "ojk", "likuiditas"}),
    "pasar_modal": frozenset({"ihsg", "saham", "bursa", "emiten", "ipo", "obligasi"}),
    "komoditas": frozenset({"batu bara", "sawit", "cpo", "nikel", "minyak", "emas"}),
    "energi": frozenset({"energi", "listrik", "pln", "pertamina", "bbm", "gas", "ebt"}),
    "tambang": frozenset({"tambang", "pertambangan", "smelter", "mineral"}),
    "korupsi": frozenset({
        "kpk", "korupsi", "suap", "gratifikasi", "tipikor", "ott",
        "pencucian uang", "dugaan korupsi",
    }),
    "hukum": frozenset({
        "pengadilan", "hakim", "jaksa", "vonis", "putusan", "gugatan",
        "mahkamah", "kejaksaan",
    }),
    "keamanan": frozenset({"polisi", "tni", "teroris", "keamanan", "kapolri"}),
    "infrastruktur": frozenset({"infrastruktur", "jalan tol", "bandara", "pelabuhan", "proyek"}),
    "transportasi": frozenset({"transportasi", "kereta", "mrt", "lrt", "kemacetan"}),
    "kesehatan": frozenset({"kesehatan", "rumah sakit", "vaksin", "bpjs", "wabah", "penyakit"}),
    "pendidikan": frozenset({"pendidikan", "sekolah", "kampus", "guru", "kurikulum", "siswa"}),
    "teknologi": frozenset({"teknologi", "startup", "digital", "aplikasi", "internet", "ai"}),
    "bencana": frozenset({"banjir", "gempa", "longsor", "erupsi", "tsunami", "bencana", "bnpb"}),
    "internasional": frozenset({"asean", "pbb", "amerika", "tiongkok", "diplomasi"}),
    "olahraga": frozenset({"sepak bola", "timnas", "liga", "olahraga", "atlet", "pertandingan"}),
    "hiburan": frozenset({"film", "musik", "artis", "konser", "selebriti"}),
}

# Source self-category → taxonomy topic. Keys are matched case-insensitively
# against `raw_category`.
CATEGORY_OVERRIDE: dict[str, str] = {
    "ekonomi": "ekonomi",
    "bisnis": "ekonomi",
    "finance": "ekonomi",
    "market": "pasar_modal",
    "bursa": "pasar_modal",
    "politik": "politik",
    "hukum": "hukum",
    "kriminal": "keamanan",
    "olahraga": "olahraga",
    "bola": "olahraga",
    "tekno": "teknologi",
    "teknologi": "teknologi",
    "kesehatan": "kesehatan",
    "internasional": "internasional",
    "dunia": "internasional",
    "hiburan": "hiburan",
    "lifestyle": "hiburan",
}


def _saturate(weight: float) -> float:
    """Map accumulated match weight → confidence in (0,1), monotone increasing."""
    return round(weight / (weight + _SATURATION), 4)


def _compile_matcher(keyword: str) -> re.Pattern[str]:
    # Word-bounded so "ai" doesn't fire inside "pandai"; phrases allow internal
    # spaces. \b works because keywords are lowercase ascii words.
    return re.compile(rf"\b{re.escape(keyword)}\b")


_MATCHERS: dict[str, tuple[tuple[re.Pattern[str], float], ...]] = {
    topic: tuple(
        (_compile_matcher(kw), _PHRASE_WEIGHT if " " in kw else _WORD_WEIGHT)
        for kw in sorted(kws)
    )
    for topic, kws in TOPIC_KEYWORDS.items()
}


def classify_topics(
    text: str,
    raw_category: str | None = None,
    max_topics: int = DEFAULT_MAX_TOPICS,
) -> list[TopicScore]:
    """Rank topics for an article.

    Counts distinct matched keywords per topic (each keyword scored at most
    once, so repetition can't inflate), saturates the weight to a bounded
    confidence, then applies the source-category override. Results are sorted by
    confidence desc with a deterministic name tie-break, capped at `max_topics`.
    """
    haystack = text.lower()
    weights: dict[str, float] = {}
    for topic, matchers in _MATCHERS.items():
        total = sum(w for pat, w in matchers if pat.search(haystack))
        if total > 0:
            weights[topic] = total

    scores = {t: _saturate(w) for t, w in weights.items()}

    if raw_category is not None:
        override = CATEGORY_OVERRIDE.get(raw_category.strip().lower())
        if override is not None:
            scores[override] = max(scores.get(override, 0.0), _OVERRIDE_FLOOR)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [TopicScore(topic=t, confidence=c) for t, c in ranked[:max_topics]]
