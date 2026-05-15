# Yatagarasu Competitive Landscape & Architecture Research

Research conducted 2026-04-06. Systems similar to Yatagarasu: personal signal curation tools that fetch from multiple sources, score relevance via LLM, and output daily digests.

---

## 1. OPEN-SOURCE PERSONAL INTELLIGENCE TOOLS

### Tier 1: Directly Comparable

**auto-news** (github.com/finaldie/auto-news) -- ~1.5k stars
- Closest analog to Yatagarasu. Multi-source aggregator (RSS, Tweets, YouTube, Reddit, Web Articles, personal journal notes) + LLM filtering.
- Stack: Python, Apache Airflow DAGs, LangChain, Notion as frontend. Supports ChatGPT/Gemini/Ollama.
- Claims 80%+ noise filtering via LLM. Weekly top-k recaps. Experimental multi-agent deep-dives.
- Heavier infrastructure: minimum 2 CPU / 6GB RAM / 20GB disk. Kubernetes + Helm + ArgoCD support.
- Has a managed SaaS version (Dots Agent) on iOS/Android.
- WEAKNESS: No documented dedup strategy. No scoring system (binary filter, not scored tiers). No feed health monitoring.
- LEARN FROM: Multi-source breadth (YouTube transcripts, Reddit). Journal note ingestion for personal context. Airflow DAGs for pipeline orchestration.

**feeds.fun** (github.com/Tiendil/feeds.fun) -- HN Show HN featured
- RSS reader with LLM-based auto-tagging + user-defined scoring rules.
- Stack: FastAPI, PostgreSQL (Yoyo migrations), separate loader/librarian workers.
- Tag processing pipeline: raw tags -> normalization chain (blacklist, replacer, splitter) -> scoring rules.
- User defines rules like "books + sci-fi -> +5 score" -- composable boolean scoring.
- Supports OpenAI and Gemini. Uses TikToken for token estimation.
- Reports filtering ~80% of 1000+ daily items.
- WEAKNESS: RSS-only (no arxiv, no web search, no HN API). No temporal decay. No embedding-based similarity.
- LEARN FROM: Tag normalization pipeline is excellent. Composable user-defined scoring rules. Separation of loader/librarian workers. PostgreSQL with versioned migrations. Periodic cleaner cron for old entries.

**Precis** (github.com/leozqin/precis)
- Self-hosted AI-enabled RSS reader. FastAPI monolith.
- Extensible handler pattern: swappable LLM backends (Ollama, OpenAI, null), storage (TinyDB, LMDB, hybrid), notifications (Matrix, Slack, Jira, ntfy), content retrieval (requests vs Playwright).
- LEARN FROM: Handler-based extensibility model is clean. Notification system with 4 backends. Hybrid storage (LMDB + filesystem for large content).

**RLLM** (github.com/DanielZhangyc/RLLM)
- iOS-native RSS + LLM reader (Swift/SwiftUI). Multi-provider (Anthropic, DeepSeek, OpenAI).
- Daily Reading AI Summary aggregates across all articles.
- "AI Article Insight Analysis" -- structured extraction beyond summarization.
- LEARN FROM: Daily synthesis across all items (not just per-item scoring). Insight extraction as structured data.

**rssfilter** (github.com/m0wer/rssfilter)
- Embedding-based recommendation. Tracks read articles, computes embeddings, clusters them, recommends similar.
- 7-service architecture: FastAPI + Redis + rq-worker + GPU worker + scheduler + proxy.
- Includes random articles to prevent filter bubbles.
- Needs ~10 articles read before generating recommendations.
- LEARN FROM: Embedding-based user profile from reading behavior. Random injection for serendipity. GPU worker separation for embeddings.

**UglyFeed** (github.com/fabriziosalmi/UglyFeed)
- Retrieve -> aggregate by similarity -> rewrite via LLM -> convert to RSS -> serve.
- Supports OpenAI, Groq, Anthropic, Ollama, Gemini.
- Includes content evaluation against reference.
- File-based storage (JSON), deploys to GitHub/GitLab.
- LEARN FROM: Similarity-based aggregation before LLM processing (reduces LLM calls). Content evaluation step.

