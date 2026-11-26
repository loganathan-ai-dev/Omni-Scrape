"""Abstract base fetcher interface and shared helpers."""

from abc import ABC, abstractmethod
from typing import Any, Optional
from urllib.parse import unquote, urlsplit, urlunsplit

from omniscrape.models import FetchResult

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class BaseFetcher(ABC):
    """Abstract interface implemented by all fetcher tiers.

    Implementations return HTTP error statuses as normal ``FetchResult`` objects and raise
    ``NetworkError`` subclasses only for transport failures. Retry and escalation decisions are
    made by ``OmniClient``.
    """

    #: Escalation tier (1 = HTTP, 2 = browser, 3 = stealth). Informational for custom fetchers.
    tier: int = 1

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
        **kwargs: Any,
    ) -> FetchResult:
        """Fetch a URL and return a standardized FetchResult."""

    @abstractmethod
    async def close(self) -> None:
        """Release underlying connections and browser resources."""

    async def __aenter__(self) -> "BaseFetcher":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()


def playwright_proxy(proxy: Optional[str]) -> Optional[dict[str, str]]:
    """Convert ``scheme://user:pass@host:port`` into Playwright's proxy dict (auth split out)."""
    if not proxy:
        return None
    parts = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    config = {"server": urlunsplit((parts.scheme, netloc, "", "", ""))}
    if parts.username:
        config["username"] = unquote(parts.username)
    if parts.password:
        config["password"] = unquote(parts.password)
    return config
