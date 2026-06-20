# Indonesia News Intelligence API

**Project codename:** `news-intel-api`  
**Primary market:** Indonesia  
**Output:** API-first news intelligence system  
**Main sources:** Indonesian online media, official RSS feeds, public news pages, licensed feeds, and approved crawlers  
**Primary value:** Convert Indonesian news into structured intelligence: trending issues, topics, actors, regions, timeline, source comparison, and quotes.

---

## 1. Vision

This project is not just a normal news aggregator.

The goal is to build an **Indonesia News Intelligence API** that can answer:

> What is happening in Indonesia, who is involved, where it happened, when it happened, from which media sources, what the actors said, and how the narrative is trending over time.

Instead of only returning a list of articles, the API should expose structured news intelligence:

- Trending topics
- Trending actors
- Trending regions
- News events
- Article clusters
- Source comparison
- Actor mentions
- Quote extraction
- Topic timeline
- Regional heat map data
- API-ready structured metadata

---

## 2. Product Positioning

### Simple positioning

> An API that turns Indonesian online media into structured, searchable, near real-time intelligence.

### Stronger positioning

> Indonesia News Intelligence API for policy, economy, business, legal, regional, and public narrative monitoring.

### Why this is different from a normal aggregator

A normal news aggregator shows:

- Title
- Source
- Link
- Date
- Category

This system should show:

- What topic is trending
- Which actor is involved
- Which region is affected
- Which media first reported it
- Which sources confirm the issue
- What quote was said
- How the issue developed over time
- Whether the issue is growing, stable, or fading
- Which related topics, actors, and regions are connected

---

## 3. Recommended First Niche

Do not start with all news at once.

Start with one valuable vertical:

## Recommended MVP Focus

**Indonesia Policy + Economy News Intelligence API**

This niche is more valuable than generic news because the target users have clear business needs.

### Target users

- Financial analysts
- Corporate strategy teams
- Government affairs teams
- Public relations agencies
- Legal firms
- Energy companies
- Infrastructure companies
- Mining companies
- Investment teams
- Media monitoring teams
- Research institutions
- Political risk analysts

### Questions the API should answer

- What economic issue is trending today?
- Which minister or institution is mentioned most?
- Which province or city is becoming a news hotspot?
- What regulation is being discussed?
- What did the actor actually say?
- Which media first reported the issue?
- Which sources repeated or confirmed the issue?
- How did the narrative change over time?

---

## 4. Core Capabilities

The API should support these intelligence outputs.

### 4.1 News search

Search articles by:

- Keyword
- Topic
- Actor
- Region
- Source
- Date range
- Category
- Event cluster
- Quote speaker

Example:

```http
GET /v1/news?q=rupiah&from=2026-06-20T00:00:00+07:00&to=2026-06-20T23:59:59+07:00
```

---

### 4.2 Trending topics

Detect topics that are increasing in attention.

Examples:

- Rupiah
- APBN
- KPK
- IKN
- Subsidi BBM
- PPN
- Harga beras
- Pilkada
- Omnibus Law
- Freeport
- Timah
- Hilirisasi
- Banjir Jakarta

Endpoint:

```http
GET /v1/trending/topics?window=24h&limit=20
```

---

### 4.3 Trending actors

Detect people or organizations being mentioned.

Actor types:

- Person
- Government institution
- Company
- Political party
- NGO
- Court
- Regulator
- Ministry
- State-owned enterprise
- Law enforcement institution

Endpoint:

```http
GET /v1/trending/actors?window=24h&limit=20
```

---

### 4.4 Trending regions

Detect provinces, cities, and regencies that are trending.

Endpoint:

```http
GET /v1/trending/regions?window=24h&limit=20
```

---

### 4.5 Quote extraction

Extract statements from news articles.

Example quote patterns in Indonesian:

```txt
"...", kata X
"...", ujar X
"...", menurut X
"...", jelas X
"...", tegas X
"...", ungkap X
X mengatakan, "..."
X menegaskan bahwa "..."
X menyebutkan bahwa "..."
```

Endpoint:

```http
GET /v1/quotes?actor=Sri%20Mulyani&window=30d
```

---

### 4.6 Event clustering

Group multiple articles about the same issue into one event.

Example:

```txt
Article A: KPK periksa pejabat X soal kasus Y
Article B: Pejabat X diperiksa KPK selama 6 jam
Article C: KPK dalami aliran dana kasus Y
```

These should become one event:

```txt
Event: KPK memeriksa pejabat X terkait kasus Y
```

Endpoint:

```http
GET /v1/events/{event_id}
```

---

### 4.7 Source comparison

Compare how different media report the same event.

Possible output:

- First source
- Most active source
- Sources with unique angle
- Sources using direct quotes
- Sources using agency copy
- Source diversity score

Endpoint:

```http
GET /v1/events/{event_id}/sources
```

---

### 4.8 Timeline

Build a timeline of an issue.

Example:

```json
{
  "event_id": "evt_kpk_case_20260620",
  "timeline": [
    {
      "time": "2026-06-20T07:10:00+07:00",
      "summary": "First report appeared."
    },
    {
      "time": "2026-06-20T11:30:00+07:00",
      "summary": "KPK gave confirmation."
    },
    {
      "time": "2026-06-20T15:00:00+07:00",
      "summary": "Suspect's lawyer responded."
    }
  ]
}
```

