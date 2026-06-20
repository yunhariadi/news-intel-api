# DESIGN.md — Architecture & Algorithms for `news-intel-api`

This document explains the *why* behind the build. Where it conflicts with the
original product spec (`docs/SPEC.md`), this document and `CLAUDE.md` win. The
spec's data model and trending formula contain defects that are corrected here.

---

## 1. System overview

```
┌──────────────┐   ┌───────────────┐   ┌────────────────────┐   ┌──────────────┐
│   Sources    │ → │   Ingestion   │ → │ Content clustering │ → │ NLP enrich   │
│ RSS/sitemap/ │   │ fetch·norm·   │   │ near-dup → origin  │   │ topic·entity·│
│ licensed     │   │ dedup·store   │   │ (anti-syndication) │   │ region·quote │
└──────────────┘   └───────────────┘   └────────────────────┘   └──────────────┘
                                                                        │
                          ┌─────────────────────────────────────────────┘
                          ▼
                ┌──────────────────┐   ┌──────────────┐   ┌──────────────┐
                │ Event clustering │ → │   Ranking    │ → │  API (JSON)  │
                │ entity+time,     │   │ bounded,     │   │ keys·limits· │
                │ stable online IDs│   │ syndic-aware │   │ webhooks     │
                └──────────────────┘   └──────────────┘   └──────────────┘
```

Layer A (deterministic, pure, tested): dedup, fingerprinting, content & event
clustering math, all ranking, compliance predicates.
Layer B (LLM, display-only): abstractive summaries, event titles.

---

## 2. Data model (corrected)

Key changes from the spec, with rationale.

### 2.1 `sources`
As in spec, plus an explicit origin concept. Add `is_wire BOOLEAN` (true for
ANTARA and other agencies) and `parent_network_id` (Tribun Network etc.), so the
origin resolver can collapse carriers.

### 2.2 `articles` (changed)
```sql
CREATE TABLE articles (
  id UUID PRIMARY KEY,
  source_id UUID REFERENCES sources(id),
  url TEXT NOT NULL UNIQUE,
  canonical_url TEXT,
  title TEXT NOT NULL,
  excerpt TEXT,                      -- HARD-CAPPED length (see compliance)
  summary TEXT,                      -- Layer B, abstractive, attributed
  dedup_key TEXT NOT NULL,           -- sha256(canonical_url)  [exact re-fetch]
  content_fingerprint BIGINT,        -- 64-bit SimHash over title+lede [near-dup]
  content_cluster_id UUID,           -- near-duplicate group
  original_source_id UUID            -- carrier→origin resolution result
      REFERENCES sources(id),
  published_at TIMESTAMPTZ,          -- CLAIMED by feed (untrusted)
  published_tz TEXT,                 -- WIB/WITA/WIT of the source
  first_seen_by_us TIMESTAMPTZ       -- our monotonic ingestion time (trusted)
      DEFAULT now(),
  provenance_confidence FLOAT DEFAULT 0,
  collected_at TIMESTAMPTZ DEFAULT now(),
  language TEXT DEFAULT 'id',
  raw_category TEXT,
  event_id UUID,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
```
Note the two hashes and the two timestamps. These two pairs are the heart of the
correctness fixes.

### 2.3 `content_clusters` (new)
```sql
CREATE TABLE content_clusters (
  id UUID PRIMARY KEY,
  representative_article_id UUID REFERENCES articles(id),
  origin_source_id UUID REFERENCES sources(id),   -- the single original source
  carrier_count INTEGER DEFAULT 1,
  first_seen_by_us TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```
**Source diversity counts distinct origin sources across the articles of an
event, deduplicated through their content_cluster, not raw article rows.**

### 2.4 `entities` (changed — legal lifecycle)
Add a status lifecycle so suspect labels are governed:
```sql
ALTER TABLE entities ADD COLUMN legal_status TEXT;     -- see enum below
ALTER TABLE entities ADD COLUMN legal_status_updated_at TIMESTAMPTZ;
ALTER TABLE entities ADD COLUMN suppressed BOOLEAN DEFAULT FALSE; -- erasure/rectify
```
`legal_status ∈ {terlapor, saksi, tersangka, terdakwa, terpidana, bebas, sp3}`.
When status moves to `bebas`/`sp3` (acquittal/case-dropped), the prior accusatory
label becomes **unexposable** by the compliance layer. See `COMPLIANCE.md`.

