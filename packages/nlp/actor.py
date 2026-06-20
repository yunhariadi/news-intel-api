"""actor.py — Actor extraction + alias resolution (Layer A).

DESIGN.md §5: handle Indonesian **gelar** (academic/religious titles — `H.`,
`Ir.`, `Dr.`, `Prof.`, and trailing degrees `S.H.`, `M.M.`, `S.E.`) by stripping
them for *matching* while keeping the clean name for *display*; resolve aliases
so "Sri Mulyani", "Sri Mulyani Indrawati", and "Menkeu Sri Mulyani" collapse to
one actor; and fall back to a rule-based PERSON detector for names absent from
the gazetteer (the gazetteer is the backbone, NER is the fallback).

The whole module is pure. Resolution order per mention:
1. gazetteer hit (person or organisation) — authoritative `entity_id`;
2. else a NER-fallback PERSON — `entity_id=None`, identity carried by a
   normalized `canonical_key` so two surface forms of the same unknown name
   still merge.

Precision over recall: a role word (`Presiden`, `Menteri`) is stripped to expose
the name, and TitleCase runs that overlap a gazetteer org/region or sit in the
non-name stoplist are not emitted as people.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from packages.nlp.gazetteer import Gazetteer

# Leading honorific/title tokens (gelar), compared with dots removed, lowercased.
_TITLE_PREFIXES: frozenset[str] = frozenset({
    "h", "hj", "haji", "ir", "dr", "drs", "dra", "prof", "kh", "r", "rr",
    "raden", "st", "tb",
})

# Role/jabatan words that precede a name; stripped so the *name* is the actor.
# Includes descriptor nouns ("pengusaha", "ekonom") that introduce a person.
_ROLE_PREFIXES: frozenset[str] = frozenset({
    "presiden", "wapres", "menteri", "menko", "menkeu", "mendag", "menkes",
    "gubernur", "wagub", "bupati", "walikota", "wali", "ketua", "kepala",
    "direktur", "dirut", "kapolri", "kapolda", "panglima", "jaksa", "hakim",
    "juru", "bicara", "anggota", "senator", "komisaris", "pengusaha", "pakar",
    "ekonom", "pengamat", "aktivis", "tokoh", "politikus", "politisi", "warga",
    "korban", "saksi", "tersangka", "terdakwa",
})

# Domain words that follow a role to form a multi-word title ("Menteri Keuangan
# Sri Mulyani"). Only stripped *after* a role word, never on their own.
_ROLE_DOMAIN: frozenset[str] = frozenset({
    "keuangan", "perdagangan", "kesehatan", "perekonomian", "dalam", "luar",
    "negeri", "pertahanan", "pendidikan", "kebudayaan", "koordinator", "bidang",
    "umum", "energi", "sumber", "daya", "mineral", "komunikasi", "informatika",
    "hukum", "ham", "sosial", "agama", "desa", "pertanian", "perindustrian",
    "perhubungan", "ketenagakerjaan", "investasi", "lingkungan", "hidup",
    "kehutanan", "pariwisata", "kelautan", "perikanan", "bumn",
})

# TitleCase words that are not personal names (months, weekdays, generic nouns,
# and prepositions/connectors that surface TitleCase at a sentence start).
_NOT_A_NAME: frozenset[str] = frozenset({
    "indonesia", "jakarta", "januari", "februari", "maret", "april", "mei",
    "juni", "juli", "agustus", "september", "oktober", "november", "desember",
    "senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu",
    "partai", "bank", "kementerian", "komisi", "badan", "dewan", "mahkamah",
    "republik", "negara", "nasional", "provinsi", "kota", "kabupaten",
    "pada", "kemarin", "menurut", "dalam", "sejak", "hingga", "saat", "ketika",
    "setelah", "sebelum", "namun", "selain", "terkait", "sementara",
})

# A trailing academic degree like ", S.H." / ", M.M." / ", Ph.D." / ", S.E.,M.Si."
_DEG = r"(?:[A-Za-z]{1,4}\.?){1,3}"
_DEGREE_TAIL = re.compile(rf"\s*,\s*{_DEG}(?:\s*,\s*{_DEG})*\s*$")
# A run of TitleCase tokens (the NER-fallback person candidate).
_TITLECASE_RUN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class ActorMention:
    display: str            # clean, gelar-stripped name for presentation
    canonical_key: str      # normalized identity key (alias-merging)
    kind: str               # "PERSON" or a gazetteer entity_type (REGULATOR, …)
    entity_id: str | None   # set when resolved against the gazetteer
    start: int
    end: int


def _strip_token_dots(token: str) -> str:
    return token.replace(".", "").lower()


def strip_gelar(name: str) -> str:
    """Remove leading titles and trailing degrees; keep the display name clean.

    `"Dr. Sri Mulyani Indrawati, S.E., M.Sc."` → `"Sri Mulyani Indrawati"`.
    Idempotent.
    """
    work = _DEGREE_TAIL.sub("", name).strip()
    tokens = work.split()
    i = 0
    while i < len(tokens) - 1 and _strip_token_dots(tokens[i]) in _TITLE_PREFIXES:
        i += 1
    return " ".join(tokens[i:]).strip()


def strip_role_prefix(name: str) -> str:
    """Drop a leading jabatan/role word so the residue is the personal name.

    `"Menteri Keuangan Sri Mulyani"` is handled token-wise: leading role words
    are removed until a non-role TitleCase token remains.
    """
    tokens = name.split()
    i = 0
    stripped_role = False
    while i < len(tokens) - 1 and tokens[i].lower() in _ROLE_PREFIXES:
        i += 1
        stripped_role = True
    if stripped_role:
        while i < len(tokens) - 1 and tokens[i].lower() in _ROLE_DOMAIN:
            i += 1
    return " ".join(tokens[i:]).strip()


def canonical_key(name: str) -> str:
    """Normalized identity key for alias merging: gelar/role-stripped, lowercased,
    punctuation removed, whitespace collapsed."""
    base = strip_role_prefix(strip_gelar(name))
    base = re.sub(r"[^\w\s]", "", base).lower()
    return _WS.sub(" ", base).strip()


def _is_name_like(run: str) -> bool:
    """A run is name-like only if *no* token is non-name vocabulary (a month,
    weekday, generic noun, or sentence-initial preposition). Precision over
    recall: one stop-token poisons the run."""
    tokens = run.split()
    if not tokens:
        return False
    return all(t.lower() not in _NOT_A_NAME for t in tokens)


def extract_actors(text: str, gazetteer: Gazetteer) -> list[ActorMention]:
    """Extract resolved actors from `text`.

    Gazetteer mentions (orgs + known persons) are authoritative; remaining
    TitleCase runs that look like personal names become NER-fallback PERSON
    actors. Output is de-duplicated by identity (entity_id, else canonical_key)
    keeping the earliest mention, and sorted by position.
    """
    mentions: list[ActorMention] = []
    occupied: list[tuple[int, int]] = []

    for g in gazetteer.find_mentions(text):
        mentions.append(
            ActorMention(
                display=g.canonical_name,
                canonical_key=canonical_key(g.canonical_name),
                kind=g.entity_type,
                entity_id=g.entity_id,
                start=g.start,
                end=g.end,
            )
        )
        occupied.append((g.start, g.end))

    for m in _TITLECASE_RUN.finditer(text):
        start, end = m.start(), m.end()
        if any(start < oe and os < end for os, oe in occupied):
            continue  # overlaps a gazetteer mention already taken
        run = strip_role_prefix(m.group(1))
        if not run or len(run.split()) < 2 or not _is_name_like(run):
            continue  # single tokens / non-name vocab → too low precision
        display = strip_gelar(run)
        mentions.append(
            ActorMention(
                display=display,
                canonical_key=canonical_key(display),
                kind="PERSON",
                entity_id=None,
                start=start,
                end=end,
            )
        )

    mentions.sort(key=lambda a: a.start)
    seen: set[str] = set()
    unique: list[ActorMention] = []
    for a in mentions:
        identity = a.entity_id or f"key:{a.canonical_key}"
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(a)
    return unique
