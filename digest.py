"""Yatagarasu - Digest renderer with health alerts and source quality."""

import os
from datetime import datetime
from pathlib import Path
from models import FeedItem
import state


def render(scored_items: list[tuple[FeedItem, int, str, str]], config: dict, sweep_type: str,
           quality_warnings: list[str] = None) -> str:
    """Render scored items into a markdown digest."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    sweep_label = {"full": "Morning", "light": "Midday/Evening"}.get(sweep_type, sweep_type)

    lines = [f"# Yatagarasu | {date_str} {sweep_label} ({time_str})", ""]

    # Feed health alerts
    sick = state.get_sick_feeds(failure_threshold=3)
    if sick:
        lines.append("## FEED HEALTH")
        for feed in sick:
            lines.append(f"- **{feed['feed_id']}** -- {feed['consecutive_failures']} consecutive failures. "
                         f"Last error: {feed.get('last_error', 'unknown')} "
                         f"(HTTP {feed.get('last_status_code', '?')})")
        lines.append("")

    # Quality warnings from extraction validation
    if quality_warnings:
        lines.append("## EXTRACTION QUALITY")
        for w in quality_warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Group by tier
    tiers = {"RED": [], "ORANGE": [], "YELLOW": []}
    min_score = config.get("scoring", {}).get("min_score", 3)
    tier_budgets = config.get("scoring", {}).get("tier_budgets", {})

    for item, score, tier, reason in scored_items:
        if score >= min_score and tier in tiers:
            tiers[tier].append((item, score, reason))

    # Apply tier budgets
    for tier_name, budget in tier_budgets.items():
        if tier_name in tiers and len(tiers[tier_name]) > budget:
            tiers[tier_name] = tiers[tier_name][:budget]

    tier_labels = {
        "RED": "RED (act on this)",
        "ORANGE": "ORANGE (shapes your model)",
        "YELLOW": "YELLOW (context)",
    }

    total = sum(len(v) for v in tiers.values())
    if total == 0:
        lines.append("*Nothing above noise threshold. Clean day.*")
        lines.append("")
    else:
        for tier_name in ["RED", "ORANGE", "YELLOW"]:
            items_in_tier = tiers[tier_name]
            if not items_in_tier:
                continue

            lines.append(f"## {tier_labels[tier_name]}")
            lines.append("")

            for item, score, reason in items_in_tier:
                source_tag = f"`{item.source}`"
                domain_tag = f"`{item.domain}`"
                lines.append(f"- **[{item.title}]({item.url})** {source_tag} {domain_tag}")
                if reason:
                    lines.append(f"  {reason}")
                lines.append("")

    # Stats
    lines.append("---")
    lines.append(f"*{total} items surfaced from {sweep_type} sweep. "
                 f"RED: {len(tiers['RED'])}, ORANGE: {len(tiers['ORANGE'])}, YELLOW: {len(tiers['YELLOW'])}*")
    lines.append("")

    # Source quality footer
    sq = state.get_source_quality()
    if sq:
        lines.append("### Source Signal Rates")
        for s in sq:
            if s["total_scored"] >= 5:  # only show after enough data
                lines.append(f"- `{s['source']}` signal: {s['signal_rate']:.0%} "
                             f"({s['scored_3plus']}/{s['total_scored']})")
        lines.append("")

    # Orient prompt
    orient = config.get("orient_prompt", "")
    if orient:
        lines.append(orient)

    return "\n".join(lines)


def write_digest(content: str, config: dict) -> str:
    """Write digest to configured output directory."""
    digest_dir = config.get("output", {}).get("digest_dir", "./digests")
    digest_dir = os.path.expanduser(digest_dir)
    os.makedirs(digest_dir, exist_ok=True)

    now = datetime.now()
    filename = f"{now.strftime('%Y-%m-%d_%H%M')}.md"
    filepath = os.path.join(digest_dir, filename)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"[digest] written to {filepath}")
    return filepath