### Tier 2: Adjacent / Infrastructure

**Daniel Miessler's PAI** (github.com/danielmiessler/Personal_AI_Infrastructure)
- Not an aggregator, but an "AI-powered operating system" with the most sophisticated memory/learning architecture.
- Three-tier memory: hot (session), warm (phase-based), cold (historical archive).
- SIGNALS/ratings.jsonl -- append-only JSONL: timestamp, task_id, signal_type, value, context.
- 7-phase loop: Observe -> Think -> Plan -> Build -> Execute -> Verify -> Learn.
- Signal types: ratings, sentiment, verification, modifications, context usage.
- Hook system captures signals at lifecycle events automatically.
- LEARN FROM: ratings.jsonl pattern for tracking scoring accuracy over time. Three-tier memory. The "learn" phase -- scoring feedback loop. ISC (Ideal State Criteria) as binary-testable acceptance criteria.

**Fabric** (github.com/danielmiessler/Fabric) -- 30k+ stars
- Collection of 200+ AI prompt patterns. Complementary to PAI.
- LEARN FROM: Prompt patterns as modular, shareable units. The "extract_wisdom" pattern specifically.

**GPT-Researcher** (github.com/assafelovic/gpt-researcher) -- 15k+ stars
- Deep research agent with planner/execution agents. Tree-like exploration.
- MCP integration for specialized data sources.
- LEARN FROM: Planner/execution agent split. MCP for source extensibility.

### FreshRSS + AI Extensions
- FeedDigest extension: auto-summarizes articles via OpenAI-compatible APIs during feed updates. Batch processing. Per-feed control.
- OllamaSummarizer: generates summaries + tags with local Ollama (gemma3:1b on CPU).
- AI Assistant: smart retitling, executive summaries, auto-tagging, category summarization.
- LEARN FROM: Per-feed LLM control. Local model support (Ollama) for cost reduction. Auto-tagging during ingestion.

### Miniflux (miniflux.app, github.com/miniflux/v2)
- Go binary, PostgreSQL, minimal memory. REST API + Fever/Google Reader API compat.
- 25+ integrations. Python client library.
- LEARN FROM: Could serve as Yatagarasu's RSS backend instead of raw urllib. API-first design. Feed polling + health built in.

---

## 2. INTELLIGENCE / OSINT TOOLS (Transferable Patterns)

### SpiderFoot (github.com/smicallef/spiderfoot) -- 13k+ stars
- Event-driven OSINT automation. 200+ modules. SQLite backend.
- KEY ARCHITECTURE: Modules declare watchedEvents() and producedEvents(). Framework routes automatically. Modules never call each other directly.
- Correlation engine: YAML-configured rules, 37 predefined rules. Post-hoc pattern detection on stored data.
- SQLite schema:
  - tbl_event_types: canonical event definitions
  - tbl_scan_results: findings with source attribution
  - tbl_scan_correlation_results: pattern matches
  - tbl_scan_log: activity trails
- Events contain: (source, type, data, parent_event). Immutable chain preserves audit trail.
- setAlias() links related identifiers for entity enrichment.
- ThreadPool for parallel module execution.
- TRANSFERABLE PATTERNS:
  1. Declarative module dependencies (watchedEvents/producedEvents)
  2. YAML correlation rules for multi-signal pattern detection
  3. Immutable event chain with parent references
  4. Post-hoc correlation (patterns from stored data, not hardcoded)
  5. Entity aliasing for cross-source resolution

