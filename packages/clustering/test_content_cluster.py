"""test_content_cluster.py — CI gate for near-dup clustering + carrier→origin.

Pins the BUILD_ORDER Phase 1 gates:
- SimHash near-dups cluster; distinct stories don't.
- Syndication: N carriers of one wire story -> 1 cluster, 1 origin, carrier_count=N.
- Origin resolution: earliest wire wins, else earliest seen.
- Determinism: input order does not change the result.
"""

from __future__ import annotations

from packages.clustering.content_cluster import (
    ArticleForClustering,
    cluster_content,
    resolve_origin,
)
from packages.utils.hashing import content_fingerprint


def _fp(title: str, lede: str = "") -> int:
    return content_fingerprint(title, lede)


WIRE_TITLE = "Pemerintah umumkan kebijakan subsidi energi baru"
WIRE_LEDE = "Menteri menyampaikan rincian kebijakan dalam konferensi pers."


# --------------------------------------------------------------------------
# Origin resolution (unit)
# --------------------------------------------------------------------------

def test_resolve_origin_prefers_earliest_wire() -> None:
    arts = [
        ArticleForClustering("tribun", "tribun", False, 0, 1.0),
        ArticleForClustering("antara", "antara", True, 0, 2.0),   # wire, but later
        ArticleForClustering("kompas", "kompas", False, 0, 0.5),  # earliest, not wire
    ]
    # Earliest WIRE wins over an earlier non-wire.
    assert resolve_origin(arts) == ("antara", "antara")


def test_resolve_origin_falls_back_to_earliest_seen() -> None:
    arts = [
        ArticleForClustering("late", "kompas", False, 0, 5.0),
        ArticleForClustering("early", "detik", False, 0, 2.0),
    ]
    assert resolve_origin(arts) == ("detik", "early")


# --------------------------------------------------------------------------
# The headline invariant: syndication collapses to one origin
# --------------------------------------------------------------------------

def test_syndicated_wire_collapses_to_one_origin() -> None:
    base = _fp(WIRE_TITLE, WIRE_LEDE)
    arts = [
        ArticleForClustering("a_antara", "antara", True, base, 0.0),   # wire origin
        ArticleForClustering("a_tribun", "tribun", False, base, 1.0),
        ArticleForClustering("a_kompas", "kompas", False, base, 2.0),
        ArticleForClustering("a_detik", "detik", False, base, 3.0),
    ]
    clusters = cluster_content(arts)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.carrier_count == 4
    assert c.origin_source_id == "antara"
    assert c.origin_article_id == "a_antara"
    assert c.first_seen_hours == 0.0


def test_distinct_stories_do_not_cluster() -> None:
    a = ArticleForClustering("x", "antara", True, _fp("Pemerintah umumkan subsidi energi"), 0.0)
    b = ArticleForClustering("y", "kompas", False, _fp("Timnas menang telak di laga final"), 0.0)
    clusters = cluster_content([a, b])
    assert len(clusters) == 2


def test_outside_time_window_does_not_cluster() -> None:
    base = _fp("Harga BBM naik mulai pekan depan")
    a = ArticleForClustering("a", "antara", True, base, 0.0)
    b = ArticleForClustering("b", "kompas", False, base, 100.0)  # > 48h apart
    clusters = cluster_content([a, b])
    assert len(clusters) == 2


def test_no_wire_in_cluster_uses_earliest_seen_origin() -> None:
    base = _fp("Banjir melanda Jakarta Selatan dini hari")
    arts = [
        ArticleForClustering("late", "kompas", False, base, 5.0),
        ArticleForClustering("early", "detik", False, base, 2.0),
        ArticleForClustering("mid", "cnbc", False, base, 3.0),
    ]
    c = cluster_content(arts)[0]
    assert c.carrier_count == 3
    assert c.origin_source_id == "detik"
    assert c.origin_article_id == "early"


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def test_clustering_is_order_independent() -> None:
    base = _fp("Inflasi tahunan tercatat melambat pada kuartal ini")
    other = _fp("Bursa saham ditutup menguat tajam sore ini")
    arts = [
        ArticleForClustering("a_antara", "antara", True, base, 0.0),
        ArticleForClustering("a_tribun", "tribun", False, base, 1.0),
        ArticleForClustering("b_kompas", "kompas", False, other, 0.0),
    ]
    assert cluster_content(arts) == cluster_content(list(reversed(arts)))