### 2.5 `quotes` (changed)
Add the fields that make a quote safe to serve:
```sql
ALTER TABLE quotes ADD COLUMN source_paragraph_url TEXT;  -- deep link for verify
ALTER TABLE quotes ADD COLUMN attribution_status TEXT;    -- as_published|inferred
ALTER TABLE quotes ADD COLUMN exposable BOOLEAN DEFAULT FALSE; -- gate on confidence
```

### 2.6 `events`, `trend_snapshots`
As in spec. `events.id` is **stable**; assignment is incremental (see §6).
`trend_snapshots` additionally stores the rolling `reference_scale` (P95 of raw
scores) used to normalize, so thresholds stay stable across windows.

---

## 3. Deduplication (two hashes, never one) — DONE (Layer A core)

Implemented + pytest-gated: `packages/utils/{text,simhash,hashing}.py` (the two
hashes) and `packages/clustering/content_cluster.py` (near-dup grouping +
carrier→origin resolution). The worker still has to feed these from storage and
persist clusters (remaining Phase 1 I/O work).

The spec's `sha256(title + source + date)` is wrong: including `source` means the
same wire story on 30 carriers hashes 30 different ways. Use two independent
mechanisms:

- **Exact re-fetch** → `dedup_key = sha256(canonical_url)`. Unique constraint;
  re-ingesting the same URL is idempotent.
- **Near-duplicate across outlets** → `content_fingerprint` = 64-bit **SimHash**
  over the normalized `title + lede`, **source-independent**. Two articles with
  Hamming distance ≤ K (start K=3) and `first_seen` within 48h are the same
  content → same `content_cluster`.

Then **carrier → origin resolution**: within a content_cluster, the origin is the
earliest `first_seen_by_us` whose source `is_wire`, else the earliest seen. All
carriers inherit `original_source_id = origin`.

Result: diversity and volume are computed over origins. 30 ANTARA reposts = 1
origin. This is what makes "source diversity" meaningful.

---

## 4. Trending (DONE — see `packages/ranking/trending.py`)

The reference module is canonical. Summary of the corrected model:

```
raw_score = compressed_volume * (1 + DIVERSITY_COEF * diversity_bonus) * importance
            + BURST_COEF * burst_z
```
- `compressed_volume` = Σ over *origin sources* of `log1p(Σ decayed weighted
  mentions from that origin)`. Per-origin log compression is what stops one wire
  dump from dominating; recency decay is applied per mention (no double count).
- `diversity_bonus` = `log1p(distinct_origins)/log1p(SOURCE_CAP)`, bounded [0,1].
- `burst_z` = clamped Poisson residual `(obs − baseline)/sqrt(baseline+σ)`,
  additive — **never** an unbounded `current/prev` ratio. `obs` and `baseline`
  are **distinct-origin counts**, not carrier copies, so syndication can't
  manufacture a spike (consistent with how `compressed_volume` dampens per
  origin). The worker computes `baseline_mean` as the mean distinct-origin count
  over comparable prior windows.
- `importance` = entity_importance (actor, 1–2) / incident_weight (region) /
  1.0 (topic). Topics do **not** get an entity_importance term.
- Eligibility gate: a target must have ≥ `MIN_MENTIONS` and
  ≥ `MIN_DISTINCT_SOURCES` origins to trend at all (a single-origin story is not
  "trending" by definition).
- `normalized_score` = `raw/reference_scale*100`, clamped 0–100, where
  `reference_scale` is a rolling P95 — so `min_score` webhook thresholds are
  stable as corpus volume grows.

Invariants pinned by `test_trending.py`: independent coverage beats wire dumps,
diversity beats raw volume, cold-start can't reach #1, acceleration breaks ties,
recency wins, output is deterministic.

Actor/region/source scores reuse these primitives with their `importance`
source; implement them in `packages/ranking/{actor,region,source}.py` with the
same test discipline.

---

## 5. NLP enrichment

Pipeline per article: clean → detect language → normalize time → classify topic
→ NER → resolve actor aliases → extract regions → extract quotes → embed →
assign event. Hybrid, **not** LLM-per-article.

