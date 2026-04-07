"""Yatagarasu - arxiv source fetcher."""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from models import FeedItem

ARXIV_API = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch recent arxiv papers.

    source_config fields:
        max_results: int (default 50, halved for light sweeps)
        categories: list[str] (arxiv category codes)
        keywords: list[str] (search terms, OR'd together)
        domain: str (domain tag for scored items, default "ai_research")
    """
    if sweep_type == "light":
        max_results = source_config.get("max_results", 50) // 2
    else:
        max_results = source_config.get("max_results", 50)

    keywords = source_config.get("keywords", [])
    categories = source_config.get("categories", ["cs.AI", "cs.CL", "cs.CV", "cs.LG"])
    domain = source_config.get("domain", "ai_research")

    # Fallback: pull keywords from global domain config if not specified per-source
    if not keywords:
        domain_cfg = global_config.get("domains", {}).get(domain, {})
        keywords = domain_cfg.get("keywords", [])
        if not categories:
            categories = domain_cfg.get("arxiv_categories", categories)

    kw_query = " OR ".join(f'all:"{kw}"' for kw in keywords[:10])
    cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
    query = f"({kw_query}) AND ({cat_query})"

    params = urllib.parse.urlencode({
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })

    url = f"{ARXIV_API}?{params}"
    items = []

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Yatagarasu/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        root = ET.fromstring(data)

        for entry in root.findall("atom:entry", NS):
            title = entry.find("atom:title", NS)
            summary = entry.find("atom:summary", NS)
            link = entry.find("atom:id", NS)
            published = entry.find("atom:published", NS)

            if title is None or title.text is None:
                continue

            title_clean = " ".join(title.text.strip().split())
            summary_clean = " ".join((summary.text or "").strip().split())[:500]

            items.append(FeedItem(
                title=title_clean,
                url=(link.text or "").strip(),
                summary=summary_clean,
                source="arxiv",
                domain=domain,
                published=(published.text or "")[:10],
            ))
    except Exception as e:
        print(f"[arxiv] fetch error: {e}")

    return items