Endpoint:

```http
GET /v1/events/{event_id}/timeline
```

---

## 5. High-Level Architecture

```txt
Media Sources
  ├─ RSS / official feeds
  ├─ Sitemap / category pages
  ├─ Licensed APIs / partnerships
  └─ Controlled crawlers, only when allowed

        ↓

Ingestion Workers
  ├─ Fetch feed/article metadata
  ├─ Deduplicate URL/title/content
  ├─ Extract article body snippet
  ├─ Normalize date/time/source/category
  └─ Store raw + normalized data

        ↓

NLP Enrichment
  ├─ Topic classification
  ├─ Named entity recognition
  ├─ Actor extraction
  ├─ Organization extraction
  ├─ Region mapping
  ├─ Quote extraction
  ├─ Actor alias resolution
  ├─ Sentiment / stance optional
  └─ Event clustering

        ↓

Ranking Engine
  ├─ Trending topic score
  ├─ Actor score
  ├─ Source diversity score
  ├─ Regional heat score
  ├─ Recency decay
  ├─ Growth rate
  └─ Burst detection

        ↓

API Layer
  ├─ Search
  ├─ Trending
  ├─ Topics
  ├─ Actors
  ├─ Regions
  ├─ Quotes
  ├─ Events
  ├─ Timeline
  └─ Source monitoring
```

---

## 6. Recommended Technology Stack

### Backend API

Recommended:

```txt
FastAPI + Python
```

Why:

- Good for API-first systems
- Easy integration with NLP models
- Good async support
- Easy OpenAPI documentation
- Good Python data ecosystem

Alternative:

```txt
Node.js + NestJS
```

Use Node.js only if the team is stronger in TypeScript.

---

### Worker system

MVP option:

```txt
APScheduler or cron + Python workers
```

Better production option:

```txt
Celery + Redis
```

Alternative:

```txt
RQ + Redis
```

Use Celery if many background jobs are expected.

---

### Database

Recommended:

```txt
PostgreSQL + pgvector
```

Use PostgreSQL for structured data and `pgvector` for embeddings.

---

### Search engine

Recommended:

```txt
OpenSearch
```

Alternative:

```txt
Elasticsearch
```

Use this for:

- Full-text search
- News search
- Faceted search
- Search by source/topic/actor/region
- Autocomplete
- Relevance scoring

---

### Cache

Recommended:

```txt
Redis
```

Use Redis for:

- Trending cache
- API response cache
- Rate limiting
- Job queues
- Temporary deduplication keys

---

### NLP

Recommended hybrid approach:

```txt
Rule-based extractor + Indonesian NLP model + LLM fallback
```

Use:

- Rule-based quote extractor
- Rule-based region dictionary
- IndoBERT-style NER models
- Embedding model for clustering
- LLM only for difficult enrichment or summary generation

Avoid using expensive LLMs for every article in the beginning.

---

### Deployment

MVP:

```txt
Docker Compose
```

Production:

```txt
Docker + Kubernetes
```

Or simpler production:

```txt
Docker Compose + VPS + managed PostgreSQL
```

---

## 7. Recommended Repository Structure

```txt
news-intel-api/
  README.md
  docker-compose.yml
  .env.example
  pyproject.toml

  apps/
    api/
      main.py
      routes/
        news.py
        trending.py
        topics.py
        actors.py
        regions.py
        quotes.py
        events.py
        sources.py
      dependencies.py
      middleware.py

    worker/
      main.py
      scheduler.py
      jobs/
        fetch_feeds.py
        fetch_articles.py
        enrich_articles.py
        cluster_events.py
        calculate_trends.py
        cleanup.py

  packages/
    source_adapters/
      base.py
      antara.py
      kompas.py
      detik.py
      cnn_indonesia.py
      cnbc_indonesia.py
      liputan6.py
      republika.py
      tempo.py
      katadata.py
      bisnis.py

    nlp/
      cleaner.py
      language.py
      topic_classifier.py
      ner.py
      actor_resolver.py
      region_extractor.py
      quote_extractor.py
      summarizer.py
      embedding.py

    ranking/
      trending.py
      burst.py
      source_diversity.py
      event_score.py

    clustering/
      event_clusterer.py
      similarity.py

    schemas/
      article.py
      source.py
      entity.py
      quote.py
      topic.py
      region.py
      event.py
      trend.py

    db/
      session.py
      models.py
      migrations/

    utils/
      time.py
      hashing.py
      text.py
      logging.py
```

---

## 8. Source Strategy

### 8.1 Use official feeds first

Start with sources that provide stable feeds or predictable public pages.

Recommended first source list:

```txt
ANTARA
Kompas
detik
CNN Indonesia
CNBC Indonesia
Liputan6
Republika
Tempo
Katadata
Bisnis
Tirto
Kumparan
Suara
Tribun Network
Kontan
Investor Daily
```

### 8.2 Source priority

Use a source tier system.

```txt
Tier 1:
Official RSS feeds, official APIs, licensed feeds

Tier 2:
Public category pages and sitemaps, only if allowed

Tier 3:
Controlled crawler with legal review and robots.txt check

Tier 4:
Partnership or paid data licensing
```

### 8.3 Important legal rule

Do not build a full-article republishing system.

The API should store and return:

- Headline
- Source
- URL
- Timestamp
- Short excerpt
- Generated summary if legally safe
- Entities
- Topics
- Regions
- Quotes
- Analytics metadata

Avoid returning full article body unless the project has permission or licensing.

---

## 9. Source Adapter Design

Each source should have an adapter.

Example interface:

```python
class SourceAdapter:
    source_name: str
    source_domain: str

    def fetch_feed_items(self) -> list[dict]:
        pass

    def normalize_item(self, item: dict) -> dict:
        pass

    def fetch_article_detail(self, url: str) -> dict:
        pass
```

Example normalized article object:

```json
{
  "source": "Antara",
  "source_domain": "antaranews.com",
  "title": "Pemerintah siapkan kebijakan baru",
  "url": "https://www.antaranews.com/...",
  "published_at": "2026-06-20T08:30:00+07:00",
  "raw_category": "ekonomi",
  "summary": "Short excerpt from feed or extracted page.",
  "content_hash": "sha256..."
}
```

---

## 10. Data Model

## 10.1 `sources`

```sql
CREATE TABLE sources (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,
  credibility_tier INTEGER DEFAULT 2,
  active BOOLEAN DEFAULT TRUE,
  fetch_interval_seconds INTEGER DEFAULT 300,
  robots_status TEXT,
  terms_notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10.2 `feeds`

```sql
CREATE TABLE feeds (
  id UUID PRIMARY KEY,
  source_id UUID REFERENCES sources(id),
  url TEXT NOT NULL,
  category TEXT,
  region TEXT,
  active BOOLEAN DEFAULT TRUE,
  last_fetched_at TIMESTAMPTZ,
  last_status_code INTEGER,
  error_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10.3 `articles`

```sql
CREATE TABLE articles (
  id UUID PRIMARY KEY,
  source_id UUID REFERENCES sources(id),
  url TEXT NOT NULL UNIQUE,
  canonical_url TEXT,
  title TEXT NOT NULL,
  summary TEXT,
  excerpt TEXT,
  content_hash TEXT,
  published_at TIMESTAMPTZ,
  collected_at TIMESTAMPTZ DEFAULT NOW(),
  language TEXT DEFAULT 'id',
  raw_category TEXT,
  event_id UUID,
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10.4 `entities`

```sql
CREATE TABLE entities (
  id UUID PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  aliases_json JSONB DEFAULT '[]',
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Entity types:

```txt
person
organization
institution
company
political_party
location
product
law
court
regulator
ministry
state_owned_enterprise
```

---

## 10.5 `article_entities`

```sql
CREATE TABLE article_entities (
  article_id UUID REFERENCES articles(id),
  entity_id UUID REFERENCES entities(id),
  role TEXT DEFAULT 'mentioned',
  confidence FLOAT DEFAULT 0,
  mention_count INTEGER DEFAULT 1,
  PRIMARY KEY (article_id, entity_id, role)
);
```

Roles:

```txt
mentioned
speaker
subject
accused
victim
institution
company
regulator
```

---

## 10.6 `regions`

```sql
CREATE TABLE regions (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  region_type TEXT NOT NULL,
  parent_id UUID REFERENCES regions(id),
  aliases_json JSONB DEFAULT '[]',
  iso_code TEXT,
  bps_code TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Region types:

```txt
country
province
city
regency
district
```

---

## 10.7 `article_regions`

```sql
CREATE TABLE article_regions (
  article_id UUID REFERENCES articles(id),
  region_id UUID REFERENCES regions(id),
  confidence FLOAT DEFAULT 0,
  PRIMARY KEY (article_id, region_id)
);
```

---

## 10.8 `topics`

```sql
CREATE TABLE topics (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  parent_topic_id UUID REFERENCES topics(id),
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Example topic taxonomy:

```txt
politik
ekonomi
hukum
korupsi
energi
tambang
infrastruktur
kesehatan
pendidikan
teknologi
transportasi
bencana
keamanan
internasional
olahraga
hiburan
pasar_modal
moneter
fiskal
pajak
perbankan
komoditas
```

---

## 10.9 `article_topics`

```sql
CREATE TABLE article_topics (
  article_id UUID REFERENCES articles(id),
  topic_id UUID REFERENCES topics(id),
  confidence FLOAT DEFAULT 0,
  PRIMARY KEY (article_id, topic_id)
);
```

---

## 10.10 `quotes`

```sql
CREATE TABLE quotes (
  id UUID PRIMARY KEY,
  article_id UUID REFERENCES articles(id),
  speaker_entity_id UUID REFERENCES entities(id),
  quote_text TEXT NOT NULL,
  context_text TEXT,
  confidence FLOAT DEFAULT 0,
  extracted_method TEXT,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 10.11 `events`

```sql
CREATE TABLE events (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  summary TEXT,
  first_seen TIMESTAMPTZ,
  last_seen TIMESTAMPTZ,
  article_count INTEGER DEFAULT 0,
  source_count INTEGER DEFAULT 0,
  main_topic_id UUID REFERENCES topics(id),
  status TEXT DEFAULT 'active',
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

Event status:

```txt
active
cooling
archived
merged
```

---

## 10.12 `trend_snapshots`

```sql
CREATE TABLE trend_snapshots (
  id UUID PRIMARY KEY,
  window TEXT NOT NULL,
  trend_type TEXT NOT NULL,
  target_id UUID,
  target_name TEXT,
  score FLOAT NOT NULL,
  mentions INTEGER DEFAULT 0,
  source_count INTEGER DEFAULT 0,
  growth_rate FLOAT DEFAULT 0,
  calculated_at TIMESTAMPTZ DEFAULT NOW()
);
```

Trend types:

```txt
topic
actor
region
quote
event
source
```

---

## 11. API Design

Base path:

```txt
/v1
```

---

## 11.1 Health check

```http
GET /v1/health
```

Response:

```json
{
  "status": "ok",
  "service": "news-intel-api",
  "version": "0.1.0"
}
```

---

## 11.2 List sources

```http
GET /v1/sources
```

Response:

```json
{
  "items": [
    {
      "id": "src_antara",
      "name": "ANTARA",
      "domain": "antaranews.com",
      "active": true,
      "last_fetched_at": "2026-06-20T08:30:00+07:00",
      "error_count": 0
    }
  ]
}
```

---

## 11.3 Source status

```http
GET /v1/sources/status
```

Response:

```json
{
  "total_sources": 10,
  "active_sources": 9,
  "sources_with_error": 1,
  "items": [
    {
      "source": "Antara",
      "status": "ok",
      "last_fetch": "2026-06-20T08:30:00+07:00",
      "last_status_code": 200,
      "items_collected_24h": 320
    }
  ]
}
```

---

## 11.4 Search news

```http
GET /v1/news
```

Query parameters:

```txt
q
topic
actor
region
source
from
to
event_id
limit
offset
sort
```

Example:

```http
GET /v1/news?q=rupiah&topic=ekonomi&window=24h&limit=20
```

Response:

```json
{
  "query": "rupiah",
  "total": 245,
  "items": [
    {
      "id": "art_01J...",
      "title": "Rupiah melemah terhadap dolar AS",
      "source": "CNBC Indonesia",
      "published_at": "2026-06-20T10:15:00+07:00",
      "url": "https://...",
      "excerpt": "Short excerpt only.",
      "topics": ["ekonomi", "market"],
      "actors": ["Bank Indonesia"],
      "regions": ["Indonesia"],
      "event_id": "evt_01J..."
    }
  ]
}
```

---

## 11.5 Get article detail

```http
GET /v1/news/{article_id}
```

Response:

```json
{
  "id": "art_01J...",
  "title": "Rupiah melemah terhadap dolar AS",
  "source": "CNBC Indonesia",
  "published_at": "2026-06-20T10:15:00+07:00",
  "url": "https://...",
  "excerpt": "Short excerpt only.",
  "summary": "Generated or feed-based short summary.",
  "topics": [
    {
      "name": "ekonomi",
      "confidence": 0.91
    }
  ],
  "actors": [
    {
      "name": "Bank Indonesia",
      "type": "institution",
      "confidence": 0.88
    }
  ],
  "regions": [
    {
      "name": "Indonesia",
      "type": "country",
      "confidence": 0.92
    }
  ],
  "quotes": []
}
```

---

## 11.6 Trending

```http
GET /v1/trending
```

Query parameters:

```txt
type = topic | actor | region | quote | event | source
window = 1h | 3h | 6h | 12h | 24h | 7d | 30d
limit
```

Example:

```http
GET /v1/trending?type=topic&window=24h&limit=20
```

Response:

```json
{
  "window": "24h",
  "type": "topic",
  "items": [
    {
      "name": "rupiah",
      "score": 91.4,
      "mentions": 182,
      "sources": 14,
      "growth_rate": 2.8,
      "top_sources": ["CNBC Indonesia", "Kompas", "Antara"],
      "related_actors": ["Bank Indonesia", "Menteri Keuangan"],
      "related_regions": ["Indonesia"]
    }
  ]
}
```

---

## 11.7 Topics

```http
GET /v1/topics
```

```http
GET /v1/topics/{topic_name}
```

Example response:

```json
{
  "topic": "ekonomi",
  "mentions_24h": 1230,
  "top_subtopics": ["rupiah", "inflasi", "APBN", "pajak"],
  "top_actors": ["Bank Indonesia", "Menteri Keuangan"],
  "top_regions": ["Indonesia", "DKI Jakarta"],
  "top_events": []
}
```

---

## 11.8 Actors

```http
GET /v1/actors
```

```http
GET /v1/actors/{actor_name}
```

Example:

```http
GET /v1/actors/Sri%20Mulyani?window=7d
```

Response:

```json
{
  "actor": "Sri Mulyani",
  "type": "person",
  "mentions": 340,
  "top_topics": ["APBN", "pajak", "rupiah"],
  "top_quotes": [
    {
      "text": "Kita akan menjaga defisit tetap terkendali.",
      "source": "Antara",
      "published_at": "2026-06-20T09:30:00+07:00"
    }
  ],
  "timeline": []
}
```

---

## 11.9 Regions

```http
GET /v1/regions
```

```http
GET /v1/regions/{region_name}/trending?window=24h
```

Response:

```json
{
  "region": "Jawa Barat",
  "top_topics": [
    {
      "topic": "transportasi",
      "mentions": 45
    },
    {
      "topic": "banjir",
      "mentions": 21
    }
  ],
  "top_events": []
}
```

---

## 11.10 Quotes

```http
GET /v1/quotes
```

Query parameters:

```txt
actor
topic
region
source
from
to
window
limit
```

Example:

```http
GET /v1/quotes?actor=Presiden&topic=ekonomi&window=30d
```

Response:

```json
{
  "items": [
    {
      "speaker": "Presiden",
      "quote": "Investasi harus dipercepat.",
      "source": "Kompas",
      "article_title": "Original article title",
      "article_url": "https://...",
      "published_at": "2026-06-18T14:00:00+07:00",
      "confidence": 0.79
    }
  ]
}
```

---

## 11.11 Events

```http
GET /v1/events
```

```http
GET /v1/events/{event_id}
```

Response:

```json
{
  "event_id": "evt_kpk_kasus_y_20260620",
  "title": "KPK memeriksa pejabat X terkait kasus Y",
  "summary": "Several media reported that KPK examined official X in relation to case Y.",
  "first_seen": "2026-06-20T07:10:00+07:00",
  "last_seen": "2026-06-20T13:40:00+07:00",
  "article_count": 18,
  "source_count": 9,
  "topics": ["hukum", "korupsi"],
  "actors": ["KPK", "Pejabat X"],
  "regions": ["Jakarta"],
  "timeline": [
    {
      "time": "07:10",
      "summary": "Media pertama melaporkan pemeriksaan."
    },
    {
      "time": "11:30",
      "summary": "KPK memberi konfirmasi."
    }
  ],
  "articles": []
}
```

---

## 12. Trending Algorithm

Do not rank trending only by count.

Use a composite score.

```txt
trend_score =
  mention_count
  × source_diversity_weight
  × recency_decay
  × growth_rate
  × entity_importance
  × event_cluster_strength
```

### 12.1 Mention count

How many articles mention the topic, actor, or region.

```txt
mention_count = total mentions in selected time window
```

---

### 12.2 Source diversity

Higher score if many different media cover the same issue.

```txt
source_diversity_weight = log(1 + unique_sources)
```

Reason:

- 20 articles from one media group should not dominate.
- 10 articles from 10 different sources is more important.

---

### 12.3 Recency decay

More recent articles should get higher weight.

Example:

```txt
recency_decay = exp(-age_hours / half_life_hours)
```

Suggested half-life:

```txt
1h trend: half_life = 1
6h trend: half_life = 3
24h trend: half_life = 8
7d trend: half_life = 48
```

---

### 12.4 Growth rate

Detect acceleration.

```txt
growth_rate = current_window_mentions / max(previous_window_mentions, 1)
```

Example:

```txt
Mentions last 6h: 60
Mentions previous 6h: 20
Growth rate: 3.0
```

---

### 12.5 Entity importance

Some actors are more important.

Example:

```txt
President
Vice President
Ministers
Bank Indonesia
OJK
KPK
Supreme Court
DPR
Major companies
Major political parties
Governors
```

Use an `entity_importance` score from 1.0 to 2.0.

---

### 12.6 Event cluster strength

If many articles are part of one event cluster, increase the score.

```txt
event_cluster_strength =
  log(1 + article_count_in_cluster) × log(1 + source_count_in_cluster)
```

---

## 13. Event Clustering Logic

### 13.1 Input features

Use these fields:

```txt
title
summary
topics
actors
regions
source category
published_at
embedding(title + summary)
```

### 13.2 Similarity criteria

Two articles are likely same event if:

```txt
semantic_similarity > 0.82
AND time_distance < 48 hours
AND shared_actor_count >= 1
```

Or:

```txt
semantic_similarity > 0.88
AND same_topic
AND same_region
```

### 13.3 Event merge rules

Merge article into existing event if:

```txt
- Similar title/summary
- Same main actor or institution
- Same region
- Same time window
- Same topic
```

Do not merge if:

```txt
- Same actor but different issue
- Same topic but unrelated event
- Different region and different incident
- Similar generic headline only
```

Example:

```txt
Do merge:
"KPK periksa pejabat X soal kasus Y"
"Pejabat X diperiksa KPK selama 6 jam"

Do not merge:
"KPK periksa pejabat X soal kasus Y"
"KPK periksa pejabat Z dalam kasus berbeda"
```

---

## 14. NLP Enrichment Pipeline

Each article should pass through this pipeline:

```txt
1. Clean text
2. Detect language
3. Normalize timestamp
4. Classify topic
5. Extract named entities
6. Resolve actor aliases
7. Extract regions
8. Extract quotes
9. Generate embedding
10. Assign event cluster
11. Store enriched result
```

---

## 14.1 Text cleaning

Remove:

```txt
- HTML tags
- Share button text
- Related article blocks
- Advertisement labels
- Newsletter blocks
- Author footer
- Repeated source boilerplate
```

Normalize:

```txt
- Unicode quotes
- Extra whitespace
- Date/time format
- Common abbreviations
```

---

## 14.2 Topic classifier

Start with a hybrid classifier:

```txt
Rule-based keyword classifier
+
ML classifier
+
Manual override taxonomy
```

Example keyword mapping:

```json
{
  "ekonomi": ["rupiah", "inflasi", "APBN", "pajak", "subsidi", "BI", "OJK"],
  "hukum": ["KPK", "tersangka", "pengadilan", "hakim", "kejaksaan", "polisi"],
  "politik": ["DPR", "partai", "presiden", "menteri", "pilkada", "pemilu"],
  "energi": ["PLN", "ESDM", "tambang", "minyak", "gas", "batubara", "solar"],
  "infrastruktur": ["jalan tol", "kereta", "pelabuhan", "bandara", "IKN"]
}
```

---

## 14.3 Named entity recognition

Entity types needed:

```txt
PERSON
ORGANIZATION
GOVERNMENT_INSTITUTION
COMPANY
POLITICAL_PARTY
LOCATION
LAW
COURT
REGULATOR
MINISTRY
STATE_OWNED_ENTERPRISE
```

---

## 14.4 Actor alias resolution

Indonesian media often use aliases.

Examples:

```txt
Sri Mulyani Indrawati
Sri Mulyani
Menkeu
Menteri Keuangan

Prabowo Subianto
Prabowo
Presiden
Presiden Prabowo

Bank Indonesia
BI
Gubernur BI

Komisi Pemberantasan Korupsi
KPK
```

Create alias table:

```json
{
  "canonical_name": "Sri Mulyani Indrawati",
  "aliases": ["Sri Mulyani", "Menkeu", "Menteri Keuangan"],
  "type": "person"
}
```

---

## 14.5 Region extraction

Use a region gazetteer.

Minimum region data:

```txt
Indonesia
34+ provinces
cities
regencies
major districts
capital aliases
local spellings
```

Examples:

```txt
DKI Jakarta
Jakarta
Jabodetabek
Kota Bandung
Bandung
Kabupaten Bekasi
Bekasi
Jawa Barat
Jabar
Jawa Timur
Jatim
Jawa Tengah
Jateng
Sulawesi Selatan
Sulsel
```

Use confidence scoring:

```txt
High confidence:
- Location appears in title
- Location appears with incident word
- Location appears multiple times
- Location appears in article category or source regional feed

Low confidence:
- Location appears only as organization name
- Location appears in unrelated boilerplate
```

---

## 14.6 Quote extraction

Use high-precision rules first.

Patterns:

```txt
"QUOTE", kata SPEAKER
"QUOTE", ujar SPEAKER
"QUOTE", jelas SPEAKER
"QUOTE", tegas SPEAKER
"QUOTE", ungkap SPEAKER
"QUOTE", menurut SPEAKER
SPEAKER mengatakan, "QUOTE"
SPEAKER menyebut, "QUOTE"
SPEAKER menegaskan, "QUOTE"
SPEAKER menjelaskan, "QUOTE"
```

Quote object:

```json
{
  "quote_text": "Kami akan menjaga inflasi tetap terkendali.",
  "speaker": "Sri Mulyani",
  "speaker_confidence": 0.84,
  "context": "Dalam konferensi pers APBN...",
  "article_id": "art_01J..."
}
```

Confidence rules:

```txt
0.90+:
- Direct quote with clear speaker nearby

0.75–0.89:
- Direct quote with nearby role/title

0.50–0.74:
- Indirect quote or unclear speaker

Below 0.50:
- Do not expose by default
```

---

## 15. Ranking and Intelligence Scores

## 15.1 Actor score

```txt
actor_score =
  mention_count
  × source_diversity
  × recency_decay
  × role_weight
  × quote_weight
```

Role weight:

```txt
speaker: 1.5
subject: 1.3
mentioned: 1.0
```

Quote weight:

```txt
has_direct_quote: 1.2
no_quote: 1.0
```

---

## 15.2 Region score

```txt
region_score =
  mention_count
  × source_diversity
  × recency_decay
  × incident_weight
```

Incident weight:

```txt
disaster/security/legal issue: higher
generic mention: lower
```

---

## 15.3 Source score

Track source performance:

```txt
- Articles collected
- First reports
- Unique events reported
- Quote-rich articles
- Error rate
- Duplicate rate
```

---

## 16. API Response Design Principles

All API responses should be:

```txt
- JSON-first
- Consistent
- Timestamped
- Source-attributed
- Pagination-ready
- Filterable
- Safe for commercial use
```

General response format:

```json
{
  "meta": {
    "request_id": "req_01J...",
    "window": "24h",
    "generated_at": "2026-06-20T10:00:00+07:00",
    "limit": 20,
    "offset": 0
  },
  "data": []
}
```

Error format:

```json
{
  "error": {
    "code": "invalid_parameter",
    "message": "window must be one of: 1h, 3h, 6h, 12h, 24h, 7d, 30d",
    "request_id": "req_01J..."
  }
}
```

---

## 17. Authentication and Rate Limiting

Use API keys.

Header:

```http
Authorization: Bearer YOUR_API_KEY
```

Rate limit tiers:

```txt
Free:
1,000 requests/month
Limited source coverage
Delayed data

Developer:
50,000 requests/month
Near real-time data
Basic trending

Business:
500,000 requests/month
Full source coverage
Webhooks
Saved queries

Enterprise:
Custom quota
Custom sources
SLA
Dedicated deployment
```

Rate limit response:

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Monthly quota exceeded."
  }
}
```

---

## 18. Webhook Alerts

Add this after MVP.

Use cases:

```txt
- Alert when actor appears in news
- Alert when topic becomes trending
- Alert when region has sudden spike
- Alert when a source publishes new article about keyword
- Alert when quote from specific actor appears
```

Endpoint:

```http
POST /v1/webhooks
```

Payload:

```json
{
  "name": "BI Rupiah Monitor",
  "target_url": "https://client.com/webhook/news",
  "rules": {
    "topics": ["rupiah", "Bank Indonesia"],
    "actors": ["Bank Indonesia"],
    "window": "1h",
    "min_score": 50
  }
}
```

---

## 19. MVP Roadmap

## Version 0.1 — News Collector API

Goal:

```txt
Collect and normalize news from 5–10 Indonesian media sources.
```

Features:

```txt
- Source registry
- Feed ingestion
- Article normalization
- Deduplication
- PostgreSQL storage
- /news endpoint
- /sources endpoint
- /sources/status endpoint
```

Do not build complex NLP yet.

---

## Version 0.2 — Intelligence Layer

Goal:

```txt
Extract topics, actors, regions, and quotes.
```

Features:

```txt
- Topic classifier
- Actor extractor
- Region extractor
- Quote extractor
- Entity alias table
- /topics endpoint
- /actors endpoint
- /regions endpoint
- /quotes endpoint
```

---

## Version 0.3 — Trending Engine

Goal:

```txt
Detect what is trending across Indonesian media.
```

Features:

```txt
- Mention counts
- Growth rate
- Source diversity
- Recency decay
- Trend snapshots
- /trending endpoint
```

---

## Version 0.4 — Event Clustering

Goal:

```txt
Group related articles into events.
```

Features:

```txt
- Article embeddings
- Similarity clustering
- Event table
- Event timeline
- Source comparison
- /events endpoint
```

---

## Version 0.5 — Commercial API

Goal:

```txt
Make the product usable by external users.
```

Features:

```txt
- API keys
- Rate limiting
- Usage dashboard
- Saved queries
- Webhook alerts
- Billing-ready quota structure
- Admin dashboard
```

---

## 20. First Development Sprint

### Sprint 1 goal

Build a working API that collects news from a few sources and returns normalized JSON.

### Tasks

```txt
1. Create FastAPI project
2. Create PostgreSQL schema
3. Create source registry
4. Build RSS feed parser
5. Add 3 source adapters
6. Store articles
7. Add deduplication
8. Add /v1/news
9. Add /v1/sources/status
10. Add Docker Compose
```

### Definition of done

```txt
- API runs locally
- Worker fetches source feeds
- Articles are stored in PostgreSQL
- Duplicate articles are skipped
- /v1/news returns articles
- /v1/sources/status shows source health
```

---

## 21. Docker Compose MVP

Recommended services:

```yaml
services:
  api:
    build: .
    command: uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - postgres
      - redis

  worker:
    build: .
    command: python apps/worker/main.py
    env_file:
      - .env
    depends_on:
      - postgres
      - redis

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: news
      POSTGRES_PASSWORD: news
      POSTGRES_DB: news_intel
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  opensearch:
    image: opensearchproject/opensearch:2
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
      - OPENSEARCH_INITIAL_ADMIN_PASSWORD=admin123!
    ports:
      - "9200:9200"

volumes:
  postgres_data:
```

---

## 22. Environment Variables

`.env.example`

```env
APP_ENV=local
APP_NAME=news-intel-api
API_HOST=0.0.0.0
API_PORT=8000

DATABASE_URL=postgresql+psycopg://news:news@postgres:5432/news_intel
REDIS_URL=redis://redis:6379/0
OPENSEARCH_URL=http://opensearch:9200

DEFAULT_TIMEZONE=Asia/Jakarta
FETCH_INTERVAL_SECONDS=300

ENABLE_LLM_ENRICHMENT=false
OPENAI_API_KEY=

API_KEY_SECRET=change_this_secret
```

---

## 23. Source Fetching Best Practices

Rules:

```txt
- Prefer official RSS/API feeds
- Respect robots.txt
- Respect publisher terms
- Use polite request intervals
- Use descriptive User-Agent
- Cache aggressively
- Store canonical URL
- Do not overload websites
- Do not republish full articles
- Link back to original source
```

Example User-Agent:

```txt
NewsIntelBot/0.1 (+https://yourdomain.com/bot-info; contact: you@yourdomain.com)
```

---

## 24. Deduplication Strategy

Use multiple dedupe layers.

### URL dedupe

```txt
canonical_url unique
```

### Title hash

```txt
normalized_title_hash
```

### Content hash

```txt
sha256(clean_title + source + published_date)
```

### Similarity dedupe

Use embeddings later.

```txt
If similarity > 0.95 and same source and same date, mark duplicate.
```

---

## 25. Time Handling

Use timezone:

```txt
Asia/Jakarta
```

Store in database as:

```txt
TIMESTAMPTZ
```

API should accept:

```txt
ISO 8601 datetime
```

Example:

```txt
2026-06-20T10:00:00+07:00
```

Supported windows:

```txt
1h
3h
6h
12h
24h
7d
30d
```

---

## 26. Admin Dashboard Later

This project is API-first, but an admin dashboard is useful.

Admin features:

```txt
- Source health
- Fetch errors
- Articles per source
- Duplicate rate
- Trending preview
- Entity extraction review
- Quote extraction review
- Event merge/split tool
- API usage dashboard
```

---

## 27. Quality Control

Track these metrics:

```txt
Ingestion:
- Fetch success rate
- Fetch latency
- Articles collected per source
- Duplicate rate
- Error rate

NLP:
- Topic confidence
- Entity confidence
- Region confidence
- Quote confidence
- Unknown actor rate

Trending:
- Trend stability
- False trend rate
- Source diversity
- Growth accuracy

API:
- Latency
- Request count
- Error count
- Cache hit rate
```

---

## 28. Manual Review Tools

Important for accuracy.

Build review tools for:

```txt
- Merge duplicate actors
- Add aliases
- Correct topic classification
- Correct region detection
- Approve/reject quotes
- Merge/split events
- Blacklist bad feed items
```

Example actor merge:

```txt
"Sri Mulyani"
"Menkeu Sri Mulyani"
"Sri Mulyani Indrawati"
→ canonical: Sri Mulyani Indrawati
```

---

## 29. Legal and Compliance Guardrails

Important principle:

> This system should be a structured metadata and intelligence layer, not a full article republication engine.

Recommended safe API fields:

```txt
- Title
- Source name
- Original URL
- Published date
- Short excerpt
- Short generated summary
- Topics
- Actors
- Regions
- Quotes with attribution
- Event metadata
- Trend score
```

Avoid by default:

```txt
- Full article body
- Large copied article excerpts
- Paywalled content
- Bypassing access controls
- Republishing media images without rights
- Ignoring robots.txt or source terms
```

Commercial version should consider:

```txt
- Publisher partnerships
- Licensed feeds
- Legal review
- Clear takedown policy
- Attribution policy
- Bot information page
```

---

## 30. Suggested API Product Tiers

### Free tier

```txt
- Delayed data
- Limited sources
- Basic search
- 1,000 requests/month
```

### Developer tier

```txt
- Near real-time data
- Basic trending
- 50,000 requests/month
```

### Business tier

```txt
- Full source coverage
- Webhooks
- Actor monitoring
- Region monitoring
- 500,000 requests/month
```

### Enterprise tier

```txt
- Custom sources
- Custom taxonomy
- Dedicated deployment
- SLA
- Private data integration
```

---

## 31. Example Customer Use Cases

### 31.1 PR agency

Use API to monitor:

```txt
- Brand mention
- CEO mention
- Competitor mention
- Negative news spike
- Media source spread
```

### 31.2 Financial analyst

Use API to monitor:

```txt
- Rupiah news
- Bank Indonesia statements
- OJK regulations
- Fiscal policy
- Commodity policy
- Public company news
```

### 31.3 Legal firm

Use API to monitor:

```txt
- Court decisions
- KPK cases
- Regulation changes
- Ministry statements
- Legal controversy
```

### 31.4 Energy company

Use API to monitor:

```txt
- ESDM policy
- PLN news
- Mining regulation
- Coal price narrative
- Renewable energy projects
- Regional project risk
```

### 31.5 Government affairs team

Use API to monitor:

```txt
- Minister statements
- DPR agenda
- Public controversy
- Regional political issues
- Policy narrative
```

---

## 32. Recommended MVP Endpoint List

Build these first:

```txt
GET /v1/health
GET /v1/sources
GET /v1/sources/status
GET /v1/news
GET /v1/news/{article_id}
GET /v1/trending
GET /v1/topics
GET /v1/actors
GET /v1/regions
GET /v1/quotes
GET /v1/events
GET /v1/events/{event_id}
```

---

## 33. Later Advanced Features

After the core system works:

```txt
- Webhook alerts
- Saved searches
- Alert rules
- Media bias/source angle comparison
- Topic narrative graph
- Actor relationship graph
- Region heat map API
- Daily intelligence digest
- Email/Telegram/Slack alert
- Customer dashboard
- Export to CSV/JSON
- LLM-generated briefings
- Custom source ingestion
- Private document + public news comparison
```

---

## 34. Build Order Recommendation

Recommended order:

```txt
1. Database schema
2. Source registry
3. RSS ingestion
4. Article normalization
5. Deduplication
6. News API
7. Source status API
8. Topic classifier
9. Actor extractor
10. Region extractor
11. Quote extractor
12. Trending score
13. Event clustering
14. API keys and rate limits
15. Webhooks
16. Admin dashboard
```

Do not start with LLM or dashboard.

Start with reliable data ingestion and clean normalized storage.

---

## 35. Key Engineering Principles

```txt
- API-first
- Source-attributed
- Metadata-focused
- Legally conservative
- Modular source adapters
- Hybrid NLP, not LLM-only
- Confidence scoring everywhere
- Manual review support
- Full observability
- Deduplication before intelligence
- Source diversity matters more than raw count
```

---

## 36. Success Criteria

The project is successful when the API can answer these reliably:

```txt
What is trending in Indonesian news today?
Which actors are being mentioned?
Which regions are heating up?
Which issue is growing fastest?
Which media first reported the event?
What direct quotes were made?
Which topics are related?
How did the event timeline develop?
```

---

## 37. Final Product Statement

**Indonesia News Intelligence API** is an API-first platform that collects Indonesian online news, normalizes it, extracts entities and quotes, clusters related articles into events, calculates trends, and exposes structured intelligence through developer-friendly JSON endpoints.

The first version should focus on **policy, economy, business, legal, and regional risk intelligence** rather than generic news aggregation.

The long-term value is not the article list.

The long-term value is:

```txt
- Actor intelligence
- Topic intelligence
- Region intelligence
- Quote intelligence
- Event intelligence
- Source intelligence
- Trend intelligence
```

This makes the system useful for companies, analysts, PR teams, legal teams, government affairs teams, and media monitoring businesses.