### OpenCTI (github.com/OpenCTI-Platform/opencti)
- STIX 2.1 data model. GraphQL API. Microservices architecture.
- DUAL CONFIDENCE SYSTEM:
  - Source Reliability: organizational trust measurement (NATO Admiralty code). Applied to Organizations, Individuals, Systems, Reports.
  - Confidence: per-entity credibility on 0-100 scale. Three templates: Admiralty, Objective (Witnessed/Deduced/Induced/Told), Standard (Low/Med/High).
- Max Confidence Level: role-based constraint. Connectors/feeds assigned trust levels. Users with lower max confidence cannot modify higher-confidence entities.
- Feed ingestion: TAXII API (STIX 2.1 bundles), Live streams for real-time sharing.
- Reliability affects deduplication process and data stream filtering.
- TRANSFERABLE PATTERNS:
  1. Separate source reliability from content confidence (two-axis scoring)
  2. Confidence templates (map to Yatagarasu tiers: RED/ORANGE/YELLOW)
  3. Max confidence per source/connector -- weight feeds differently
  4. Confidence affects what can override what (higher-confidence sources win dedup)

### MISP (misp-project.org)
- Multi-origin ingestion. Consolidated workspace. Reduced API latency in 2.5.
- Simpler architecture than OpenCTI, easier for small teams.
- TRANSFERABLE: Feed consolidation patterns. Sharing/export formats.

---

## 3. ACADEMIC PAPER DISCOVERY TOOLS

### arxiv-sanity-lite (github.com/karpathy/arxiv-sanity-lite)
- Karpathy's tool. TF-IDF features on abstracts. SVM per user tag for personalized recommendations.
- Pipeline: arxiv_daemon.py polls API -> compute.py generates TF-IDF vectors -> SVM trains on tagged papers -> daily email recommendations.
- Storage: sqlitedict (acknowledged as hacky, wants proper SQLite).
- Runs on $5/mo Linode indexing ~30k papers.
- LEARN FROM: SVM-on-TF-IDF is lightweight personalization that improves with user feedback. Daily email digest from tags. The entire approach is cheap and effective.

### Semantic Scholar API (semanticscholar.org/product/api)
- 200M+ papers. SPECTER2 embeddings available via API.
- Services: Academic Graph, Recommendations, Datasets.
- Alerts: email for new citations and new papers. AI-powered Research Feeds per folder.
- FREE API, no key required for basic access.
- LEARN FROM: Use as a source alongside arxiv. SPECTER2 embeddings for paper similarity. Citation graph traversal for discovery.

### Connected Papers
- Built on Semantic Scholar corpus. Co-citation and bibliographic coupling for graph building.
- Papers clustered by similarity. Visual graph layout.
- LEARN FROM: Co-citation as signal (papers frequently cited together are related).

### ResearchRabbit (researchrabbit.ai)
- Upload RIS/BibTeX -> recommendations via Similar/Earlier/Later work modes.
- Powered by Semantic Scholar (non-medical) and PubMed (medical).
- LEARN FROM: Earlier/Later work temporal decomposition. Author-based recommendations.

### Elicit (elicit.com)
- 125M+ papers. Semantic search (meaning-based, not keyword).
- Architecture: "supervising reasoning processes, not outcomes." Open-source ICE library for compositional LM programs.
- Structured data extraction from papers.
- LEARN FROM: Semantic search over keyword search for paper discovery. Structured extraction patterns.

### Undermind (undermind.ai)
- Reads hundreds of papers, answers questions. Notification on relevant new papers.
- LEARN FROM: Question-driven discovery (not just keyword/topic).

### Ai2 Paper Finder (Allen Institute)
- Sub-agents with ranking scores. Re-ranks by combining semantic relevance + metadata (recency, citations).
- Fast mode vs deep mode.
- LEARN FROM: Multi-signal re-ranking (semantic + recency + citation count).

---

## 4. NEWSLETTER / DIGEST GENERATION

