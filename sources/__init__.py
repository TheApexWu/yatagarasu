"""Yatagarasu - Source registry.

Each source type is a module with a fetch(source_config, global_config, sweep_type) function.
Adding a new source type:
  1. Create sources/your_source.py with fetch(source_config, global_config, sweep_type) -> list[FeedItem]
  2. Register it here in SOURCE_TYPES
  3. Add config entries under sources[] in config.yaml
"""

from sources import arxiv_feed, hn_feed, rss_feed, serp_feed

# Maps source type names to their fetch modules.
# Each module must implement: fetch(source_config: dict, global_config: dict, sweep_type: str) -> list[FeedItem]
SOURCE_TYPES = {
    "arxiv": arxiv_feed,
    "hackernews": hn_feed,
    "rss": rss_feed,
    "serp": serp_feed,
}
