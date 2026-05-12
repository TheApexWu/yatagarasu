"""Yatagarasu - Bluesky source fetcher via AT Protocol public API.

Free, no auth required, 3000 req/5min rate limit.
Used as a proxy for Twitter/X signal since many tech/VC people cross-post.
"""

import json
import urllib.request
import urllib.error
from models import FeedItem

BSKY_API = "https://public.api.bsky.app/xrpc"


def _get_author_feed(handle: str, limit: int = 20) -> list[dict]:
    """Fetch recent posts from a Bluesky user."""
    url = f"{BSKY_API}/app.bsky.feed.getAuthorFeed?actor={handle}&limit={limit}&filter=posts_no_replies"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Yatagarasu/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("feed", [])
    except urllib.error.HTTPError as e:
        print(f"[bluesky] {handle} HTTP {e.code}")
        return []
    except Exception as e:
        print(f"[bluesky] {handle} error: {e}")
        return []


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch from configured Bluesky accounts.

    source_config fields:
        accounts: list[{handle: str, domain: str, label: str}]
    """
    accounts = source_config.get("accounts", [])
    items = []
    seen_urls = set()

    for acct in accounts:
        handle = acct["handle"]
        domain = acct.get("domain", "founder_vc")
        label = acct.get("label", handle)
        limit = acct.get("limit", 20)

        if sweep_type == "light":
            limit = max(limit // 2, 5)

        feed = _get_author_feed(handle, limit=limit)

        for entry in feed:
            post = entry.get("post", {})
            record = post.get("record", {})
            text = record.get("text", "").strip()
            if not text:
                continue

            # Build URL from post URI
            uri = post.get("uri", "")
            author_handle = post.get("author", {}).get("handle", handle)
            # URI format: at://did:plc:xxx/app.bsky.feed.post/yyy
            post_id = uri.split("/")[-1] if "/" in uri else ""
            url = f"https://bsky.app/profile/{author_handle}/post/{post_id}" if post_id else ""

            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Use first line as title, rest as summary
            lines = text.split("\n")
            title = lines[0][:200]
            summary = text[:400]

            # Extract any embedded link
            embed = post.get("embed", {})
            external = embed.get("external", {})
            if external:
                ext_title = external.get("title", "")
                ext_url = external.get("uri", "")
                if ext_title:
                    title = f"{label}: {ext_title}"
                    summary = f"{text[:200]} | {external.get('description', '')}"[:400]
                if ext_url and ext_url not in seen_urls:
                    url = ext_url
                    seen_urls.add(ext_url)

            items.append(FeedItem(
                title=title,
                url=url,
                summary=summary,
                source=f"bluesky:{label}",
                domain=domain,
                published=record.get("createdAt", "")[:10],
            ))

    return items