### Mailbrew (mailbrew.com)
- Acquired by Evernomic Nov 2025. 70k+ users. Rebuilt infrastructure.
- Mix-and-match sources (Reddit, RSS, Twitter, weather) into multiple "brews."
- Schedule per brew (morning tech, Friday fun).
- LEARN FROM: Multiple digest profiles per user (Yatagarasu could have "AI Morning," "CW Weekly," "Career Alert"). Per-brew scheduling. Source mixing as UX primitive.

### beehiiv
- RSS-to-Send automation: auto-creates newsletters from RSS feed.
- Full API: subscribers, emails, custom fields, segmentation.
- Integrations with Zapier/Make.
- LEARN FROM: Yatagarasu digest could auto-publish to beehiiv via API. RSS-to-Send as distribution channel.

### Buttondown
- API-first, single developer, minimalist. REST API for subscribers, emails, tags, metadata.
- LEARN FROM: If beehiiv is too heavy, Buttondown API is simpler for programmatic newsletter generation.

### Omnivore (RIP -- acquihired by ElevenLabs Nov 2024)
- Open source read-it-later with AI digest. TypeScript/Next.js.
- Digest feature: AI curates highlights from library. Delivered via email or app.
- Obsidian/Logseq integration.
- WHAT IT DID RIGHT: AI-curated digest from personal library. Obsidian sync.
- CODE STILL ON GITHUB: github.com/omnivore-app/omnivore -- worth studying the digest implementation.

---

## 5. KEY ARCHITECTURAL PATTERNS

### Deduplication Across Time

**Current Yatagarasu**: URL + title prefix (first 60 chars). In-memory only. No persistence.

**Better approaches by tier:**

1. IMMEDIATE: SQLite `seen_items` table with URL hash + title hash + first_seen timestamp. UNIQUE constraint on url_hash. Query with dedup_window_hours.
```sql
CREATE TABLE seen_items (
    url_hash TEXT PRIMARY KEY,
    title_hash TEXT,
    title TEXT,
    url TEXT,
    source TEXT,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    score INTEGER DEFAULT 0,
    tier TEXT
);
CREATE INDEX idx_seen_first ON seen_items(first_seen);
```

2. SCALABLE: Bloom filter for fast "definitely not seen" checks, SQLite as ground truth. pybloom-live (PyPI) provides ScalableBloomFilter that grows automatically. Serialize to disk between runs.
```python
from pybloom_live import ScalableBloomFilter
bf = ScalableBloomFilter(initial_capacity=10000, error_rate=0.001)
bf.add(url_hash)
if url_hash in bf:  # might be false positive, check SQLite
    ...
```

3. ADVANCED: Embedding-based near-duplicate detection. Compute sentence embedding of title+summary, check cosine similarity against recent items. Threshold ~0.92 for near-dupes.

### Feed Health Monitoring

**Pattern from OSINT/threat intel:**
```sql
CREATE TABLE feed_health (
    feed_id TEXT PRIMARY KEY,
    last_success DATETIME,
    last_failure DATETIME,
    consecutive_failures INTEGER DEFAULT 0,
    total_items_lifetime INTEGER DEFAULT 0,
    avg_items_per_fetch REAL DEFAULT 0,
    last_status_code INTEGER,
    last_error TEXT
);
```
- Alert after N consecutive failures.
- Track items_per_fetch trending to zero (feed dying).
- Log HTTP status codes (403/404 = feed moved/dead, 429 = rate limited).
- Auto-disable feed after threshold, surface in digest as "[FEED HEALTH] Transformer Circuits RSS returned 403 for 3 days."

### Relevance Scoring That Improves Over Time

**Current Yatagarasu**: One-shot Haiku scoring. No feedback loop.

**Improvement paths:**

1. FEEDBACK LOGGING (from PAI pattern): Append to scores.jsonl after each digest:
```json
{"date": "2026-04-06", "item_url": "...", "llm_score": 4, "tier": "ORANGE", "user_action": null}
```
Later, user marks items: "actually useful" / "noise" / "missed something important". This builds training data.

