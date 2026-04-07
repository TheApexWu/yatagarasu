"""Yatagarasu - Hacker News source fetcher via Algolia + Firebase APIs."""

import json
import urllib.request
import urllib.parse
from models import FeedItem

ALGOLIA_API = "https://hn.algolia.com/api/v1"


def _search_hn(query: str, tags: str = "story", hits: int = 20) -> list[dict]:
    params = f"query={urllib.parse.quote(query)}&tags={tags}&hitsPerPage={hits}"
    url = f"{ALGOLIA_API}/search?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Yatagarasu/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("hits", [])
    except Exception as e:
        print(f"[hn] search error for '{query}': {e}")
        return []


def _fetch_top(n: int = 100) -> list[dict]:
    try:
        req = urllib.request.Request(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers={"User-Agent": "Yatagarasu/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            ids = json.loads(resp.read())[:n]

        items = []
        for story_id in ids[:50]:
            try:
                item_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                req2 = urllib.request.Request(item_url, headers={"User-Agent": "Yatagarasu/1.0"})
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    item = json.loads(resp2.read())
                if item and item.get("type") == "story":
                    items.append(item)
            except Exception:
                continue
        return items
    except Exception as e:
        print(f"[hn] top stories error: {e}")
        return []


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch HN stories.

    source_config fields:
        min_points: int (default 50)
        top_n: int (default 100, halved for light sweeps)
        search_terms: list[{query: str, domain: str}] (config-driven, replaces hardcoded)
    """
    items = []
    seen_urls = set()

    min_points = source_config.get("min_points", 50)
    top_n = source_config.get("top_n", 100)
    search_terms = source_config.get("search_terms", [])

    # keyword search (full sweep only)
    if sweep_type == "full" and search_terms:
        for term_cfg in search_terms:
            query = term_cfg.get("query", "")
            domain = term_cfg.get("domain", "ai_research")
            if not query:
                continue

            hits = _search_hn(query, hits=10)
            for hit in hits:
                url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                points = hit.get("points", 0) or 0
                if points < min_points:
                    continue

                items.append(FeedItem(
                    title=hit.get("title", ""),
                    url=url,
                    summary=f"{points} points, {hit.get('num_comments', 0)} comments on HN",
                    source="hackernews",
                    domain=domain,
                    published=hit.get("created_at", "")[:10],
                ))

    # top stories filtered by domain keywords
    n = top_n if sweep_type == "full" else top_n // 2
    top = _fetch_top(n=n)

    all_keywords_flat = []
    for domain_cfg in global_config.get("domains", {}).values():
        all_keywords_flat.extend(kw.lower() for kw in domain_cfg.get("keywords", []))

    for story in top:
        title = story.get("title", "")
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id', '')}"
        if url in seen_urls:
            continue

        points = story.get("score", 0)
        if points < min_points:
            continue

        title_lower = title.lower()
        if any(kw in title_lower for kw in all_keywords_flat):
            seen_urls.add(url)
            items.append(FeedItem(
                title=title,
                url=url,
                summary=f"{points} points on HN",
                source="hackernews",
                domain="ai_research",
                published="",
            ))

    return items