- **Gazetteer is the backbone, not NER.** Off-the-shelf IndoBERT NER yields
  PERSON/ORG/LOC and will not label MINISTRY/REGULATOR/SOE/COURT/LAW — exactly
  the high-value types. Ship a curated, version-controlled gazetteer of
  Indonesian government bodies, BUMN, parties, regulators, and their **acronyms**
  (`db/gazetteer/`). NER is the fallback for unknown names.
- **Actor alias resolution** handles gelar (`H.`, `Ir.`, `Dr.`, `S.H.`, `M.M.`)
  — strip for matching, keep for display — and acronym collisions (`PT`, party
  acronyms). Code-mixing (id/en/regional) is constant; normalize before match.
- **Quote extraction** must handle the majority case the spec misses:
  **continuation quotes** where the second quote's speaker is a pronoun (`Ia`,
  `Dia`, `Beliau`) resolving to the last named speaker, and split quotes
  (`"X," kata Y, "Z."`). High-precision rules first; confidence floor before a
  quote becomes `exposable`. Every quote carries `source_paragraph_url`.
- **Topic** classifier: rule-based keyword map + ML, manual override taxonomy.

Quality is measured against the NLP gold set in CI (per-extractor P/R).

---

## 6. Event clustering (entity+time first, embeddings second)

- **Block before compare.** Bucket candidate articles by shared canonical actor
  or by (region, day) so pairwise similarity is not O(n²).
- **Primary signal is entity+time overlap**, which is more robust and cheaper
  than embeddings for news. Two articles are the same event if they share ≥1
  canonical actor, are within a 48h window, and share topic/region; embedding
  cosine (multilingual-e5 / IndoBERT sentence encoder over `title+lede`, not
  feed boilerplate) is a tie-breaker, not the gate.
- **Stable IDs, incremental assignment.** A new article joins an existing event
  or opens a new one. **Never** batch re-partition and reassign IDs — that
  breaks webhooks, saved searches, and timelines. Merges/splits are explicit,
  logged operations exposed to the manual-review tools.
- Calibrate thresholds against a labeled event set; don't ship raw magic numbers.

---

## 7. Provenance, time, and "first reported"

- `published_at` is **claimed** (feeds backfill, overwrite, and lie). Never the
  basis of a factual primacy claim.
- `first_seen_by_us` is **trusted** (our monotonic clock). "First reported" in
  the API means "first observed by us" unless wire byline / sitemap lastmod
  corroboration raises `provenance_confidence`.
- Three Indonesian zones: store source-local zone (`published_tz`) + UTC.
  Compute all trend windows in UTC. A Papua (WIT) event is +2h vs Jakarta;
  hardcoding `Asia/Jakarta` misdates eastern-Indonesia stories and corrupts
  recency/burst.

---

## 8. API design notes

- Base path `/v1`. Endpoints per spec §32, plus the response envelope
  `{ "meta": {request_id, window, generated_at, limit, cursor}, "data": [] }`.
- **Cursor pagination** (`created_at`+`id`), not offset.
- Resolve `window` vs `from`/`to`: if `window` is present it derives `from/to`
  from `generated_at`; explicit `from/to` override `window`.
- Rate-limit headers (`X-RateLimit-*`, `Retry-After`); ETag/conditional GET on
  cacheable trending responses.
- Quote/actor endpoints run every row through the compliance layer before
  serialization (suppressed/non-exposable rows are dropped).

---

## 9. Infrastructure

- **v0.1**: Postgres (pgvector image) + Redis + API + worker. Full-text search
  via Postgres `tsvector` (Indonesian config); vectors via pgvector. **No
  OpenSearch.**
- Add OpenSearch only when search QPS/faceting outgrows Postgres (a later phase).
- Per-source circuit breakers + rate limits so one slow source can't stall the
  pool. Idempotent ingestion on `dedup_key`. Backpressure on large sitemap dumps.
- Adapter golden-file tests + extraction-yield drift alarms (sites change HTML
  constantly; adapters rot silently otherwise).

---

## 10. What "good" looks like

The system is correct when, on live data: independent multi-source stories
out-rank wire dumps; cold-start rumors don't top the board; "first observed"
is never presented as proven primacy; an acquitted person's suspect label
disappears; every served quote deep-links to its source paragraph; and no
endpoint ever returns a full article body. All of these are enforced by tests,
not by reviewer vigilance.
