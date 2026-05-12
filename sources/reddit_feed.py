"""Yatagarasu - Reddit source fetcher via JSON API (no auth required)."""

import json
import urllib.request
import urllib.error
from models import FeedItem


REDDIT_BASE = "https://www.reddit.com"


def _fetch_subreddit(name: str, limit: int = 25, sort: str = "hot") -> list[dict]:
    """Fetch posts from a subreddit using Reddit's public JSON API."""
    url = f"{REDDIT_BASE}/r/{name}/{sort}.json?limit={limit}&raw_json=1"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Yatagarasu/1.0 (signal curation; not a bot)",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return [child["data"] for child in data.get("data", {}).get("children", [])
                if child.get("kind") == "t3"]
    except urllib.error.HTTPError as e:
        print(f"[reddit] r/{name} HTTP {e.code}")
        return []
    except Exception as e:
        print(f"[reddit] r/{name} error: {e}")
        return []


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch from configured subreddits.

    source_config fields:
        subreddits: list[{name, domain, min_score, limit, search_terms?}]
    """
    subreddits = source_config.get("subreddits", [])
    items = []
    seen_urls = set()

    for sub_cfg in subreddits:
        name = sub_cfg["name"]
        domain = sub_cfg.get("domain", "jp_fashion_market")
        min_score = sub_cfg.get("min_score", 5)
        limit = sub_cfg.get("limit", 25)
        search_terms = [t.lower() for t in sub_cfg.get("search_terms", [])]

        # light sweeps: halve the limit
        if sweep_type == "light":
            limit = max(limit // 2, 5)

        posts = _fetch_subreddit(name, limit=limit)

        for post in posts:
            score = post.get("score", 0)
            if score < min_score:
                continue

            title = post.get("title", "").strip()
            url = post.get("url", "")
            selftext = post.get("selftext", "")[:400]
            permalink = post.get("permalink", "")

            if not title:
                continue

            # If search_terms specified, filter to posts mentioning them
            if search_terms:
                text_lower = f"{title} {selftext}".lower()
                if not any(term in text_lower for term in search_terms):
                    continue

            # Use permalink as canonical URL for self posts
            if url.startswith("/r/") or "reddit.com" in url:
                url = f"{REDDIT_BASE}{permalink}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            summary = selftext if selftext else f"{score} upvotes on r/{name}"
            num_comments = post.get("num_comments", 0)
            if num_comments > 0:
                summary = f"{score} pts, {num_comments} comments. {summary}"

            items.append(FeedItem(
                title=title,
                url=url,
                summary=summary[:400],
                source=f"reddit:r/{name}",
                domain=domain,
                published="",
            ))

    return items
