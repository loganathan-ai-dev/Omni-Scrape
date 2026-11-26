"""URL deduplication on canonical URLs (fragments, tracking parameters, trailing slashes ignored)."""

from typing import Set

from omniscrape.crawler.urls import canonicalize


class URLFilter:
    """Filters duplicate URLs to prevent crawl loops."""

    def __init__(self):
        self._seen: Set[str] = set()

    def add(self, url: str) -> bool:
        """Returns True if URL was newly added, False if already seen."""
        key = canonicalize(url)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def __contains__(self, url: str) -> bool:
        return canonicalize(url) in self._seen
