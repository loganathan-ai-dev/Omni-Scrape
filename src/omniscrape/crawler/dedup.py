"""URL deduplication using exact set and bloom filter."""

from typing import Set


class URLFilter:
    """Filters duplicate requests to prevent crawl loops."""

    def __init__(self):
        self._seen: Set[str] = set()

    def add(self, url: str) -> bool:
        """Returns True if URL was newly added, False if already seen."""
        norm_url = url.split("#")[0].rstrip("/")
        if norm_url in self._seen:
            return False
        self._seen.add(norm_url)
        return True

    def __contains__(self, url: str) -> bool:
        norm_url = url.split("#")[0].rstrip("/")
        return norm_url in self._seen
