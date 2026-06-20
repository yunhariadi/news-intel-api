"""test_rss.py — Golden-file gate for the RSS adapter.

A saved feed snapshot maps to an exact normalized output. If a feed/HTML shape
change or a normalization regression alters extraction, the golden comparison
goes red. Behavioral asserts below pin the specific guarantees (excerpt cap,
UTC conversion, tracking-strip, skip-on-missing-link) so a wrong-but-consistent
golden can't silently pass review.

Regenerate the golden intentionally (after eyeballing the diff) with:
    python -c "import json,pathlib; from packages.schemas.article import SourceConfig; \
from packages.source_adapters.rss import parse_rss; \
p=pathlib.Path('tests/fixtures/feeds'); \
print(json.dumps([a.model_dump(mode='json') for a in \
parse_rss((p/'antara_sample.xml').read_bytes(), SOURCE)], indent=2))"
"""

from __future__ import annotations

import json
from datetime import UTC, timedelta
from pathlib import Path

from packages.schemas.article import SourceConfig
from packages.source_adapters.rss import canonicalize_url, parse_rss

_FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "feeds"
SOURCE = SourceConfig(source_id="antara", name="ANTARA", is_wire=True, default_tz="Asia/Jakarta")


def _parse_sample() -> list[dict[str, object]]:
    raw = (_FIXTURES / "antara_sample.xml").read_bytes()
    return [a.model_dump(mode="json") for a in parse_rss(raw, SOURCE)]


def test_matches_golden() -> None:
    expected = json.loads((_FIXTURES / "antara_sample.expected.json").read_text("utf-8"))
    assert _parse_sample() == expected


def test_item_without_link_is_skipped() -> None:
    # The fixture has three <item>s; one has no <link> and must be dropped.
    raw = (_FIXTURES / "antara_sample.xml").read_bytes()
    arts = parse_rss(raw, SOURCE)
    assert len(arts) == 2
    assert all(a.url for a in arts)


def test_excerpt_capped_and_html_stripped() -> None:
    raw = (_FIXTURES / "antara_sample.xml").read_bytes()
    first = parse_rss(raw, SOURCE)[0]
    assert first.excerpt is not None
    assert len(first.excerpt) <= 300            # compliance C1
    assert "<" not in first.excerpt and ">" not in first.excerpt


def test_pubdate_converted_to_utc() -> None:
    raw = (_FIXTURES / "antara_sample.xml").read_bytes()
    first = parse_rss(raw, SOURCE)[0]
    assert first.published_at is not None
    assert first.published_at.utcoffset() == timedelta(0)  # stored in UTC
    # 08:30 +0700 -> 01:30Z
    assert first.published_at.astimezone(UTC).isoformat() == "2026-06-16T01:30:00+00:00"
    assert first.published_tz == "Asia/Jakarta"


def test_canonicalize_strips_tracking_keeps_url() -> None:
    dirty = "https://x.id/a?utm_source=rss&id=42&fbclid=zzz&ref=home#frag"
    assert canonicalize_url(dirty) == "https://x.id/a?id=42"
    # The raw url is preserved on the article; only canonical_url is cleaned.
    raw = (_FIXTURES / "antara_sample.xml").read_bytes()
    first = parse_rss(raw, SOURCE)[0]
    assert "utm_source" in first.url
    assert "utm_source" not in first.canonical_url
