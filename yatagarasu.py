#!/usr/bin/env python3
"""
Yatagarasu - Signal curation system.
The three-legged crow guides through noise.

Usage:
    python yatagarasu.py                  # Full sweep (morning)
    python yatagarasu.py --light          # Light sweep (midday/evening)
    python yatagarasu.py --dry-run        # Fetch + score but don't write digest
    python yatagarasu.py --sources-only   # Fetch only, skip scoring (debug)
    python yatagarasu.py --health         # Show feed health + source quality
"""

import argparse
import os
import re
import sys
import yaml
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import state
from models import FeedItem
from sources import SOURCE_TYPES
from scorer import score_items
from digest import render, write_digest
from validate import validate_items, assess_quality


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    if not os.path.exists(config_path):
        print("[yatagarasu] ERROR: config.yaml not found.")
        print("  Copy config.example.yaml to config.yaml and edit your profile.")
        sys.exit(1)
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[yatagarasu] ERROR: config.yaml is malformed YAML: {e}")
        sys.exit(1)
    # Validate required sections
    missing = [k for k in ("profile", "sources", "domains") if k not in config]
    if missing:
        print(f"[yatagarasu] ERROR: config.yaml missing required sections: {', '.join(missing)}")
        print("  See config.example.yaml for the expected structure.")
        sys.exit(1)
    return config


def dedup_items(items: list[FeedItem]) -> list[FeedItem]:
    """Remove duplicates within a single fetch batch (in-memory)."""
    seen_ids = set()
    deduped = []
    for item in items:
        if item.item_id in seen_ids:
            continue
        seen_ids.add(item.item_id)
        deduped.append(item)
    return deduped


def apply_noise_filters(items: list[FeedItem], config: dict) -> list[FeedItem]:
    """Filter out items matching noise patterns."""
    filters = config.get("noise_filters", {})
    skip_domains = [d.lower() for d in filters.get("skip_domains", [])]
    skip_patterns = filters.get("skip_patterns", [])

    compiled = []
    for pat in skip_patterns:
        try:
            compiled.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            continue

    filtered = []
    for item in items:
        url_lower = item.url.lower()
        if any(sd in url_lower for sd in skip_domains):
            continue
        text = f"{item.title} {item.summary}".lower()
        if any(p.search(text) for p in compiled):
            continue
        filtered.append(item)
    return filtered


def fetch_all_sources(config: dict, sweep_type: str) -> tuple[list[FeedItem], list[str]]:
    """Fetch from all enabled sources. Returns (items, quality_warnings)."""
    all_items = []
    quality_warnings = []
    sources_config = config.get("sources", {})

    for source_type, module in SOURCE_TYPES.items():
        source_cfg = sources_config.get(source_type, {})
        if not source_cfg.get("enabled", True):
            continue

        # skip full-only sources on light sweeps
        if sweep_type == "light" and source_cfg.get("sweep") == "full":
            if source_type == "serp":
                continue

        print(f"[yatagarasu] fetching {source_type}...")
        try:
            raw_items = module.fetch(source_cfg, config, sweep_type)
        except Exception as e:
            print(f"[yatagarasu] {source_type} fetch failed: {e}")
            quality_warnings.append(f"[{source_type}] fetch crashed: {e}")
            continue

        # validate extraction quality
        valid_items, report = validate_items(raw_items, source_type)
        warning = assess_quality(report)
        if warning:
            quality_warnings.append(warning)
            print(f"[yatagarasu] {warning}")

        all_items.extend(valid_items)

    return all_items, quality_warnings


