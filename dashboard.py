#!/usr/bin/env python3
"""
Yatagarasu Dashboard -- Terminal signal audit display.
Shinto shrine aesthetic meets Y2K terminal noir.

Usage:
    python dashboard.py              # full dashboard
    python dashboard.py --compact    # one-screen summary
"""

import argparse
import os
import sys
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state


# ---- GLYPHS ----
TORII = "⛩"
CROW = "八咫烏"
BAR_FULL = "█"
BAR_MED = "▓"
BAR_LOW = "░"
DEAD = "✖"
LIVE = "●"
WARN = "▲"
DOT = "·"

# ANSI colors -- Y2K terminal palette
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
    # Y2K accent
    LIME    = "\033[38;5;118m"
    PINK    = "\033[38;5;205m"


def bar(value: float, width: int = 20, color: str = C.CYAN) -> str:
    """Render a horizontal bar."""
    filled = int(value * width)
    empty = width - filled
    return f"{color}{BAR_FULL * filled}{C.GRAY}{BAR_LOW * empty}{C.RESET}"


def signal_color(rate: float) -> str:
    if rate >= 0.3:
        return C.GREEN
    elif rate >= 0.15:
        return C.YELLOW
    elif rate > 0:
        return C.ORANGE
    return C.RED


def header():
    now = datetime.now()
    lines = [
        "",
        f"  {C.RED}{C.BOLD}{TORII}  YATAGARASU  {TORII}{C.RESET}",
        f"  {C.GRAY}{CROW} {DOT} signal audit {DOT} {now.strftime('%Y-%m-%d %H:%M')}{C.RESET}",
        f"  {C.GRAY}{'─' * 50}{C.RESET}",
        "",
    ]
    return "\n".join(lines)


def feed_health_panel() -> str:
    health = state.get_feed_health()
    if not health:
        return f"  {C.GRAY}no feed data yet. run a sweep first.{C.RESET}\n"

    lines = [f"  {C.BOLD}{C.WHITE}FEED HEALTH{C.RESET}", ""]

    for h in health:
        name = h["feed_id"][:35].ljust(35)
        fetches = h["total_fetches"]
        items = h["total_items"]
        fails = h["consecutive_failures"]

        if fails >= 3:
            icon = f"{C.RED}{DEAD}"
            status = f"DEAD ({fails}x fail)"
            color = C.RED
        elif fails > 0:
            icon = f"{C.ORANGE}{WARN}"
            status = f"WARN ({fails}x)"
            color = C.ORANGE
        else:
            icon = f"{C.GREEN}{LIVE}"
            status = "LIVE"
            color = C.GREEN

        avg = items / fetches if fetches > 0 else 0
        lines.append(
            f"  {icon} {color}{name}{C.RESET} "
            f"{C.GRAY}{status:15s} "
            f"{fetches:3d} fetches {DOT} {items:4d} items {DOT} ~{avg:.0f}/run{C.RESET}"
        )

        if fails >= 3 and h.get("last_error"):
            lines.append(f"      {C.RED}{C.DIM}└ {h['last_error'][:60]}{C.RESET}")

    lines.append("")
    return "\n".join(lines)


def source_quality_panel() -> str:
    quality = state.get_source_quality()
    if not quality:
        return f"  {C.GRAY}no scoring data yet.{C.RESET}\n"

    lines = [f"  {C.BOLD}{C.WHITE}SOURCE SIGNAL RATES{C.RESET}", ""]

    for q in quality:
        name = q["source"][:30].ljust(30)
        total = q["total_scored"]
        s3 = q["scored_3plus"]
        s4 = q["scored_4plus"]
        rate = q["signal_rate"] if total > 0 else 0
        premium = q["premium_rate"] if total > 0 else 0

        sc = signal_color(rate)
        rate_str = f"{rate:5.0%}" if total > 0 else "  n/a"

        lines.append(
            f"  {sc}{name}{C.RESET} "
            f"{bar(rate, 20, sc)} "
            f"{sc}{rate_str}{C.RESET} "
            f"{C.GRAY}({s3}/{total}){C.RESET}"
        )

        if premium > 0:
            lines.append(
                f"  {' ' * 30} "
                f"{C.PURPLE}premium: {premium:.0%} ({s4} items scored 4+){C.RESET}"
            )

    lines.append("")
    return "\n".join(lines)


