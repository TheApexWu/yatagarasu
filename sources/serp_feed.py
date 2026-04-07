"""Yatagarasu - SerpAPI web search fetcher. Config-driven queries."""

import json
import os
import urllib.request
import urllib.parse
from models import FeedItem

SERP_API = "https://serpapi.com/search.json"


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Search the web via SerpAPI.

    source_config fields:
        sweep: str ("full" = only run on full sweeps)
        queries: list[{query: str, domain: str}]
        results_per_query: int (default 5)
    """
    if sweep_type == "light" and source_config.get("sweep", "full") == "full":
        return []

    api_key = os.environ.get("SERP_API_KEY", "")
    if not api_key:
        print("[serp] SERP_API_KEY not set, skipping web search")
        return []

    items = []
    seen_urls = set()
    queries = source_config.get("queries", [])
    results_per = source_config.get("results_per_query", 5)
    skip_domains = global_config.get("noise_filters", {}).get("skip_domains", [])

    for q_cfg in queries:
        query = q_cfg.get("query", "")
        domain = q_cfg.get("domain", "ai_research")
        if not query:
            continue

        try:
            params = urllib.parse.urlencode({
                "q": query,
                "api_key": api_key,
                "engine": "google",
                "num": results_per,
                "tbm": "nws",
            })
            url = f"{SERP_API}?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "Yatagarasu/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())

            for result in data.get("news_results", []) + data.get("organic_results", []):
                link = result.get("link", "")
                if link in seen_urls:
                    continue
                seen_urls.add(link)

                if any(sd in link for sd in skip_domains):
                    continue

                items.append(FeedItem(
                    title=result.get("title", ""),
                    url=link,
                    summary=result.get("snippet", "")[:400],
                    source="serp",
                    domain=domain,
                    published=result.get("date", ""),
                ))
        except Exception as e:
            print(f"[serp] query '{query}' error: {e}")

    return items
