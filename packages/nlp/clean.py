"""clean.py — Text cleaning + language detection (Layer A).

Pure normalization that prepares feed text for downstream extractors. Distinct
from `utils/text.py` (which produces the aggressive, source-independent token
stream for fingerprinting): here we keep casing and punctuation because the
quote/actor/region extractors need them (capitalization marks names, `"` marks
quotes). What we strip is *boilerplate*: HTML, curly-quote variants, and the
Indonesian wire **dateline** prefix (`JAKARTA (ANTARA) -`, `JAKARTA,
KOMPAS.com -`) that would otherwise be misread as a place mention or speaker.

Language detection is a deterministic stopword-ratio heuristic — no model, no
network — good enough to gate `id`/`en` so non-Indonesian items skip the
Indonesian-tuned extractors.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# A wire dateline: an UPPERCASE place (optionally multi-word), an optional
# parenthetical/agency or "<Outlet>.com", then a dash. Anchored to the string
# start and deliberately conservative so it can't eat a real sentence.
_DATELINE = re.compile(
    r"^\s*[A-Z][A-Z][A-Z .'-]{1,28}?,?\s*"       # PLACE (>=3 upper chars)
    r"(?:\([^)]{1,30}\)|[A-Za-z]+\.com)?\s*"      # (ANTARA) | KOMPAS.com (optional)
    r"[-–—]\s+"          # hyphen / en-dash / em-dash separator
)

# Curly / typographic quotes -> ASCII, so the quote extractor matches one form.
# Spelled as \u escapes (not literals) to stay unambiguous in source.
_QUOTE_MAP = {
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "«": '"', "»": '"',
}
_QUOTE_TABLE = str.maketrans(_QUOTE_MAP)

# Function-word fingerprints. Indonesian vs English; deliberately small and
# high-signal so the ratio is stable on short ledes.
_ID_STOP = frozenset({
    "yang", "dan", "di", "dari", "untuk", "dengan", "pada", "ini", "itu",
    "adalah", "akan", "tidak", "dalam", "ke", "tersebut", "oleh", "juga",
    "para", "kata", "atau", "karena", "saya", "kami", "mereka", "ada", "sudah",
})
_EN_STOP = frozenset({
    "the", "and", "of", "to", "in", "is", "for", "that", "with", "on", "as",
    "are", "was", "by", "be", "this", "from", "or", "an", "it", "at", "has",
})

_WORD = re.compile(r"[a-z]+")


def normalize_quotes(text: str) -> str:
    """Map typographic quote characters to ASCII `"` / `'`."""
    return text.translate(_QUOTE_TABLE)


def strip_html(text: str) -> str:
    """Remove tags and collapse whitespace. Feeds sometimes embed markup in
    `description`."""
    return _WS.sub(" ", _TAG.sub(" ", text)).strip()


def strip_dateline(text: str) -> str:
    """Drop a leading wire dateline prefix if present. Idempotent."""
    return _DATELINE.sub("", text, count=1).lstrip()


def clean_text(raw: str) -> str:
    """Full cleaning for extractor input: de-HTML, normalize quotes, collapse
    whitespace, then strip a dateline. Order matters — HTML first so a tag can't
    hide the dateline."""
    return strip_dateline(normalize_quotes(strip_html(raw)))


def detect_language(text: str) -> str:
    """Return `"id"`, `"en"`, or `"unknown"` from stopword ratios.

    Deterministic and dependency-free. Ties go to `id` (this is an Indonesian
    corpus); no recognizable function words → `unknown` so the caller can fall
    back to the source's declared language rather than mislabel.
    """
    tokens = _WORD.findall(text.lower())
    if not tokens:
        return "unknown"
    id_hits = sum(t in _ID_STOP for t in tokens)
    en_hits = sum(t in _EN_STOP for t in tokens)
    if id_hits == 0 and en_hits == 0:
        return "unknown"
    return "en" if en_hits > id_hits else "id"
