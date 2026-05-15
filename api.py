#!/usr/bin/env python3
"""
Yatagarasu API -- JSON endpoints for signal intelligence.

Usage:
    python api.py                # serve on localhost:8000
    python api.py --port 9000    # custom port
"""

import argparse
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import yaml

import state

app = FastAPI(title="Yatagarasu", version="1.0", description="Signal curation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def _db():
    conn = state._connect()
    return conn


# ---- ENDPOINTS ----


@app.get("/api/digest")
def get_digest(
    limit: int = Query(30, ge=1, le=200),
    hours: int = Query(24, ge=1, le=720),
):
    """Latest scored items, grouped by tier, with signal analytics."""
    conn = _db()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT item_id, url, title, summary, source, domain, published,
               first_seen, llm_score, tier, llm_reason
        FROM items
        WHERE tier IN ('RED', 'ORANGE', 'YELLOW') AND first_seen > ?
        ORDER BY
            CASE tier WHEN 'RED' THEN 0 WHEN 'ORANGE' THEN 1 WHEN 'YELLOW' THEN 2 ELSE 3 END,
            llm_score DESC
        LIMIT ?
    """, (cutoff, limit)).fetchall()

    items = [dict(r) for r in rows]
    tiers = {"RED": [], "ORANGE": [], "YELLOW": []}
    for item in items:
        t = item.get("tier")
        if t in tiers:
            tiers[t].append(item)

    # Signal analytics: total fetched vs surfaced in this window
    total_fetched = conn.execute(
        "SELECT COUNT(*) FROM items WHERE first_seen > ?", (cutoff,)
    ).fetchone()[0]
    surfaced = len(items)
    noise_kill_rate = round(1 - (surfaced / total_fetched), 3) if total_fetched > 0 else 0

    # Signal density per domain and hottest domain
    domain_rows = conn.execute("""
        SELECT domain,
               COUNT(*) as total,
               SUM(CASE WHEN tier IN ('RED', 'ORANGE') THEN 1 ELSE 0 END) as hot
        FROM items
        WHERE first_seen > ? AND tier IN ('RED', 'ORANGE', 'YELLOW')
        GROUP BY domain
        ORDER BY hot DESC
    """, (cutoff,)).fetchall()
    conn.close()

    signal_density = {}
    hottest_domain = None
    max_hot = 0
    for dr in domain_rows:
        d = dict(dr)
        signal_density[d["domain"]] = {
            "surfaced": d["total"],
            "hot": d["hot"],
            "density": round(d["hot"] / d["total"], 2) if d["total"] > 0 else 0,
        }
        if d["hot"] > max_hot:
            max_hot = d["hot"]
            hottest_domain = d["domain"]

    return {
        "generated_at": datetime.now().isoformat(),
        "window_hours": hours,
        "total": surfaced,
        "items_fetched": total_fetched,
        "noise_kill_rate": noise_kill_rate,
        "hottest_domain": hottest_domain,
        "signal_density": signal_density,
        "tiers": tiers,
        "counts": {k: len(v) for k, v in tiers.items()},
    }


@app.get("/api/items")
def get_items(
    tier: str = Query(None),
    domain: str = Query(None),
    source: str = Query(None),
    hours: int = Query(48, ge=1, le=720),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Filtered item query."""
    conn = _db()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    where = ["first_seen > ?"]
    params: list = [cutoff]

    if tier:
        where.append("tier = ?")
        params.append(tier.upper())
    if domain:
        where.append("domain = ?")
        params.append(domain)
    if source:
        where.append("source LIKE ?")
        params.append(f"%{source}%")

    where_sql = " AND ".join(where)
    params.extend([limit, offset])

    rows = conn.execute(f"""
        SELECT item_id, url, title, summary, source, domain, published,
               first_seen, llm_score, tier, llm_reason
        FROM items WHERE {where_sql}
        ORDER BY first_seen DESC
        LIMIT ? OFFSET ?
    """, params).fetchall()

    total = conn.execute(f"SELECT COUNT(*) FROM items WHERE {where_sql}", params[:-2]).fetchone()[0]
    conn.close()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {"tier": tier, "domain": domain, "source": source, "hours": hours},
    }


