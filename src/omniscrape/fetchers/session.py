"""Persistent session handling cookies, authentication, and headers."""

from typing import Optional
from omniscrape.fetchers.http import FastFetcher
from omniscrape.models import FetchResult


class FetcherSession:
    """Session container maintaining cookie state and connection reuse."""

    def __init__(self, fetcher: Optional[FastFetcher] = None):
        self.fetcher = fetcher or FastFetcher()
        self.cookies: dict[str, str] = {}
        self.headers: dict[str, str] = {}

    async def get(self, url: str, **kwargs) -> FetchResult:
        result = await self.fetcher.fetch(
            url,
            method="GET",
            headers=self.headers,
            cookies=self.cookies,
            **kwargs,
        )
        if result.cookies:
            self.cookies.update(result.cookies)
        return result

    async def close(self) -> None:
        await self.fetcher.close()
