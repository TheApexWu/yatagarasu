"""Yatagarasu - Trending detection.

Detects breakout signals: entities appearing in 3+ distinct sources within 24h.
Uses simple regex-based entity extraction -- no external NLP libraries.
"""

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from models import FeedItem

# Stopwords to skip when extracting capitalized phrases
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "its", "as", "are", "was",
    "were", "be", "been", "has", "have", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "shall",
    "not", "no", "nor", "so", "yet", "both", "each", "few", "more",
    "most", "other", "some", "such", "than", "too", "very", "just",
    "about", "above", "after", "again", "all", "also", "any", "because",
    "before", "between", "down", "during", "even", "every", "first",
    "how", "if", "into", "like", "new", "now", "only", "out", "over",
    "own", "same", "she", "he", "they", "this", "that", "these", "those",
    "through", "under", "until", "up", "what", "when", "where", "which",
    "while", "who", "whom", "why", "you", "your", "we", "our", "my",
    "his", "her", "their", "i", "me", "us", "vs", "via",
    # Common title filler
    "using", "based", "open", "source", "data", "model", "system",
    "paper", "show", "shows", "says", "announces", "launches", "gets",
    "makes", "reveals", "plans", "report", "update", "way", "things",
    "here", "there", "then", "still", "already", "really", "going",
    "build", "built", "world", "best", "next", "full", "long", "last",
    "big", "top", "high", "low", "old", "real", "right", "left",
    "look", "looking", "find", "found", "help", "need", "want", "use",
    "work", "working", "think", "know", "time", "year", "years",
    "market", "company", "product", "app", "day", "week", "today",
    "good", "great", "free", "live", "start", "end", "take", "back",
    "much", "many", "well", "part", "kind", "case", "point", "set",
}

# Patterns that look like entities: 1-4 consecutive capitalized words
# Also matches single-letter + Cap (e.g. "Y Combinator") and CamelCase (e.g. "OpenAI")
_CAP_PHRASE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")

# CamelCase / mixed-case proper nouns (OpenAI, DeepMind, GitHub, etc.)
_CAMELCASE = re.compile(r"\b([A-Z][a-z]+[A-Z][A-Za-z]*)\b")

# Single uppercase letter + capitalized word (Y Combinator, X Corp)
_LETTER_PREFIX = re.compile(r"\b([A-Z]\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")

# All-caps tokens (acronyms): 2-6 uppercase letters
_ACRONYM = re.compile(r"\b([A-Z]{2,6})\b")

# Noise acronyms to skip
_SKIP_ACRONYMS = {"AI", "ML", "US", "UK", "EU", "CEO", "CTO", "VP", "PM",
                  "API", "SDK", "RSS", "URL", "PDF", "LLM", "GPU", "CPU",
                  "RAM", "SSD", "HDD", "SQL", "CSS", "HTML", "HTTP", "JSON",
                  "XML", "YC", "VC", "IPO", "NYC", "SF", "LA", "DC", "MIT",
                  "PHD", "MBA", "BSC", "MSC", "PR", "QA", "HR", "FYI",
                  "FAQ", "TBD", "ETA", "ROI", "KPI", "MVP", "NLP", "CV",
                  "GAN", "RNN", "CNN", "LLM", "RAG", "AGI", "ASI"}


@dataclass
class TrendingSignal:
    entity: str
    source_count: int
    sources: list[str]
    first_seen: str
    titles: list[str]


def _normalize(s: str) -> str:
    """Lowercase, strip whitespace."""
    return s.strip().lower()


def _extract_entities(title: str) -> set[str]:
    """Extract candidate entity names from a title string."""
    entities = set()

    # Capitalized phrases (e.g. "Sam Altman", "Deep Learning")
    for m in _CAP_PHRASE.finditer(title):
        phrase = m.group(1)
        words = phrase.split()
        if len(words) == 1 and words[0].lower() in _STOPWORDS:
            continue
        if all(w.lower() in _STOPWORDS for w in words):
            continue
        entities.add(_normalize(phrase))

    # CamelCase proper nouns (OpenAI, DeepMind, GitHub)
    for m in _CAMELCASE.finditer(title):
        entities.add(_normalize(m.group(1)))

    # Letter-prefix names (Y Combinator, X Corp)
    for m in _LETTER_PREFIX.finditer(title):
        entities.add(_normalize(m.group(1)))

    # Acronyms
    for m in _ACRONYM.finditer(title):
        acr = m.group(1)
        if acr not in _SKIP_ACRONYMS:
            entities.add(acr.lower())

    return entities