def show_health():
    """Print feed health and source quality reports."""
    state.init_db()

    print("\n=== FEED HEALTH ===")
    health = state.get_feed_health()
    if not health:
        print("No feed health data yet. Run a sweep first.")
    else:
        for h in health:
            status = "OK" if h["consecutive_failures"] == 0 else f"FAILING ({h['consecutive_failures']}x)"
            print(f"  {h['feed_id']:30s} {status:15s} fetches: {h['total_fetches']}, items: {h['total_items']}")
            if h["consecutive_failures"] > 0:
                print(f"    last error: HTTP {h.get('last_status_code', '?')} -- {h.get('last_error', '')}")

    print("\n=== SOURCE QUALITY ===")
    quality = state.get_source_quality()
    if not quality:
        print("No scoring data yet.")
    else:
        for q in quality:
            rate = f"{q['signal_rate']:.0%}" if q['total_scored'] > 0 else "n/a"
            print(f"  {q['source']:30s} signal: {rate} ({q['scored_3plus']}/{q['total_scored']})")

    print()


def run(sweep_type: str = "full", dry_run: bool = False, sources_only: bool = False):
    """Main sweep pipeline."""
    config = load_config()
    state.init_db()

    print(f"[yatagarasu] {sweep_type} sweep starting at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Fetch from all sources (with validation)
    all_items, quality_warnings = fetch_all_sources(config, sweep_type)
    items_fetched = len(all_items)
    print(f"[yatagarasu] raw items: {items_fetched}")

    if items_fetched == 0:
        print("[yatagarasu] WARNING: 0 items fetched from all sources.")
        print("  This usually means a config problem or network issue.")
        print("  Try: python yatagarasu.py --sources-only")
        quality_warnings.append("0 items fetched from all sources -- check config and network.")

    # 2. In-memory dedup (within this batch)
    all_items = dedup_items(all_items)

    # 3. Noise filter
    all_items = apply_noise_filters(all_items, config)
    print(f"[yatagarasu] after dedup + noise filter: {len(all_items)}")

    # 4. Cross-run dedup (SQLite persistent)
    dedup_window = config.get("noise_filters", {}).get("dedup_window_hours", 48)
    all_items = state.filter_seen(all_items, window_hours=dedup_window)
    items_after_dedup = len(all_items)
    print(f"[yatagarasu] after cross-run dedup ({dedup_window}h window): {items_after_dedup}")

    # Record all items as seen
    state.record_items(all_items)

    if sources_only:
        for item in all_items:
            print(f"  [{item.domain}] [{item.source}] {item.title}")
        return

    # 5. Score with LLM
    print("[yatagarasu] scoring...")
    scored = score_items(all_items, config)

    # Record scores in state
    state.update_scores(scored)
    state.update_source_quality(scored)

    # 6. Render digest
    content = render(scored, config, sweep_type, quality_warnings=quality_warnings)

    # Count tiers for metadata
    min_score = config.get("scoring", {}).get("min_score", 3)
    red = sum(1 for _, s, t, _ in scored if s >= min_score and t == "RED")
    orange = sum(1 for _, s, t, _ in scored if s >= min_score and t == "ORANGE")
    yellow = sum(1 for _, s, t, _ in scored if s >= min_score and t == "YELLOW")
    items_surfaced = red + orange + yellow

    if dry_run:
        print("\n--- DRY RUN DIGEST ---")
        print(content)
        print("--- END ---")
        state.record_digest(sweep_type, items_fetched, items_after_dedup,
                           len(scored), items_surfaced, red, orange, yellow, "(dry-run)")
        return

    # 7. Write to output
    filepath = write_digest(content, config)
    state.record_digest(sweep_type, items_fetched, items_after_dedup,
                       len(scored), items_surfaced, red, orange, yellow, filepath)
    print(f"[yatagarasu] done. {filepath}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yatagarasu signal curation")
    parser.add_argument("--light", action="store_true", help="Light sweep (midday/evening)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write digest file")
    parser.add_argument("--sources-only", action="store_true", help="Fetch only, skip scoring")
    parser.add_argument("--health", action="store_true", help="Show feed health + source quality")
    args = parser.parse_args()

    if args.health:
        show_health()
    else:
        sweep = "light" if args.light else "full"
        run(sweep_type=sweep, dry_run=args.dry_run, sources_only=args.sources_only)