def digest_history_panel() -> str:
    conn = state._connect()
    rows = conn.execute("""
        SELECT timestamp, sweep_type, items_fetched, items_surfaced,
               red_count, orange_count, yellow_count
        FROM digests ORDER BY id DESC LIMIT 10
    """).fetchall()
    conn.close()

    if not rows:
        return f"  {C.GRAY}no digests yet.{C.RESET}\n"

    lines = [f"  {C.BOLD}{C.WHITE}RECENT DIGESTS{C.RESET}", ""]

    for r in rows:
        ts = r["timestamp"][:16]
        sweep = r["sweep_type"]
        fetched = r["items_fetched"] or 0
        surfaced = r["items_surfaced"] or 0
        red = r["red_count"] or 0
        orange = r["orange_count"] or 0
        yellow = r["yellow_count"] or 0

        sweep_tag = f"{C.LIME}full{C.RESET}" if sweep == "full" else f"{C.GRAY}lite{C.RESET}"

        red_str = f"{C.RED}{red}R{C.RESET}" if red > 0 else f"{C.GRAY}0R{C.RESET}"
        org_str = f"{C.ORANGE}{orange}O{C.RESET}" if orange > 0 else f"{C.GRAY}0O{C.RESET}"
        yel_str = f"{C.YELLOW}{yellow}Y{C.RESET}" if yellow > 0 else f"{C.GRAY}0Y{C.RESET}"

        noise_rate = 1 - (surfaced / fetched) if fetched > 0 else 0

        lines.append(
            f"  {C.GRAY}{ts}{C.RESET} "
            f"[{sweep_tag}] "
            f"{C.WHITE}{fetched:3d}{C.RESET} fetched {C.GRAY}>{C.RESET} "
            f"{red_str} {org_str} {yel_str}  "
            f"{C.GRAY}{noise_rate:.0%} noise killed{C.RESET}"
        )

    lines.append("")
    return "\n".join(lines)


def stats_panel() -> str:
    conn = state._connect()

    total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    total_digests = conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0]
    total_red = conn.execute("SELECT COUNT(*) FROM items WHERE tier = 'RED'").fetchone()[0]
    total_orange = conn.execute("SELECT COUNT(*) FROM items WHERE tier = 'ORANGE'").fetchone()[0]

    # items in last 24h
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    recent = conn.execute("SELECT COUNT(*) FROM items WHERE first_seen > ?", (cutoff,)).fetchone()[0]

    conn.close()

    lines = [
        f"  {C.BOLD}{C.WHITE}LIFETIME{C.RESET}",
        "",
        f"  {C.CYAN}items seen     {C.WHITE}{total_items:,}{C.RESET}",
        f"  {C.CYAN}digests        {C.WHITE}{total_digests}{C.RESET}",
        f"  {C.RED}RED caught     {C.WHITE}{total_red}{C.RESET}",
        f"  {C.ORANGE}ORANGE caught  {C.WHITE}{total_orange}{C.RESET}",
        f"  {C.CYAN}last 24h       {C.WHITE}{recent}{C.RESET}",
        "",
    ]
    return "\n".join(lines)


def footer() -> str:
    return (
        f"  {C.GRAY}{'─' * 50}{C.RESET}\n"
        f"  {C.DIM}{C.GRAY}yatagarasu {DOT} github.com/TheApexWu/yatagarasu{C.RESET}\n"
        f"  {C.DIM}{C.GRAY}the three-legged crow guides through noise{C.RESET}\n"
    )


def render_dashboard(compact: bool = False):
    state.init_db()
    print(header())
    print(feed_health_panel())
    print(source_quality_panel())
    if not compact:
        print(digest_history_panel())
        print(stats_panel())
    print(footer())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yatagarasu dashboard")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    render_dashboard(compact=args.compact)