def _load_recent_items(db_path: str, hours: int = 24) -> list[dict]:
    """Load items from the last N hours from SQLite."""
    import os
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute(
        "SELECT title, source, first_seen FROM items WHERE first_seen > ?",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def detect_trending(
    scored_items: list[tuple[FeedItem, int, str, str]],
    config: dict,
    db_path: str | None = None,
) -> list[TrendingSignal]:
    """Detect entities appearing in 3+ distinct sources within 24h.

    Combines current scored batch with historical items from SQLite.
    Returns TrendingSignals sorted by source_count descending.
    """
    threshold = config.get("trending", {}).get("threshold", 3)
    window_hours = config.get("trending", {}).get("window_hours", 24)

    # Resolve DB path
    if db_path is None:
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "yatagarasu.db"
        )

    # entity -> {source -> [titles]}
    entity_sources: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    # entity -> first_seen timestamp
    entity_first_seen: dict[str, str] = {}

    # Process current batch
    now_iso = datetime.now().isoformat()
    for item, score, tier, reason in scored_items:
        entities = _extract_entities(item.title)
        for ent in entities:
            entity_sources[ent][item.source].append(item.title)
            if ent not in entity_first_seen:
                entity_first_seen[ent] = now_iso

    # Process historical items from DB
    historical = _load_recent_items(db_path, hours=window_hours)
    for row in historical:
        entities = _extract_entities(row["title"])
        for ent in entities:
            entity_sources[ent][row["source"]].append(row["title"])
            ts = row.get("first_seen", now_iso)
            if ent not in entity_first_seen or ts < entity_first_seen[ent]:
                entity_first_seen[ent] = ts

    # Filter to entities meeting threshold
    signals = []
    seen_titles = set()  # deduplicate titles across entities

    # Skip single-word entities that are too generic (only keep multi-word or known proper nouns)
    _KNOWN_ENTITIES = {"mercari", "buyee", "grailhunt", "anthropic", "openai", "google",
                       "nvidia", "stripe", "antler", "apple", "meta", "microsoft",
                       "deepmind", "mistral", "amazon", "tesla", "shopify", "vercel"}

    for entity, sources_map in entity_sources.items():
        distinct_sources = list(sources_map.keys())
        if len(distinct_sources) < threshold:
            continue
        # Skip single-word generic entities unless they're known proper nouns
        if " " not in entity and entity not in _KNOWN_ENTITIES:
            continue

        # Collect unique titles
        titles = []
        for src_titles in sources_map.values():
            for t in src_titles:
                if t not in seen_titles:
                    titles.append(t)

        signals.append(TrendingSignal(
            entity=entity,
            source_count=len(distinct_sources),
            sources=sorted(distinct_sources),
            first_seen=entity_first_seen.get(entity, now_iso),
            titles=titles[:10],  # cap at 10 titles per entity
        ))

    # Sort by source count descending, then alphabetically
    signals.sort(key=lambda s: (-s.source_count, s.entity))

    # Mark titles as seen to avoid duplicates across signals
    for sig in signals:
        for t in sig.titles:
            seen_titles.add(t)

    return signals


def record_trending(signals: list[TrendingSignal], db_path: str | None = None):
    """Write trending signals to the trending_alerts table."""
    if not signals:
        return

    import os
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "state", "yatagarasu.db"
        )

    conn = sqlite3.connect(db_path)
    now = datetime.now().isoformat()
    for sig in signals:
        conn.execute("""
            INSERT OR REPLACE INTO trending_alerts
            (entity, source_count, sources, first_seen, detected_at)
            VALUES (?, ?, ?, ?, ?)
        """, (sig.entity, sig.source_count, ",".join(sig.sources),
              sig.first_seen, now))
    conn.commit()
    conn.close()
