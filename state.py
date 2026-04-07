"""Yatagarasu - SQLite state management.

Tracks: seen items (dedup), feed health, source quality, digest metadata.
All state lives in state/yatagarasu.db.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from models import FeedItem


DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
DB_PATH = os.path.join(DB_DIR, "yatagarasu.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            source TEXT NOT NULL,
            domain TEXT NOT NULL,
            published TEXT,
            first_seen TEXT NOT NULL,
            llm_score INTEGER,
            tier TEXT,
            llm_reason TEXT,
            digest_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_items_first_seen ON items(first_seen);
        CREATE INDEX IF NOT EXISTS idx_items_source ON items(source);

        CREATE TABLE IF NOT EXISTS feed_health (
            feed_id TEXT PRIMARY KEY,
            feed_url TEXT,
            last_success TEXT,
            last_failure TEXT,
            last_status_code INTEGER,
            last_error TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            total_fetches INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS source_quality (
            source TEXT PRIMARY KEY,
            total_scored INTEGER DEFAULT 0,
            scored_3plus INTEGER DEFAULT 0,
            scored_4plus INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            sweep_type TEXT NOT NULL,
            items_fetched INTEGER,
            items_after_dedup INTEGER,
            items_scored INTEGER,
            items_surfaced INTEGER,
            red_count INTEGER DEFAULT 0,
            orange_count INTEGER DEFAULT 0,
            yellow_count INTEGER DEFAULT 0,
            filepath TEXT
        );
    """)
    conn.commit()
    conn.close()


# --- Dedup ---

def filter_seen(items: list[FeedItem], window_hours: int = 48) -> list[FeedItem]:
    """Return only items not seen within the dedup window."""
    if not items:
        return []
    conn = _connect()
    cutoff = (datetime.now() - timedelta(hours=window_hours)).isoformat()
    seen_ids = set()
    # batch query
    for item in items:
        row = conn.execute(
            "SELECT item_id FROM items WHERE item_id = ? AND first_seen > ?",
            (item.item_id, cutoff)
        ).fetchone()
        if row:
            seen_ids.add(item.item_id)
    conn.close()
    return [i for i in items if i.item_id not in seen_ids]


def record_items(items: list[FeedItem]):
    """Record items as seen. Upsert: don't overwrite existing entries."""
    if not items:
        return
    conn = _connect()
    now = datetime.now().isoformat()
    for item in items:
        conn.execute("""
            INSERT INTO items (item_id, url, title, summary, source, domain, published, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO NOTHING
        """, (item.item_id, item.url, item.title, item.summary[:500],
              item.source, item.domain, item.published, now))
    conn.commit()
    conn.close()


def update_scores(scored: list[tuple[FeedItem, int, str, str]]):
    """Update items with their LLM scores."""
    if not scored:
        return
    conn = _connect()
    for item, score, tier, reason in scored:
        conn.execute("""
            UPDATE items SET llm_score = ?, tier = ?, llm_reason = ?
            WHERE item_id = ?
        """, (score, tier, reason, item.item_id))
    conn.commit()
    conn.close()


# --- Feed Health ---

def record_fetch_success(feed_id: str, feed_url: str, item_count: int):
    """Record a successful fetch."""
    conn = _connect()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO feed_health (feed_id, feed_url, last_success, consecutive_failures, total_fetches, total_items)
        VALUES (?, ?, ?, 0, 1, ?)
        ON CONFLICT(feed_id) DO UPDATE SET
            last_success = ?,
            consecutive_failures = 0,
            total_fetches = total_fetches + 1,
            total_items = total_items + ?
    """, (feed_id, feed_url, now, item_count, now, item_count))
    conn.commit()
    conn.close()


def record_fetch_failure(feed_id: str, feed_url: str, status_code: int, error: str):
    """Record a failed fetch."""
    conn = _connect()
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO feed_health (feed_id, feed_url, last_failure, last_status_code, last_error, consecutive_failures, total_fetches)
        VALUES (?, ?, ?, ?, ?, 1, 1)
        ON CONFLICT(feed_id) DO UPDATE SET
            last_failure = ?,
            last_status_code = ?,
            last_error = ?,
            consecutive_failures = consecutive_failures + 1,
            total_fetches = total_fetches + 1
    """, (feed_id, feed_url, now, status_code, error, now, status_code, error))
    conn.commit()
    conn.close()


def get_feed_health() -> list[dict]:
    """Return all feed health records."""
    conn = _connect()
    rows = conn.execute("SELECT * FROM feed_health ORDER BY consecutive_failures DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sick_feeds(failure_threshold: int = 3) -> list[dict]:
    """Return feeds with consecutive failures >= threshold."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM feed_health WHERE consecutive_failures >= ?",
        (failure_threshold,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Source Quality ---

def update_source_quality(scored: list[tuple[FeedItem, int, str, str]]):
    """Update source quality metrics from scored items."""
    if not scored:
        return
    # aggregate by source
    by_source = {}
    for item, score, tier, reason in scored:
        src = item.source
        if src not in by_source:
            by_source[src] = {"total": 0, "s3": 0, "s4": 0}
        by_source[src]["total"] += 1
        if score >= 3:
            by_source[src]["s3"] += 1
        if score >= 4:
            by_source[src]["s4"] += 1

    conn = _connect()
    for src, counts in by_source.items():
        conn.execute("""
            INSERT INTO source_quality (source, total_scored, scored_3plus, scored_4plus)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                total_scored = total_scored + ?,
                scored_3plus = scored_3plus + ?,
                scored_4plus = scored_4plus + ?
        """, (src, counts["total"], counts["s3"], counts["s4"],
              counts["total"], counts["s3"], counts["s4"]))
    conn.commit()
    conn.close()


def get_source_quality() -> list[dict]:
    """Return source quality metrics."""
    conn = _connect()
    rows = conn.execute("""
        SELECT source, total_scored, scored_3plus, scored_4plus,
               CASE WHEN total_scored > 0 THEN ROUND(CAST(scored_3plus AS REAL) / total_scored, 2) ELSE 0 END as signal_rate,
               CASE WHEN total_scored > 0 THEN ROUND(CAST(scored_4plus AS REAL) / total_scored, 2) ELSE 0 END as premium_rate
        FROM source_quality
        ORDER BY signal_rate DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Digest Metadata ---

def record_digest(sweep_type: str, items_fetched: int, items_after_dedup: int,
                  items_scored: int, items_surfaced: int,
                  red: int, orange: int, yellow: int, filepath: str) -> int:
    """Record digest metadata. Returns digest id."""
    conn = _connect()
    now = datetime.now().isoformat()
    cursor = conn.execute("""
        INSERT INTO digests (timestamp, sweep_type, items_fetched, items_after_dedup,
                            items_scored, items_surfaced, red_count, orange_count, yellow_count, filepath)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (now, sweep_type, items_fetched, items_after_dedup, items_scored,
          items_surfaced, red, orange, yellow, filepath))
    digest_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return digest_id