2. SVM-ON-TFIDF (from arxiv-sanity-lite): After accumulating ~50 labeled items, train a lightweight SVM on TF-IDF features of title+summary. Use as pre-filter BEFORE sending to Haiku. Items SVM scores <0.3 skip LLM entirely (saves API cost).

3. EMBEDDING PROFILE (from rssfilter): Compute embeddings of items user engages with. Cluster into interest centroids. New items closer to centroids get score boost. Items far from all centroids but passing LLM threshold get "serendipity" tag.

4. EXPONENTIAL DECAY: Apply recency weighting to relevance:
```python
import math
def decay_score(base_score, hours_old, half_life=24):
    return base_score * math.exp(-0.693 * hours_old / half_life)
```
RED items: half_life=48h. YELLOW items: half_life=12h.

5. SOURCE QUALITY TRACKING (from OpenCTI): Track per-source signal rate:
```sql
CREATE TABLE source_quality (
    source TEXT PRIMARY KEY,
    total_items INTEGER DEFAULT 0,
    items_scored_3plus INTEGER DEFAULT 0,
    items_scored_4plus INTEGER DEFAULT 0,
    signal_rate REAL DEFAULT 0,  -- items_scored_3plus / total_items
    last_updated DATETIME
);
```
Sources with consistently low signal_rate get deprioritized or flagged for review.

### State Management ("What Have I Already Seen?")

**Pattern synthesis across all tools:**

```
state/
  seen.db              # SQLite: URL hashes, title hashes, timestamps
  seen.bloom           # Serialized bloom filter for fast lookup
  scores.jsonl         # Append-only scoring history
  feed_health.json     # Per-feed status
  source_quality.json  # Signal rate per source
  user_profile.pkl     # SVM model or embedding centroids (if using)
```

SQLite is the right choice for Yatagarasu's scale (~200 items/day, <100k items/year). No need for PostgreSQL.

### Alert Fatigue Prevention

**Techniques from SOC/monitoring world:**

1. TIER BUDGET: Cap items per tier per digest. MAX 2 RED, 5 ORANGE, 10 YELLOW. If more items qualify, raise the threshold for that run.

2. CONSOLIDATION: Group related items. "3 papers on DPO variants published today" instead of listing all 3 separately.

3. ADAPTIVE THRESHOLDS: If average daily RED count > 1 over a week, the threshold is too low. Auto-adjust min_score upward.

4. DIGEST FREQUENCY CONTROL: Already have 3x daily. Consider: if morning sweep produced 2+ RED items, skip midday sweep and just re-check RED sources at evening.

5. SILENCE TRACKING: "5 consecutive clean days" is itself a signal (nothing happening in your domains, or your keywords need updating).

---

## 6. SPECIFIC TECHNICAL IMPLEMENTATIONS

### Python Libraries Worth Adopting

| Library | Purpose | Why |
|---------|---------|-----|
| `feedparser` | RSS/Atom parsing | Battle-tested, handles malformed feeds. Replace Yatagarasu's raw XML parsing. |
| `trafilatura` | Full article text extraction | Best precision/recall for web content. Replaces newspaper3k. |
| `pybloom-live` | Scalable bloom filter | Dedup. Grows automatically. Serializable. |
| `sentence-transformers` | Embedding computation | all-MiniLM-L6-v2 for fast similarity. |
| `scikit-learn` | TF-IDF + SVM | Lightweight personalization (arxiv-sanity pattern). |
| `datasketch` | MinHash LSH | Near-duplicate detection at scale. |
| `tiktoken` | Token counting | Estimate Haiku API costs before sending. |
| `sqlite-utils` | SQLite convenience | Simon Willison's tool. CLI + Python. |
| `httpx` | HTTP client | Async support, connection pooling. Replace urllib. |
| `tenacity` | Retry logic | Exponential backoff for API calls and feed fetches. |
| `structlog` | Structured logging | JSON logs for pipeline debugging. |
| `apscheduler` | Scheduling | Replace cron/launchd with in-process scheduling. |

