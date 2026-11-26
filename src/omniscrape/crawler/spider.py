"""Spider request and base class definitions."""

from typing import Any, AsyncIterator, Callable, Optional, Union
from omniscrape.models import FetchResult
from omniscrape.parsers.selector import Selector


class Request:
    """Represents a spider URL crawl target."""

    def __init__(
        self,
        url: str,
        callback: Optional[Callable[..., Any]] = None,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        meta: Optional[dict[str, Any]] = None,
        priority: int = 0,
    ):
        self.url = url
        self.callback = callback
        self.method = method
        self.headers = headers or {}
        self.meta = meta or {}
        self.priority = priority


class Spider:
    """Base Spider class for concurrent multi-page web crawlers."""

    name: str = "base_spider"
    start_urls: list[str] = []
    concurrency: int = 10
    stealth: str = "auto"

    async def parse(self, response: FetchResult, selector: Selector) -> AsyncIterator[Union[Request, dict, Any]]:
        """Override to parse response and yield Request or extracted item."""
        if False:
            yield None

    async def on_error(self, request: Request, error: Exception) -> None:
        pass