@app.get("/api/sources")
def get_sources():
    """Source quality metrics -- portfolio performance view with tiered ranking."""
    quality = state.get_source_quality()
    health = state.get_feed_health()

    # merge health into quality by source name
    health_map = {h["feed_id"]: h for h in health}

    sources = []
    for q in quality:
        entry = {
            "source": q["source"],
            "total_scored": q["total_scored"],
            "scored_3plus": q["scored_3plus"],
            "scored_4plus": q["scored_4plus"],
            "signal_rate": q["signal_rate"],
            "premium_rate": q["premium_rate"],
        }
        # attach health if available
        h = health_map.get(q["source"])
        if h:
            entry["consecutive_failures"] = h["consecutive_failures"]
            entry["total_fetches"] = h["total_fetches"]
            entry["total_items"] = h["total_items"]
            entry["status"] = "DEAD" if h["consecutive_failures"] >= 3 else (
                "WARN" if h["consecutive_failures"] > 0 else "LIVE"
            )
        else:
            entry["status"] = "UNKNOWN"
        sources.append(entry)

    # Sort by signal rate descending
    sources.sort(key=lambda s: s["signal_rate"], reverse=True)

    # Tier sources into portfolio buckets
    alpha_generators = [s for s in sources if s["signal_rate"] > 0.40]
    reliable = [s for s in sources if 0.15 <= s["signal_rate"] <= 0.40]
    noisy = [s for s in sources if s["signal_rate"] < 0.15]
    dead_sources = [s for s in sources if s.get("status") == "DEAD"]

    return {
        "portfolio": {
            "alpha_generators": alpha_generators,
            "reliable": reliable,
            "noisy": noisy,
        },
        "sources": sources,
        "total_sources": len(sources),
        "dead_sources": len(dead_sources),
        "avg_signal_rate": round(
            sum(s["signal_rate"] for s in sources) / len(sources), 3
        ) if sources else 0,
    }


@app.get("/api/trending")
def get_trending(hours: int = Query(48, ge=1, le=720)):
    """Cross-source trending signals."""
    conn = _db()
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT entity, source_count, sources, first_seen, detected_at
        FROM trending_alerts
        WHERE detected_at > ?
        ORDER BY source_count DESC, detected_at DESC
    """, (cutoff,)).fetchall()
    conn.close()

    # deduplicate by entity (keep highest source_count)
    seen = {}
    for r in rows:
        entity = r["entity"]
        if entity not in seen or r["source_count"] > seen[entity]["source_count"]:
            seen[entity] = dict(r)

    return {
        "trending": list(seen.values()),
        "window_hours": hours,
        "total": len(seen),
    }


@app.get("/api/domains")
def get_domains():
    """Domain configuration -- show what verticals are active."""
    config = _load_config()
    domains = config.get("domains", {})

    result = {}
    for name, cfg in domains.items():
        # count items in this domain
        conn = _db()
        count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE domain = ?", (name,)
        ).fetchone()[0]
        tier_counts = {}
        for row in conn.execute(
            "SELECT tier, COUNT(*) as c FROM items WHERE domain = ? AND tier IS NOT NULL GROUP BY tier",
            (name,)
        ).fetchall():
            tier_counts[row["tier"]] = row["c"]
        conn.close()

        result[name] = {
            "weight": cfg.get("weight", 1.0),
            "keywords": cfg.get("keywords", [])[:5],  # sample
            "keyword_count": len(cfg.get("keywords", [])),
            "total_items": count,
            "tier_breakdown": tier_counts,
        }

    return {"domains": result, "total_domains": len(result)}


@app.get("/api/stats")
def get_stats():
    """System-wide statistics."""
    conn = _db()
    total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_scored = conn.execute("SELECT COUNT(*) FROM items WHERE tier IS NOT NULL").fetchone()[0]
    total_digests = conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0]

    cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = conn.execute("SELECT COUNT(*) FROM items WHERE first_seen > ?", (cutoff_24h,)).fetchone()[0]

    tier_counts = {}
    for row in conn.execute(
        "SELECT tier, COUNT(*) as c FROM items WHERE tier IN ('RED','ORANGE','YELLOW') GROUP BY tier"
    ).fetchall():
        tier_counts[row["tier"]] = row["c"]

    # last digest
    last_digest = conn.execute(
        "SELECT * FROM digests ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    return {
        "total_items": total_items,
        "total_scored": total_scored,
        "total_digests": total_digests,
        "items_last_24h": recent,
        "tier_counts": tier_counts,
        "last_digest": dict(last_digest) if last_digest else None,
    }


@app.get("/api/performance")
def get_performance():
    """System performance metrics -- sweep history and signal trends."""
    conn = _db()

    # Last 10 sweeps
    sweeps = conn.execute("""
        SELECT id, timestamp, sweep_type, items_fetched, items_after_dedup,
               items_scored, items_surfaced, red_count, orange_count, yellow_count
        FROM digests
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()
    sweeps = [dict(s) for s in sweeps]

    # Compute per-sweep metrics
    for s in sweeps:
        fetched = s.get("items_fetched") or 0
        surfaced = s.get("items_surfaced") or 0
        s["noise_kill_rate"] = round(1 - (surfaced / fetched), 3) if fetched > 0 else 0
        s["signal_count"] = (s.get("red_count") or 0) + (s.get("orange_count") or 0) + (s.get("yellow_count") or 0)

    # Trend: average signal rate over last 10 sweeps
    signal_rates = [s["noise_kill_rate"] for s in sweeps]
    avg_noise_kill = round(sum(signal_rates) / len(signal_rates), 3) if signal_rates else 0

    # Total lifetime stats
    lifetime = conn.execute("""
        SELECT COUNT(*) as total_sweeps,
               SUM(items_fetched) as total_fetched,
               SUM(items_surfaced) as total_surfaced,
               SUM(red_count) as total_red,
               SUM(orange_count) as total_orange,
               SUM(yellow_count) as total_yellow
        FROM digests
    """).fetchone()
    conn.close()

    lt = dict(lifetime) if lifetime else {}
    total_f = lt.get("total_fetched") or 0
    total_s = lt.get("total_surfaced") or 0

    return {
        "sweeps": list(reversed(sweeps)),  # chronological order
        "sweep_count": len(sweeps),
        "avg_noise_kill_rate": avg_noise_kill,
        "lifetime": {
            "total_sweeps": lt.get("total_sweeps") or 0,
            "total_fetched": total_f,
            "total_surfaced": total_s,
            "lifetime_noise_kill_rate": round(1 - (total_s / total_f), 3) if total_f > 0 else 0,
            "total_red": lt.get("total_red") or 0,
            "total_orange": lt.get("total_orange") or 0,
            "total_yellow": lt.get("total_yellow") or 0,
        },
    }


