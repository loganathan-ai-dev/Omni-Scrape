"""Spider and Request definitions."""

from typing import Any, AsyncIterator, Callable, Optional, Union

from omniscrape.models import FetchResult
from omniscrape.parsers.selector import Selector


class Request:
    """A URL to crawl, with its callback, priority and crawl depth.

    ``meta`` is persisted with the request and handed back to the callback as ``response.meta``.
    """

    def __init__(
        self,
        url: str,
        callback: Optional[Callable[..., Any]] = None,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        meta: Optional[dict[str, Any]] = None,
        priority: int = 0,
        depth: int = 0,
        dont_filter: bool = False,
        tier: Optional[Union[int, str]] = None,
    ):
        self.url = url
        self.callback = callback
        self.callback_name: Optional[str] = getattr(callback, "__name__", None) if callback else None
        self.method = method
        self.headers = headers or {}
        self.meta = meta or {}
        self.priority = priority
        self.depth = depth
        self.dont_filter = dont_filter
        self.tier = tier  # override the engine's fetch tier/engine for this request

    def fingerprint(self) -> str:
        from omniscrape.crawler.urls import fingerprint

        return fingerprint(self.url, self.method)

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.url} depth={self.depth} priority={self.priority}>"


class Spider:
    """Base class for crawlers. Override ``parse`` to yield items (dicts/models) and Requests."""

    name: str = "base_spider"
    start_urls: list[str] = []
    allowed_domains: list[str] = []   # empty = no domain restriction
    concurrency: int = 10
    max_depth: Optional[int] = None

    async def start_requests(self) -> AsyncIterator[Request]:
        for url in self.start_urls:
            yield Request(url=url)

    async def parse(self, response: FetchResult, selector: Selector) -> AsyncIterator[Union[Request, dict, Any]]:
        """Override to parse a response and yield Requests or items."""
        if False:
            yield None

    async def on_error(self, request: Request, error: Exception) -> None:
        pass
