"""Yatagarasu - Push notifications for high-tier items."""

import subprocess
import urllib.request
import urllib.error
from models import FeedItem

TIER_ORDER = {"RED": 0, "ORANGE": 1, "YELLOW": 2}
NTFY_PRIORITY = {"RED": "urgent", "ORANGE": "default", "YELLOW": "low"}


def _passes_min_tier(item_tier: str, min_tier: str) -> bool:
    """Check if item_tier meets or exceeds min_tier threshold."""
    return TIER_ORDER.get(item_tier, 99) <= TIER_ORDER.get(min_tier, 99)


def _send_ntfy(item: FeedItem, tier: str, reason: str, backend_cfg: dict) -> bool:
    """Send notification via ntfy.sh. Returns True on success."""
    topic = backend_cfg.get("topic", "yatagarasu")
    url = f"https://ntfy.sh/{topic}"

    body = f"[{tier}] {item.title}\n{item.source} | {item.domain}"
    if reason:
        body += f"\n{reason}"

    headers = {
        "Title": f"Yatagarasu {tier}",
        "Priority": NTFY_PRIORITY.get(tier, "default"),
        "Tags": tier.lower(),
    }
    if item.url:
        headers["Click"] = item.url

    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10):
            return True
    except (urllib.error.URLError, OSError) as e:
        print(f"[notify] ntfy failed: {e}")
        return False


def _send_macos(item: FeedItem, tier: str, reason: str, _backend_cfg: dict) -> bool:
    """Send macOS native notification via osascript. Returns True on success."""
    title = f"Yatagarasu [{tier}]"
    # Escape double quotes for osascript
    msg = item.title.replace('"', '\\"')
    subtitle = f"{item.source} | {item.domain}".replace('"', '\\"')

    script = f'display notification "{msg}" with title "{title}" subtitle "{subtitle}"'
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5, check=True)
        return True
    except (subprocess.SubprocessError, OSError) as e:
        print(f"[notify] macos failed: {e}")
        return False


BACKENDS = {
    "ntfy": _send_ntfy,
    "macos": _send_macos,
}


def notify(scored_items: list[tuple[FeedItem, int, str, str]], config: dict) -> int:
    """Send notifications for high-tier items. Returns count sent."""
    notif_cfg = config.get("notifications", {})
    if not notif_cfg.get("enabled", False):
        return 0

    backends = notif_cfg.get("backends", [])
    if not backends:
        return 0

    min_score = config.get("scoring", {}).get("min_score", 3)
    max_per_sweep = notif_cfg.get("max_per_sweep", 10)
    sent = 0

    for item, score, tier, reason in scored_items:
        if sent >= max_per_sweep:
            break
        if score < min_score:
            continue
        if tier not in TIER_ORDER:
            continue

        for backend_cfg in backends:
            backend_type = backend_cfg.get("type", "")
            send_fn = BACKENDS.get(backend_type)
            if not send_fn:
                continue

            min_tier = backend_cfg.get("min_tier", "RED")
            if not _passes_min_tier(tier, min_tier):
                continue

            if send_fn(item, tier, reason, backend_cfg):
                sent += 1

    if sent > 0:
        print(f"[notify] {sent} notifications sent")
    return sent