### SQLite Schema for Yatagarasu v2

```sql
-- Core item tracking
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    title_hash TEXT NOT NULL,
    summary TEXT,
    source TEXT NOT NULL,        -- 'arxiv', 'hackernews', 'rss:Simon Willison', 'serp'
    domain TEXT NOT NULL,        -- 'ai_research', 'fashion_cw', etc.
    published DATE,
    first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    llm_score INTEGER,           -- 1-5
    tier TEXT,                   -- 'RED', 'ORANGE', 'YELLOW'
    llm_reason TEXT,
    digest_date DATE,            -- which digest included this
    user_rating INTEGER,         -- null until user rates. 1=noise, 2=ok, 3=valuable
    embedding BLOB               -- optional: sentence embedding for similarity
);

CREATE INDEX idx_items_first_seen ON items(first_seen);
CREATE INDEX idx_items_source ON items(source);
CREATE INDEX idx_items_tier ON items(tier);
CREATE INDEX idx_items_digest ON items(digest_date);

-- Feed health tracking
CREATE TABLE feed_health (
    feed_id TEXT PRIMARY KEY,     -- 'arxiv', 'rss:Simon Willison', etc.
    feed_url TEXT,
    last_success DATETIME,
    last_failure DATETIME,
    last_status_code INTEGER,
    last_error TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    total_fetches INTEGER DEFAULT 0,
    total_items INTEGER DEFAULT 0,
    avg_items_per_fetch REAL DEFAULT 0
);

-- Source signal quality
CREATE TABLE source_quality (
    source TEXT PRIMARY KEY,
    total_scored INTEGER DEFAULT 0,
    scored_3plus INTEGER DEFAULT 0,
    scored_4plus INTEGER DEFAULT 0,
    signal_rate REAL GENERATED ALWAYS AS (
        CASE WHEN total_scored > 0 THEN CAST(scored_3plus AS REAL) / total_scored ELSE 0 END
    ) STORED,
    premium_rate REAL GENERATED ALWAYS AS (
        CASE WHEN total_scored > 0 THEN CAST(scored_4plus AS REAL) / total_scored ELSE 0 END
    ) STORED
);

-- Digest metadata
CREATE TABLE digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    sweep_type TEXT NOT NULL,     -- 'full', 'light'
    items_fetched INTEGER,
    items_after_dedup INTEGER,
    items_scored INTEGER,
    items_surfaced INTEGER,
    red_count INTEGER,
    orange_count INTEGER,
    yellow_count INTEGER,
    haiku_tokens_used INTEGER,
    haiku_cost_cents REAL,
    filepath TEXT
);
```

### Bloom Filter Integration

```python
import hashlib
import os
import pickle
from pybloom_live import ScalableBloomFilter

BLOOM_PATH = "state/seen.bloom"

def load_bloom():
    if os.path.exists(BLOOM_PATH):
        with open(BLOOM_PATH, "rb") as f:
            return pickle.load(f)
    return ScalableBloomFilter(initial_capacity=10000, error_rate=0.001)

def save_bloom(bf):
    with open(BLOOM_PATH, "wb") as f:
        pickle.dump(bf, f)

def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().rstrip("/").encode()).hexdigest()

def is_seen(bf, url: str) -> bool:
    h = url_hash(url)
    return h in bf  # may have false positives at 0.1% rate

def mark_seen(bf, url: str):
    bf.add(url_hash(url))
```

### Exponential Decay Scoring

```python
import math
from datetime import datetime

HALF_LIFE = {
    "RED": 48,      # hours
    "ORANGE": 24,
    "YELLOW": 12,
}

def decayed_score(base_score: int, tier: str, published: datetime) -> float:
    hours_old = (datetime.now() - published).total_seconds() / 3600
    half_life = HALF_LIFE.get(tier, 24)
    decay = math.exp(-0.693 * hours_old / half_life)
    return base_score * decay
```

---

## 7. PRIORITIZED RECOMMENDATIONS FOR YATAGARASU

