# news-intel-api

**Indonesia News Intelligence API.** An API-first system that turns Indonesian
online news into structured intelligence: trending topics, actors, and regions;
attributed quotes; event clusters with timelines; and source comparison — served
as developer-friendly JSON.

It is a **metadata and intelligence layer, not a news republisher.** It returns
titles, short excerpts, abstractive summaries, attributed quotes, entities, and
trend scores — always with a link back to the origin. It never returns full
article bodies. (This is a legal constraint — see [`COMPLIANCE.md`](./COMPLIANCE.md).)

> **MVP niche:** Indonesia **Policy + Economy** news intelligence — for financial
> analysts, government-affairs and PR teams, legal and energy firms, and
> political-risk researchers. Start narrow; expand later.

---

## Building this with an AI coding agent

This repo is written to be built by an AI coding agent (e.g. Claude Code). The
documents below are the agent's instructions and **override the raw product
spec** wherever they differ — the spec has a few correct-looking but wrong
shortcuts that these docs deliberately fix.

| File                                   | Purpose                                              |
|----------------------------------------|------------------------------------------------------|
| [`CLAUDE.md`](./CLAUDE.md)             | Agent operating manual. **Read first.** Prime Directives, Layer A/B rules, conventions, "do not" list. |
| [`DESIGN.md`](./DESIGN.md)             | Architecture + corrected algorithms (dedup, syndication, trending, events, NLP, provenance). |
| [`COMPLIANCE.md`](./COMPLIANCE.md)     | Indonesian regulatory invariants (UU PDP, Publisher Rights, UU ITE, copyright) as enforceable rules. |
| [`BUILD_ORDER.md`](./BUILD_ORDER.md)   | Phased plan (v0.1→v0.5) with definition-of-done and CI gates per phase. |
| `docs/SPEC.md`                         | Original product spec (reference only; superseded by the above). |

**Agent, start here:** read `CLAUDE.md`, then `BUILD_ORDER.md`, then implement
Phase 0. For each component: typed contract → pure Layer A core → its pytest gate
→ wire-up. The Prime Directives are non-negotiable.

---

## The five things that make this correct (and most aggregators wrong)

1. **Syndication-aware.** Indonesian media runs on wire copy (ANTARA, Tribun
   Network, cross-posting). Source diversity is counted over *distinct original
   sources*, not URLs — so 30 reposts of one wire story count as one source, not
   thirty.
2. **Bounded, stable trends.** No `current/prev` growth multiplier (it explodes
   on cold starts). Burst is a clamped, additive signal on top of
   diversity-weighted volume. Scores normalize 0–100 so webhook thresholds hold
   over time. Reference implementation: [`packages/ranking/trending.py`](./packages/ranking/trending.py).
3. **Honest provenance.** `published_at` (claimed by the feed) and
   `first_seen_by_us` (our trusted clock) are separate. "First reported" means
   "first observed by us" unless stronger provenance exists.
4. **Compliance is code.** Suspect labels disappear on acquittal; quotes deep-link
   to their source paragraph; suppressed/erased subjects vanish from every
   response — all enforced by tests, not vigilance.
5. **Layer A / Layer B.** All deterministic logic (dedup, scoring, clustering,
   compliance) is pure and tested *before* any LLM touches the data. LLMs only
   narrate (summaries, event titles) and never feed back into a decision.

---

## Quickstart

```bash
cp .env.example .env          # then edit secrets
make up                       # docker compose: postgres+pgvector, redis, api, worker
curl localhost:8000/v1/health # {"meta":{...},"data":{"status":"ok",...}}

make test                     # pytest across packages (includes the trending gate)
make lint                     # ruff + mypy --strict
```

Run the canonical Layer A gates directly:
```bash
pytest -q packages/ranking/test_trending.py        # 25 trending invariants
pytest -q packages/compliance/test_invariants.py   # 12 compliance invariants
```

---

## Architecture (brief)

```
Sources → Ingestion → Content clustering (anti-syndication) → NLP enrichment
        → Event clustering (stable IDs) → Ranking (bounded) → API (JSON)
```

Two clustering layers: `content_cluster` (near-duplicates / same story, many
carriers) and `event` (related-but-distinct articles over time). Diversity is
counted over origins across content clusters. Full detail in
[`DESIGN.md`](./DESIGN.md).

---

## Stack

Python 3.12 · FastAPI · PostgreSQL + pgvector (Postgres FTS for v0.1 — **no
OpenSearch until a later phase**) · Redis · APScheduler (→ Celery later) ·
hybrid NLP (rules + gazetteer + Indonesian NER, LLM only for narration).

## Repository layout

```
apps/{api,worker}        packages/{source_adapters,nlp,ranking,clustering,
                                   compliance,schemas,db,utils}
```

## Legal

This software is a metadata/intelligence layer. Operators are responsible for
respecting robots.txt, publisher terms, and Indonesian law (UU PDP, Perpres
32/2024 Publisher Rights, UU ITE, UU Hak Cipta). See [`COMPLIANCE.md`](./COMPLIANCE.md)
and obtain local legal review before commercial launch.
