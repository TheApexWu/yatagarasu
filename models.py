"""Yatagarasu - Core data models."""

import hashlib
from dataclasses import dataclass, field


@dataclass
class FeedItem:
    title: str
    url: str
    summary: str
    source: str          # e.g. "arxiv", "hackernews", "rss:Simon Willison", "serp"
    domain: str          # e.g. "ai_research", "fashion_cw", "startup_vc"
    published: str       # YYYY-MM-DD or empty
    raw_score: float = 0.0
    item_id: str = field(default="", repr=False)

    def __post_init__(self):
        if not self.item_id:
            self.item_id = self._compute_id()

    def _compute_id(self) -> str:
        key = self.url.strip().lower().rstrip("/")
        return hashlib.sha256(key.encode()).hexdigest()[:16]
