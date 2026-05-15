"""Yatagarasu - Contraband Wu bridge source.

Pulls entity velocity data from the CW database.
On Mac Mini: reads contraband.db directly (local).
On MacBook (or anywhere else): SSHes to Mac Mini and runs sqlite3 there.
"""
from __future__ import annotations

import json
import os
import subprocess
from models import FeedItem

MAC_MINI = "amadeus@100.106.203.57"
CW_DB_REMOTE = "~/Documents/GitHub/contraband-wu-intel/storage/data/contraband.db"
CW_DB_LOCAL = os.path.expanduser("~/Documents/GitHub/contraband-wu-intel/storage/data/contraband.db")
USE_LOCAL = os.path.exists(CW_DB_LOCAL)

VELOCITY_QUERY = (
    'SELECT e.entity, e.entity_type, e.entity_en, '
    'SUM(CASE WHEN r.scraped_at > datetime("now", "-7 days") THEN 1 ELSE 0 END) as this_week, '
    'SUM(CASE WHEN r.scraped_at > datetime("now", "-14 days") AND r.scraped_at <= datetime("now", "-7 days") THEN 1 ELSE 0 END) as last_week, '
    'COUNT(*) as total '
    'FROM entities e JOIN raw_posts r ON e.post_id = r.post_id '
    'GROUP BY e.entity, e.entity_type HAVING this_week >= 2 '
    'ORDER BY this_week DESC LIMIT 30;'
)

RECENT_CODED_QUERY = (
    'SELECT e.entity, e.entity_en, e.mention_count, '
    'SUM(CASE WHEN r.scraped_at > datetime("now", "-3 days") THEN 1 ELSE 0 END) as recent '
    'FROM entities e JOIN raw_posts r ON e.post_id = r.post_id '
    'WHERE e.entity_type = "coded" AND e.entity_en IS NOT NULL AND e.entity_en != "" '
    'GROUP BY e.entity HAVING recent > 0 ORDER BY recent DESC LIMIT 10;'
)


def _ssh_query(query: str) -> str:
    """Run a SQLite query on Mac Mini — local if available, else via SSH."""
    if USE_LOCAL:
        cmd = ["sqlite3", "-json", CW_DB_LOCAL]
    else:
        remote_cmd = f"sqlite3 -json {CW_DB_REMOTE}"
        cmd = [
            "ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            MAC_MINI, remote_cmd,
        ]
    try:
        result = subprocess.run(cmd, input=query, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            print(f"[cw_bridge] query error: {result.stderr.strip()}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("[cw_bridge] query timeout")
        return ""
    except Exception as e:
        print(f"[cw_bridge] query error: {e}")
        return ""


def _parse_json(raw: str) -> list[dict]:
    """Parse sqlite3 -json output."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fallback: try line-by-line
        print(f"[cw_bridge] JSON parse failed, trying pipe-delimited fallback")
        return []


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch entity velocity data from CW on Mac Mini."""
    if sweep_type == "light" and source_config.get("sweep", "full") == "full":
        return []

    items = []

    # 1. Entity velocity — aesthetic/product movers
    print("[cw_bridge] querying entity velocity...")
    raw = _ssh_query(VELOCITY_QUERY)
    rows = _parse_json(raw)

    for row in rows:
        entity = row.get("entity", "")
        entity_en = row.get("entity_en", "")
        entity_type = row.get("entity_type", "")
        this_week = row.get("this_week", 0)
        last_week = row.get("last_week", 0)
        total = row.get("total", 0)

        # calculate velocity
        if last_week > 0:
            velocity = ((this_week - last_week) / last_week) * 100
            vel_str = f"+{velocity:.0f}%" if velocity > 0 else f"{velocity:.0f}%"
        elif this_week > 0:
            vel_str = "NEW"
            velocity = 100
        else:
            continue

        label = f"{entity} ({entity_en})" if entity_en else entity
        title = f"[CW {entity_type}] {label}: {this_week} mentions this week ({vel_str} vs last week)"
        summary = (
            f"Chinese consumer signal: {entity_type} entity '{label}' has {this_week} mentions "
            f"this week vs {last_week} last week ({vel_str}). Total lifetime: {total}. "
            f"Source: XHS + Bilibili via Contraband Wu pipeline."
        )

        items.append(FeedItem(
            title=title,
            url=f"cw://entity/{entity}",
            summary=summary,
            source="cw_bridge",
            domain="chinese_consumer",
            published="",
            item_id=f"cw_vel_{entity}_{this_week}",
        ))

    # 2. Coded language — recent euphemisms
    print("[cw_bridge] querying coded language...")
    raw = _ssh_query(RECENT_CODED_QUERY)
    rows = _parse_json(raw)

    for row in rows:
        entity = row.get("entity", "")
        entity_en = row.get("entity_en", "")
        recent = row.get("recent", 0)
        total = row.get("mention_count", 0)

        title = f"[CW coded] {entity} ({entity_en}): {recent} recent uses"
        summary = (
            f"Coded language detection: '{entity}' translates to '{entity_en}'. "
            f"{recent} uses in last 3 days, {total} total. "
            f"Chinese internet euphemism tracked by Contraband Wu."
        )

        items.append(FeedItem(
            title=title,
            url=f"cw://coded/{entity}",
            summary=summary,
            source="cw_bridge",
            domain="chinese_consumer",
            published="",
            item_id=f"cw_coded_{entity}_{recent}",
        ))

    print(f"[cw_bridge] {len(items)} signals from CW")
    return items
