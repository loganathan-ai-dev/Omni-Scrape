"""Abstract base fetcher interface."""

from abc import ABC, abstractmethod
from typing import Optional
from omniscrape.models import FetchResult


class BaseFetcher(ABC):
    """Abstract interface implemented by all fetcher tiers."""

    @abstractmethod
    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        **kwargs,
    ) -> FetchResult:
        """Fetch a URL and return a standardized FetchResult."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Release underlying connections and browser resources."""
        pass
