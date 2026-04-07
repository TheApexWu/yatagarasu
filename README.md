# Yatagarasu

Autonomous signal curation that runs while you sleep, scores everything against your actual work, and only shows you what matters.

Named for the three-legged crow -- divine guide through noise.

## What it does

Yatagarasu monitors your sources (arxiv, Hacker News, RSS feeds, web search) on a schedule, scores every item against your personal profile using an LLM, and drops a markdown digest with only what's above the noise floor.

After a week it tells you which sources are actually producing signal and which are dead weight.

```
$ python yatagarasu.py --health

=== FEED HEALTH ===
  rss:Simon Willison             OK              fetches: 21, items: 630
  rss:Anthropic (community)      OK              fetches: 21, items: 315

=== SOURCE QUALITY ===
  arxiv                          signal: 28% (147/525)
  rss:Simon Willison             signal: 10% (63/630)
  rss:Marginal Revolution        signal: 0% (0/315)
```

## Why

Most people's information diet is 90% noise they've never audited.

- RSS readers show you everything. No scoring, no priority.
- ChatGPT/Claude are stateless. They can't run on a schedule, can't remember what you already read, can't track source quality over time.
- Feedly/Perplexity are black boxes. You can't see why something was surfaced or how your sources perform.

Yatagarasu is the opposite: transparent, config-driven, self-auditing. You define what matters in a YAML file. It does the rest.

## Features

- **Multi-source ingestion**: arxiv, Hacker News, any RSS/Atom feed, SerpAPI web search. Pluggable -- add new source types with one Python file.
- **LLM scoring**: Claude Haiku scores items 1-5 against your profile. RED/ORANGE/YELLOW tiers. Configurable tier budgets prevent alert fatigue.
- **Persistent dedup**: SQLite tracks what you've already seen. Items within a 48h window are suppressed across runs.
- **Feed health monitoring**: Tracks consecutive failures per feed. Dead feeds get surfaced in your digest, not silently ignored.
- **Source quality tracking**: Signal rate (% of items scoring 3+) per source, accumulated over time. Know which sources are worth your attention.
- **Extraction validation**: Items are validated post-fetch. Sources returning garbage get flagged.
- **Config-driven everything**: Profile, domains, keywords, sources, noise filters, tier budgets -- all in `config.yaml`.
- **Scheduled automation**: 3x daily via launchd (macOS) or cron.

## Setup

```bash
# clone
git clone https://github.com/TheApexWu/yatagarasu.git
cd yatagarasu

# install (just pyyaml)
pip install -r requirements.txt

# configure
cp .env.example .env
# add your ANTHROPIC_API_KEY (required) -- get it at https://console.anthropic.com/settings/keys
# add SERP_API_KEY (optional) -- get it at https://serpapi.com/manage-api-key

cp config.example.yaml config.yaml
# edit config.yaml -- set your profile, domains, sources

# test
source .env && python yatagarasu.py --dry-run
```

## Usage

```bash
# full sweep (all sources)
python yatagarasu.py

# light sweep (reduced scope)
python yatagarasu.py --light

# dry run (score but don't write file)
python yatagarasu.py --dry-run

# fetch only, no scoring (debug)
python yatagarasu.py --sources-only

# check feed health + source quality
python yatagarasu.py --health
```

## Automate (macOS)

```bash
bash install.sh
# creates 3 launchd jobs: 6:30am (full), 12:30pm (light), 6:30pm (light)
```

## Configuration

Everything lives in `config.yaml`. Key sections:

**profile** -- who you are, what you're working on. Drives LLM scoring.
```yaml
profile:
  description: "a ML researcher focused on computer vision"
  projects:
    - "CVPR paper on diffusion guidance"
    - "Open-source image segmentation tool"
  noise_patterns:
    - "Benchmark leaderboard drama"
    - "AI doomer culture war"
```

**sources** -- what to monitor. Add/remove without touching code.
```yaml
sources:
  rss:
    feeds:
      - name: "Your Blog"
        url: "https://yourblog.com/feed/"
        domain: "your_domain"
  hackernews:
    search_terms:
      - query: "diffusion models"
        domain: "ai_research"
```

**domains** -- what you care about, with weights.
```yaml
domains:
  ai_research:
    weight: 1.0
    keywords: ["diffusion", "guidance", "score matching"]
  industry:
    weight: 0.6
    keywords: ["Series A", "computer vision startup"]
```

## Adding a new source type

1. Create `sources/reddit_feed.py`:
```python
from models import FeedItem

def fetch(source_config, global_config, sweep_type):
    # your fetch logic
    return [FeedItem(title=..., url=..., summary=..., source="reddit", domain=..., published=...)]
```

2. Register in `sources/__init__.py`:
```python
from sources import reddit_feed
SOURCE_TYPES["reddit"] = reddit_feed
```

3. Add config:
```yaml
sources:
  reddit:
    enabled: true
    subreddits: ["MachineLearning", "LocalLLaMA"]
```

## Architecture

```
config.yaml          -- what you care about
sources/             -- pluggable fetchers (arxiv, HN, RSS, SERP)
models.py            -- FeedItem dataclass
validate.py          -- post-extraction quality checks
scorer.py            -- LLM scoring (Claude Haiku)
digest.py            -- markdown rendering + health alerts
state.py             -- SQLite: dedup, feed health, source quality
yatagarasu.py        -- pipeline orchestrator
state/yatagarasu.db  -- persistent state (gitignored)
```

Pipeline: `Fetch -> Validate -> Dedup (in-memory) -> Noise filter -> Dedup (SQLite) -> Score (LLM) -> Render -> Write`

## Requirements

- Python 3.10+
- `pyyaml`
- Anthropic API key (for Claude Haiku scoring)
- Optional: SerpAPI key (for web search source)

## License

MIT
