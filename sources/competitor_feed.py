"""Yatagarasu - Competitor page monitor.

Fetches competitor URLs, extracts title + meta description + relevant text.
Dedup handled by the global state layer (content hash changes trigger new items).
"""

import re
import hashlib
import urllib.request
import urllib.error
from datetime import datetime
from models import FeedItem
import state


def _extract_meta(html: str) -> dict:
    """Pull title and meta description from HTML."""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        title = m.group(1).strip()

    desc = ""
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
            html, re.IGNORECASE | re.DOTALL,
        )
    if m:
        desc = m.group(1).strip()

    return {"title": title, "description": desc}


def _extract_update_text(html: str) -> str:
    """Extract text near keywords like update, changelog, new, launch, announce."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())

    keywords = r"(?:update|changelog|new feature|launch|announce|release|upgrade|pricing|beta)"
    snippets = []
    for m in re.finditer(keywords, text, re.IGNORECASE):
        start = max(0, m.start() - 120)
        end = min(len(text), m.end() + 120)
        snippets.append(text[start:end].strip())
        if len(snippets) >= 5:
            break

    return " ... ".join(snippets)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _fetch_page(url: str) -> str | None:
    """Fetch a URL and return the HTML body, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Yatagarasu/1.0 (signal monitor)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"[competitor] {url} HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"[competitor] {url} fetch error: {e}")
        return None


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch competitor pages and create FeedItems from changes.

    source_config fields:
        targets: list[{name: str, urls: list[str], domain: str}]
    """
    if sweep_type != "full" and source_config.get("sweep") == "full":
        return []

    targets = source_config.get("targets", [])
    items = []

    for target in targets:
        name = target["name"]
        domain = target.get("domain", "jp_fashion_market")
        feed_id = f"competitor:{name}"

        for url in target.get("urls", []):
            html = _fetch_page(url)
            if html is None:
                state.record_fetch_failure(feed_id, url, 0, "fetch failed")
                continue

            meta = _extract_meta(html)
            update_text = _extract_update_text(html)
            page_title = meta["title"] or name
            page_desc = meta["description"] or ""

            summary_parts = []
            if page_desc:
                summary_parts.append(page_desc)
            if update_text:
                summary_parts.append(update_text)
            summary = " | ".join(summary_parts)[:600] if summary_parts else f"Page snapshot for {name}"

            # Use content hash so dedup catches unchanged pages
            content_key = _content_hash(f"{page_title}{summary}")
            item_id = hashlib.sha256(f"{url}:{content_key}".encode()).hexdigest()[:16]

            items.append(FeedItem(
                title=f"[{name}] {page_title}",
                url=url,
                summary=summary,
                source=f"competitor:{name}",
                domain=domain,
                published=datetime.now().strftime("%Y-%m-%d"),
                item_id=item_id,
            ))

            state.record_fetch_success(feed_id, url, 1)

    return items
