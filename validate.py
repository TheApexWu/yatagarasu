"""Yatagarasu - Extraction validation and quality checks.

Validates items post-fetch, tracks extraction quality per source.
Surfaces degradation so extraction doesn't fail silently.
"""

from models import FeedItem


def validate_items(items: list[FeedItem], source_name: str) -> tuple[list[FeedItem], dict]:
    """Validate extracted items. Returns (valid_items, quality_report).

    Quality report tracks what went wrong so sources can self-diagnose.
    """
    valid = []
    report = {
        "source": source_name,
        "total": len(items),
        "valid": 0,
        "empty_title": 0,
        "empty_url": 0,
        "empty_summary": 0,
        "malformed_url": 0,
        "duplicate_in_batch": 0,
    }

    seen_ids = set()
    for item in items:
        # hard fails: skip item entirely
        if not item.title or not item.title.strip():
            report["empty_title"] += 1
            continue
        if not item.url or not item.url.strip():
            report["empty_url"] += 1
            continue
        if not item.url.startswith("http"):
            report["malformed_url"] += 1
            continue
        if item.item_id in seen_ids:
            report["duplicate_in_batch"] += 1
            continue

        # soft issues: keep item but track
        if not item.summary or not item.summary.strip():
            report["empty_summary"] += 1
            # still valid, just lacks summary

        seen_ids.add(item.item_id)
        valid.append(item)

    report["valid"] = len(valid)
    return valid, report


def assess_quality(report: dict) -> str | None:
    """Return a warning string if extraction quality is degraded, else None."""
    total = report["total"]
    if total == 0:
        return f"[{report['source']}] returned 0 items"

    valid_rate = report["valid"] / total
    if valid_rate < 0.5:
        return f"[{report['source']}] {report['valid']}/{total} items valid ({valid_rate:.0%})"

    issues = []
    if report["empty_summary"] > total * 0.3:
        issues.append(f"{report['empty_summary']} missing summaries")
    if report["malformed_url"] > 0:
        issues.append(f"{report['malformed_url']} malformed URLs")

    if issues:
        return f"[{report['source']}] quality issues: {', '.join(issues)}"
    return None
