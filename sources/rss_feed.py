"""Yatagarasu - RSS/Atom source fetcher with feed health tracking."""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from models import FeedItem
import state

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_rss(xml_bytes: bytes, feed_name: str, domain: str) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom feed."""
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    # RSS 2.0
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        desc = item.findtext("description", "").strip()
        pub = item.findtext("pubDate", "").strip()
        if not title:
            continue
        items.append(FeedItem(
            title=title,
            url=link,
            summary=_strip_html(desc)[:400],
            source=f"rss:{feed_name}",
            domain=domain,
            published=_parse_date(pub),
        ))

    # Atom
    for entry in root.findall("atom:entry", ATOM_NS):
        title_el = entry.find("atom:title", ATOM_NS)
        link_el = entry.find("atom:link", ATOM_NS)
        summary_el = entry.find("atom:summary", ATOM_NS) or entry.find("atom:content", ATOM_NS)
        pub_el = entry.find("atom:published", ATOM_NS) or entry.find("atom:updated", ATOM_NS)

        title = (title_el.text or "").strip() if title_el is not None else ""
        link = (link_el.get("href", "") if link_el is not None else "").strip()
        summary = (summary_el.text or "").strip() if summary_el is not None else ""
        pub = (pub_el.text or "").strip() if pub_el is not None else ""

        if not title:
            continue
        items.append(FeedItem(
            title=title,
            url=link,
            summary=_strip_html(summary)[:400],
            source=f"rss:{feed_name}",
            domain=domain,
            published=_parse_date(pub),
        ))

    return items


def _strip_html(text: str) -> str:
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    return " ".join(clean.split())


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    if "T" in date_str:
        return date_str[:10]
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10]


def fetch(source_config: dict, global_config: dict, sweep_type: str = "full") -> list[FeedItem]:
    """Fetch from all configured RSS feeds with health tracking.

    source_config fields:
        feeds: list[{name: str, url: str, domain: str, reliability: float}]
    """
    feeds = source_config.get("feeds", [])
    all_items = []

    for feed_cfg in feeds:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        domain = feed_cfg.get("domain", "ai_research")
        feed_id = f"rss:{name}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Yatagarasu/1.0",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()

            items = _parse_rss(data, name, domain)
            all_items.extend(items)
            state.record_fetch_success(feed_id, url, len(items))

        except urllib.error.HTTPError as e:
            print(f"[rss] {name} HTTP {e.code}: {e.reason}")
            state.record_fetch_failure(feed_id, url, e.code, str(e.reason))
        except Exception as e:
            print(f"[rss] {name} fetch error: {e}")
            state.record_fetch_failure(feed_id, url, 0, str(e))

    return all_items
