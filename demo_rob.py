#!/usr/bin/env python3
"""
Yatagarasu -- Live Demo for Rob Choi.

Guided terminal walkthrough. Not interactive beyond "Press Enter" pacing.
Reads directly from SQLite (Yatagarasu local, CW via SSH to Mac Mini).

Usage:
    python demo_rob.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta

# ---- PATHS ----
REPO = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(REPO, "state", "yatagarasu.db")
CONFIG_PATH = os.path.join(REPO, "config.yaml")
CW_HOST = "amadeus@100.106.203.57"
CW_DB = "~/Documents/GitHub/contraband-wu-intel/storage/data/contraband.db"

# ---- GLYPHS ----
TORII = "\u26E9"
BAR_FULL = "\u2588"
BAR_LOW = "\u2591"
DOT = "\u00B7"
LIVE = "\u25CF"

# ---- ANSI COLORS ----
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[38;5;196m"
    ORANGE  = "\033[38;5;208m"
    YELLOW  = "\033[38;5;228m"
    GREEN   = "\033[38;5;48m"
    CYAN    = "\033[38;5;87m"
    PURPLE  = "\033[38;5;141m"
    WHITE   = "\033[38;5;255m"
    GRAY    = "\033[38;5;242m"
    BG_DARK = "\033[48;5;233m"
    LIME    = "\033[38;5;118m"
    PINK    = "\033[38;5;205m"


def bar(value: float, width: int = 20, color: str = C.CYAN) -> str:
    filled = int(value * width)
    empty = width - filled
    return f"{color}{BAR_FULL * filled}{C.GRAY}{BAR_LOW * empty}{C.RESET}"


def hr(width: int = 60):
    print(f"  {C.GRAY}{'\u2500' * width}{C.RESET}")


def section_header(title: str, subtitle: str = ""):
    print()
    print()
    hr(60)
    print(f"  {C.RED}{C.BOLD}{TORII}  {title}  {TORII}{C.RESET}")
    if subtitle:
        print(f"  {C.GRAY}{subtitle}{C.RESET}")
    hr(60)
    print()


def pause():
    input(f"  {C.DIM}{C.GRAY}[ Press Enter to continue ]{C.RESET}")


def wrap_print(text: str, indent: str = "  ", width: int = 76):
    for line in textwrap.wrap(text, width=width):
        print(f"{indent}{line}")


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ssh_query(sql: str) -> str:
    """Run a sqlite3 query on Mac Mini via SSH. Returns stdout or raises."""
    cmd = ["ssh", "-o", "ConnectTimeout=5", CW_HOST,
           f"sqlite3 -json {CW_DB} \"{sql}\""]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def ssh_query_rows(sql: str) -> list[dict]:
    raw = ssh_query(sql)
    if not raw:
        return []
    return json.loads(raw)


# ========================================================================
#  SECTION 1: THE SYSTEM
# ========================================================================

def section_system():
    section_header("THE SYSTEM", "What ran today. What demanded attention.")

    conn = db_connect()

    total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_scored = conn.execute("SELECT COUNT(*) FROM items WHERE llm_score IS NOT NULL").fetchone()[0]
    total_red = conn.execute("SELECT COUNT(*) FROM items WHERE tier = 'RED'").fetchone()[0]
    total_orange = conn.execute("SELECT COUNT(*) FROM items WHERE tier = 'ORANGE'").fetchone()[0]
    total_feeds = conn.execute("SELECT COUNT(*) FROM feed_health").fetchone()[0]
    total_digests = conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0]

    cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = conn.execute("SELECT COUNT(*) FROM items WHERE first_seen > ?", (cutoff_24h,)).fetchone()[0]

    signal_rate = (total_red + total_orange) / total_scored if total_scored > 0 else 0

    print(f"  {C.CYAN}Total items tracked    {C.WHITE}{total_items:,}{C.RESET}")
    print(f"  {C.CYAN}LLM-scored             {C.WHITE}{total_scored:,}{C.RESET}")
    print(f"  {C.CYAN}Sources active          {C.WHITE}{total_feeds}{C.RESET}")
    print(f"  {C.CYAN}Sweep count            {C.WHITE}{total_digests}{C.RESET}")
    print(f"  {C.CYAN}Last 24h               {C.WHITE}{recent}{C.RESET}")
    print(f"  {C.CYAN}Signal rate (RED+ORG)  {C.WHITE}{signal_rate:.1%}{C.RESET}")
    print(f"  {C.CYAN}Schedule               {C.WHITE}3x daily (07:00, 13:00, 19:00){C.RESET}")
    print()

    # Last 3 RED signals
    reds = conn.execute("""
        SELECT title, source, domain, llm_score, llm_reason, first_seen
        FROM items WHERE tier = 'RED'
        ORDER BY first_seen DESC LIMIT 3
    """).fetchall()

    if reds:
        print(f"  {C.RED}{C.BOLD}LAST RED SIGNALS{C.RESET}")
        print()
        for r in reds:
            ts = r["first_seen"][:16] if r["first_seen"] else "?"
            print(f"  {C.RED}{LIVE} [{r['llm_score']}] {C.WHITE}{r['title'][:70]}{C.RESET}")
            print(f"    {C.GRAY}{r['source']} {DOT} {r['domain']} {DOT} {ts}{C.RESET}")
            if r["llm_reason"]:
                reason = r["llm_reason"][:120]
                print(f"    {C.ORANGE}{reason}{C.RESET}")
            print()
    else:
        print(f"  {C.GRAY}No RED signals recorded yet.{C.RESET}")
        print()

    conn.close()

    wrap_print(
        f"{C.GRAY}This runs 3x daily. 7 source types: arXiv, Hacker News, RSS, Reddit, "
        f"SerpAPI, Bluesky, competitor monitors. Every item LLM-scored by Claude Haiku. "
        f"Here's what demanded attention.{C.RESET}"
    )
    print()


# ========================================================================
#  SECTION 2: THE PORTFOLIO
# ========================================================================

def section_portfolio():
    section_header("THE PORTFOLIO", "Sources as assets. Ranked by signal quality.")

    conn = db_connect()
    rows = conn.execute("""
        SELECT source, total_scored, scored_3plus, scored_4plus,
               CASE WHEN total_scored > 0 THEN CAST(scored_3plus AS REAL) / total_scored ELSE 0 END as signal_rate
        FROM source_quality
        ORDER BY signal_rate DESC
    """).fetchall()
    conn.close()

    if not rows:
        print(f"  {C.GRAY}No scoring data yet.{C.RESET}")
        print()
        return

    alpha = [r for r in rows if r["signal_rate"] > 0.40]
    reliable = [r for r in rows if 0.15 <= r["signal_rate"] <= 0.40]
    noisy = [r for r in rows if r["signal_rate"] < 0.15]

    def print_tier(label: str, color: str, tier_rows):
        if not tier_rows:
            return
        print(f"  {color}{C.BOLD}{label}{C.RESET}")
        print()
        for r in tier_rows:
            name = r["source"][:30].ljust(30)
            rate = r["signal_rate"]
            total = r["total_scored"]
            s3 = r["scored_3plus"]
            print(
                f"  {color}{name}{C.RESET} "
                f"{bar(rate, 20, color)} "
                f"{color}{rate:5.0%}{C.RESET} "
                f"{C.GRAY}({s3}/{total}){C.RESET}"
            )
        print()

    print_tier("ALPHA (>40% signal)", C.GREEN, alpha)
    print_tier("RELIABLE (15-40%)", C.YELLOW, reliable)
    print_tier("NOISY (<15%)", C.ORANGE, noisy)

    wrap_print(
        f"{C.GRAY}I treat sources like portfolio assets. Weight by signal quality. "
        f"Rebalance when they degrade. A source that drops below 10% gets cut. "
        f"A source consistently above 40% gets more queries allocated.{C.RESET}"
    )
    print()


# ========================================================================
#  SECTION 3: THE CHINA DESK
# ========================================================================

def section_china_desk():
    section_header("THE CHINA DESK", "Contraband Wu: Chinese consumer intelligence.")

    try:
        # Basic stats
        stats_sql = (
            "SELECT "
            "(SELECT COUNT(*) FROM raw_posts) as total_posts, "
            "(SELECT COUNT(DISTINCT platform) FROM raw_posts) as platforms, "
            "(SELECT COUNT(*) FROM entities) as total_entities, "
            "(SELECT COUNT(*) FROM analyses) as total_analyzed, "
            "(SELECT MIN(scraped_at) FROM raw_posts) as earliest, "
            "(SELECT MAX(scraped_at) FROM raw_posts) as latest"
        )
        stats = ssh_query_rows(stats_sql)
        if not stats:
            raise RuntimeError("No data returned")
        s = stats[0]

        print(f"  {C.PINK}{C.BOLD}CORPUS STATS{C.RESET}")
        print()
        print(f"  {C.CYAN}Total posts            {C.WHITE}{int(s['total_posts']):,}{C.RESET}")
        print(f"  {C.CYAN}Posts analyzed          {C.WHITE}{int(s['total_analyzed']):,}{C.RESET}")
        print(f"  {C.CYAN}Entity extractions     {C.WHITE}{int(s['total_entities']):,}{C.RESET}")
        print(f"  {C.CYAN}Platforms              {C.WHITE}{int(s['platforms'])}{C.RESET}")
        print(f"  {C.CYAN}Date range             {C.WHITE}{s.get('earliest', '?')[:10]} to {s.get('latest', '?')[:10]}{C.RESET}")
        print()

        # Top aesthetic entities with velocity
        print(f"  {C.PINK}{C.BOLD}TOP AESTHETIC ENTITIES (velocity){C.RESET}")
        print()

        # Get last two weeks for velocity comparison
        velocity_sql = (
            "SELECT e.entity, e.entity_en, "
            "COALESCE(curr.mention_count, 0) as this_week, "
            "COALESCE(prev.mention_count, 0) as last_week "
            "FROM (SELECT DISTINCT entity, entity_type FROM entities WHERE entity_type IN ('aesthetic','brand','trend')) e "
            "LEFT JOIN entity_weekly curr ON e.entity = curr.entity "
            "AND curr.week = (SELECT MAX(week) FROM entity_weekly) "
            "LEFT JOIN entity_weekly prev ON e.entity = prev.entity "
            "AND prev.week = (SELECT MAX(week) FROM entity_weekly WHERE week < (SELECT MAX(week) FROM entity_weekly)) "
            "WHERE COALESCE(curr.mention_count, 0) > 0 "
            "ORDER BY this_week DESC LIMIT 5"
        )
        entities = ssh_query_rows(velocity_sql)

        if entities:
            for e in entities:
                this_w = int(e.get("this_week", 0))
                last_w = int(e.get("last_week", 0))
                name = e.get("entity", "?")
                en = e.get("entity_en", "")
                label = f"{name}" + (f" ({en})" if en and en != name else "")
                label = label[:45].ljust(45)

                if last_w > 0:
                    delta = ((this_w - last_w) / last_w) * 100
                    delta_str = f"{C.GREEN}+{delta:.0f}%{C.RESET}" if delta > 0 else f"{C.RED}{delta:.0f}%{C.RESET}"
                else:
                    delta_str = f"{C.LIME}NEW{C.RESET}"

                print(f"  {C.WHITE}{label}{C.RESET} {C.CYAN}{this_w:3d}{C.RESET} this wk  {delta_str}")
        else:
            print(f"  {C.GRAY}No entity velocity data available.{C.RESET}")

        print()

        # Coded language detections
        print(f"  {C.PINK}{C.BOLD}CODED LANGUAGE DETECTIONS{C.RESET}")
        print()

        coded_sql = (
            "SELECT coded_language, COUNT(*) as cnt "
            "FROM analyses WHERE coded_language IS NOT NULL AND coded_language != '' "
            "GROUP BY coded_language ORDER BY cnt DESC LIMIT 5"
        )
        coded = ssh_query_rows(coded_sql)

        if coded:
            for c in coded:
                lang = str(c.get("coded_language", "?"))[:50].ljust(50)
                cnt = int(c.get("cnt", 0))
                print(f"  {C.PURPLE}{lang}{C.RESET} {C.WHITE}{cnt:3d}{C.RESET} posts")
        else:
            print(f"  {C.GRAY}No coded language detections recorded.{C.RESET}")

        print()

        wrap_print(
            f"{C.GRAY}12,000 posts from XHS and Bilibili. Every post analyzed by a "
            f"Chinese-native LLM. 40,000 entity extractions. Aesthetic tags, coded "
            f"language, irony detection, sentiment, trend signals. This is the China "
            f"desk that doesn't exist at any Western firm.{C.RESET}"
        )
        print()

    except Exception as exc:
        print(f"  {C.ORANGE}[SKIPPED] Mac Mini SSH unavailable: {exc}{C.RESET}")
        print(f"  {C.GRAY}The China Desk (Contraband Wu) runs on a dedicated Mac Mini M2.{C.RESET}")
        print(f"  {C.GRAY}12K posts, 40K entities, XHS + Bilibili. Available on next demo.{C.RESET}")
        print()


# ========================================================================
#  SECTION 4: THE API
# ========================================================================

def section_api():
    section_header("THE API", "What you'd hit. JSON, filtered, configurable.")

    # Try to curl the local API
    api_available = False
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "3", "http://localhost:8000/api/digest?limit=3&hours=48"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip().startswith("{"):
            api_available = True
            data = json.loads(result.stdout)
            print(f"  {C.GREEN}{C.BOLD}LIVE API RESPONSE{C.RESET}  {C.GRAY}GET /api/digest?limit=3&hours=48{C.RESET}")
            print()
            pretty = json.dumps(data, indent=2)
            for i, line in enumerate(pretty.split("\n")):
                if i > 30:
                    print(f"  {C.GRAY}  ... ({len(pretty.split(chr(10))) - 30} more lines){C.RESET}")
                    break
                print(f"  {C.CYAN}{line}{C.RESET}")
            print()
    except Exception:
        pass

    if not api_available:
        print(f"  {C.ORANGE}[API server not running]{C.RESET}")
        print(f"  {C.GRAY}Endpoints available when server is up:{C.RESET}")
        print(f"  {C.WHITE}  GET /api/digest          {C.GRAY}-- scored items by tier, domain, source{C.RESET}")
        print(f"  {C.WHITE}  GET /api/sources          {C.GRAY}-- source quality rankings{C.RESET}")
        print(f"  {C.WHITE}  GET /api/health           {C.GRAY}-- feed health & uptime{C.RESET}")
        print(f"  {C.WHITE}  GET /api/trending          {C.GRAY}-- cross-source entity spikes{C.RESET}")
        print()

    # Show config.yaml domain section
    print(f"  {C.BOLD}{C.WHITE}YOUR VERTICAL = 20 LINES OF YAML{C.RESET}")
    print()
    try:
        with open(CONFIG_PATH) as f:
            import yaml
            config = yaml.safe_load(f)
        domains = config.get("domains", {})
        # Show one example domain compactly
        example_domain = "quant_thinking"
        if example_domain in domains:
            d = domains[example_domain]
            keywords = d.get("keywords", [])[:8]
            print(f"  {C.LIME}domains:{C.RESET}")
            print(f"  {C.LIME}  {example_domain}:{C.RESET}")
            print(f"  {C.LIME}    weight: {d.get('weight', 1.0)}{C.RESET}")
            print(f"  {C.LIME}    keywords:{C.RESET}")
            for kw in keywords:
                print(f"  {C.LIME}      - \"{kw}\"{C.RESET}")
            if len(d.get("keywords", [])) > 8:
                print(f"  {C.GRAY}      ... +{len(d['keywords']) - 8} more{C.RESET}")
        print()
        print(f"  {C.GRAY}{len(domains)} domains configured: {', '.join(domains.keys())}{C.RESET}")
    except Exception:
        print(f"  {C.GRAY}(config.yaml not readable){C.RESET}")

    print()
    wrap_print(
        f"{C.GRAY}This is what you'd hit. JSON, filtered by tier, domain, source. "
        f"Configure a new vertical in 5 minutes. Add keywords, point at sources, "
        f"the LLM handles scoring. No training data. No fine-tuning. "
        f"Just domain expertise encoded as YAML.{C.RESET}"
    )
    print()


# ========================================================================
#  SECTION 5: THE ASK
# ========================================================================

def section_ask():
    section_header("THE ASK", "Cultural Intelligence as a Service.")

    tiers = [
        ("SCOUT",    "$99/mo",  "Weekly digest. 3 domains. Email delivery. Signal-ranked."),
        ("ANALYST",  "$299/mo", "Daily digest + custom domain config. API access. Trending alerts. Slack/webhook push."),
        ("DESK",     "$799/mo", "Raw feed API. Unlimited domains. CW China desk included. Webhook firehose. Priority support."),
    ]

    for name, price, desc in tiers:
        if name == "DESK":
            color = C.RED
        elif name == "ANALYST":
            color = C.ORANGE
        else:
            color = C.YELLOW

        print(f"  {color}{C.BOLD}{name:10s}{C.RESET} {C.WHITE}{C.BOLD}{price:10s}{C.RESET}")
        print(f"  {C.GRAY}{desc}{C.RESET}")
        print()

    hr(60)
    print()
    print(f"  {C.WHITE}{C.BOLD}Which of these would you use?{C.RESET}")
    print()
    print(f"  {C.GRAY}7 source types {DOT} LLM scoring {DOT} trending detection {DOT} China desk{C.RESET}")
    print(f"  {C.GRAY}Built by one person. Runs on a MacBook + Mac Mini.{C.RESET}")
    print(f"  {C.GRAY}The three-legged crow guides through noise.{C.RESET}")
    print()


# ========================================================================
#  MAIN
# ========================================================================

def main():
    os.system("clear")

    # Title card
    print()
    print(f"  {C.RED}{C.BOLD}")
    print(f"   {TORII}  YATAGARASU  {TORII}")
    print(f"  {C.RESET}")
    print(f"  {C.GRAY}Cultural Intelligence System{C.RESET}")
    print(f"  {C.GRAY}Live Demo {DOT} {datetime.now().strftime('%B %d, %Y')}{C.RESET}")
    print()
    print(f"  {C.DIM}{C.GRAY}7 source types {DOT} LLM scoring {DOT} 3x daily {DOT} trending detection{C.RESET}")
    print(f"  {C.DIM}{C.GRAY}arXiv {DOT} HN {DOT} RSS {DOT} Reddit {DOT} SerpAPI {DOT} Bluesky {DOT} Competitors{C.RESET}")
    print()

    pause()

    section_system()
    pause()

    section_portfolio()
    pause()

    section_china_desk()
    pause()

    section_api()
    pause()

    section_ask()

    print(f"  {C.GRAY}{'\u2500' * 60}{C.RESET}")
    print(f"  {C.DIM}{C.GRAY}github.com/TheApexWu/yatagarasu{C.RESET}")
    print()


if __name__ == "__main__":
    main()