### Phase 1: Foundation (1-2 days)
1. Add SQLite state tracking (seen_items table). Persist dedup across runs.
2. Replace urllib with httpx. Add tenacity for retry logic.
3. Add feed_health table. Log success/failure per source.
4. Track digest metadata (items fetched/scored/surfaced, token usage).

### Phase 2: Scoring Intelligence (1 week)
5. Add scores.jsonl feedback log. After reading digest, rate items.
6. Implement source_quality tracking. Surface signal rates in digest footer.
7. Add tier budget caps to prevent alert fatigue.
8. Add exponential decay for recency weighting.

### Phase 3: Personalization (2 weeks)
9. Switch RSS parsing to feedparser.
10. Add Semantic Scholar as a source (free API, SPECTER2 embeddings).
11. Implement SVM-on-TF-IDF pre-filter (arxiv-sanity pattern) after 50+ rated items.
12. Add bloom filter for fast dedup.

### Phase 4: Distribution (when CW needs it)
13. Auto-publish AI Research digest section to beehiiv via API.
14. Add Obsidian dataview-compatible frontmatter to digests.
15. Weekly rollup digest (auto-news pattern).

---

## SOURCES

### Open-Source Projects
- auto-news: https://github.com/finaldie/auto-news
- feeds.fun: https://github.com/Tiendil/feeds.fun
- Precis: https://github.com/leozqin/precis
- RLLM: https://github.com/DanielZhangyc/RLLM
- rssfilter: https://github.com/m0wer/rssfilter
- UglyFeed: https://github.com/fabriziosalmi/UglyFeed
- PAI: https://github.com/danielmiessler/Personal_AI_Infrastructure
- Fabric: https://github.com/danielmiessler/Fabric
- GPT-Researcher: https://github.com/assafelovic/gpt-researcher
- arxiv-sanity-lite: https://github.com/karpathy/arxiv-sanity-lite
- SpiderFoot: https://github.com/smicallef/spiderfoot
- OpenCTI: https://github.com/OpenCTI-Platform/opencti
- Miniflux: https://github.com/miniflux/v2
- Omnivore: https://github.com/omnivore-app/omnivore
- feeds.fun HN discussion: https://news.ycombinator.com/item?id=43279239
- FreshRSS FeedDigest: https://github.com/fengchang/xExtension-FeedDigest
- FreshRSS AI Assistant: https://github.com/cvlc/freshrss-ai-assistant
- text-dedup: https://github.com/ChenghaoMou/text-dedup
- pybloom-live: https://pypi.org/project/pybloom-live/
- sqlite-bloomfilter: https://github.com/coleifer/sqlite3-bloomfilter

### Academic/Commercial Tools
- Semantic Scholar API: https://www.semanticscholar.org/product/api
- Connected Papers: https://www.connectedpapers.com
- ResearchRabbit: https://www.researchrabbit.ai
- Elicit: https://elicit.com
- Undermind: https://www.undermind.ai
- Ai2 Paper Finder: https://allenai.org/blog/paper-finder

### Newsletter/Digest Platforms
- Mailbrew: https://mailbrew.com
- beehiiv API: https://developers.beehiiv.com
- Buttondown: https://buttondown.com

### Architecture References
- OpenCTI confidence scoring: https://docs.opencti.io/latest/usage/reliability-confidence/
- OpenCTI data model: https://docs.opencti.io/latest/usage/data-model/
- PAI core architecture: https://deepwiki.com/danielmiessler/Personal_AI_Infrastructure/1.2-core-architecture
- SpiderFoot architecture: https://deepwiki.com/smicallef/spiderfoot
- Exponential decay scoring: https://milvus.io/docs/exponential-decay.md
- Bloom filters for dedup: https://dataget.ai/blogs/bloom-filter-web-scraping-deduplication/
- Trafilatura evaluation: https://trafilatura.readthedocs.io/en/latest/evaluation.html