@app.get("/api/items/timeline")
def get_items_timeline(days: int = Query(7, ge=1, le=30)):
    """Items per day grouped by tier -- chart-ready time series."""
    conn = _db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    rows = conn.execute("""
        SELECT DATE(first_seen) as day,
               tier,
               COUNT(*) as count
        FROM items
        WHERE first_seen >= ? AND tier IN ('RED', 'ORANGE', 'YELLOW')
        GROUP BY day, tier
        ORDER BY day ASC
    """, (cutoff,)).fetchall()

    # Also get total items per day (including noise) for signal rate calc
    total_rows = conn.execute("""
        SELECT DATE(first_seen) as day, COUNT(*) as count
        FROM items
        WHERE first_seen >= ?
        GROUP BY day
        ORDER BY day ASC
    """, (cutoff,)).fetchall()
    conn.close()

    total_by_day = {r["day"]: r["count"] for r in total_rows}

    # Build chart-ready structure
    days_data = {}
    for r in rows:
        day = r["day"]
        if day not in days_data:
            days_data[day] = {"day": day, "RED": 0, "ORANGE": 0, "YELLOW": 0, "total_fetched": total_by_day.get(day, 0)}
        days_data[day][r["tier"]] = r["count"]

    # Fill in missing days
    timeline = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        if d in days_data:
            entry = days_data[d]
        else:
            entry = {"day": d, "RED": 0, "ORANGE": 0, "YELLOW": 0, "total_fetched": total_by_day.get(d, 0)}
        entry["surfaced"] = entry["RED"] + entry["ORANGE"] + entry["YELLOW"]
        entry["signal_rate"] = round(entry["surfaced"] / entry["total_fetched"], 3) if entry["total_fetched"] > 0 else 0
        timeline.append(entry)

    return {
        "timeline": timeline,
        "days": days,
        "summary": {
            "avg_daily_surfaced": round(sum(t["surfaced"] for t in timeline) / len(timeline), 1) if timeline else 0,
            "avg_daily_signal_rate": round(sum(t["signal_rate"] for t in timeline) / len(timeline), 3) if timeline else 0,
            "best_day": max(timeline, key=lambda t: t["surfaced"])["day"] if timeline else None,
            "total_red": sum(t["RED"] for t in timeline),
            "total_orange": sum(t["ORANGE"] for t in timeline),
            "total_yellow": sum(t["YELLOW"] for t in timeline),
        },
    }


# ---- SERVE DASHBOARD ----

@app.get("/")
def serve_dashboard():
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    return {"message": "Yatagarasu API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    parser = argparse.ArgumentParser(description="Yatagarasu API server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()

    state.init_db()
    print(f"[yatagarasu-api] serving on http://{args.host}:{args.port}")
    print(f"[yatagarasu-api] dashboard: http://{args.host}:{args.port}/")
    print(f"[yatagarasu-api] api docs:  http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
