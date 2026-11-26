"""OmniScrape - Universal Dynamic Web Scraping Framework.

Main package public entry points.
"""

import asyncio
from typing import Optional, Union

from omniscrape._version import __version__
from omniscrape.classifier.detector import PageClassifier
from omniscrape.classifier.strategies import EscalationStrategy
from omniscrape.client import OmniClient, build_scrape_result
from omniscrape.crawler.engine import CrawlEngine
from omniscrape.crawler.spider import Request, Spider
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.fetchers.browser import DynamicFetcher
from omniscrape.fetchers.http import FastFetcher
from omniscrape.fetchers.pool import ProxyPoolManager
from omniscrape.fetchers.registry import available_fetchers, create_fetcher, register_fetcher
from omniscrape.fetchers.session import FetcherSession
from omniscrape.fetchers.stealth import StealthFetcher
from omniscrape.models import Article, FetchResult, Product, ScrapeResult
from omniscrape.normalizers.currency import parse_price
from omniscrape.normalizers.dates import parse_date
from omniscrape.normalizers.markdown import html_to_markdown
from omniscrape.normalizers.units import parse_unit
from omniscrape.parsers.adaptive import AdaptiveEngine, NodeFingerprint
from omniscrape.parsers.density import DensityAnalyzer
from omniscrape.parsers.selector import Element, Selector
from omniscrape.parsers.semantic import SemanticExtractor
from omniscrape.parsers.tables import TableParser
from omniscrape.storage.duckdb_backend import DuckDBStorage
from omniscrape.storage.jsonl_backend import JSONLStorage

__all__ = [
    "__version__",
    "scrape",
    "scrape_sync",
    "fetch",
    "OmniClient",
    "build_scrape_result",
    "register_fetcher",
    "create_fetcher",
    "available_fetchers",
    "scrape_product",
    "scrape_article",
    "Selector",
    "Element",
    "SemanticExtractor",
    "DensityAnalyzer",
    "AdaptiveEngine",
    "NodeFingerprint",
    "TableParser",
    "Spider",
    "Request",
    "CrawlEngine",
    "FastFetcher",
    "DynamicFetcher",
    "StealthFetcher",
    "ProxyPoolManager",
    "FetcherSession",
    "PageClassifier",
    "EscalationStrategy",
    "DuckDBStorage",
    "JSONLStorage",
    "Product",
    "Article",
    "ScrapeResult",
    "FetchResult",
    "parse_price",
    "parse_unit",
    "parse_date",
    "html_to_markdown",
]


async def fetch(
    url: str,
    tier: Optional[Union[int, str]] = None,
    headers: Optional[dict[str, str]] = None,
    proxy: Optional[str] = None,
    timeout: float = 30.0,
    *,
    allow_stealth: bool = False,
    retries: int = 2,
    **kwargs,
) -> FetchResult:
    """Fetch a URL with automatic (``tier=None``) or forced tier/engine selection.

    Auto mode starts with the fast HTTP tier and escalates to browser rendering when the page is
    an empty JavaScript shell. Escalation to the stealth tier on a block happens only with
    ``allow_stealth=True``. For many requests, reuse an ``OmniClient`` instead.
    """
    async with OmniClient(allow_stealth=allow_stealth, retries=retries, timeout=timeout) as client:
        return await client.fetch(url, tier=tier, headers=headers, proxy=proxy, **kwargs)


async def scrape(
    url: str,
    tier: Optional[Union[int, str]] = None,
    headers: Optional[dict[str, str]] = None,
    proxy: Optional[str] = None,
    *,
    allow_stealth: bool = False,
    retries: int = 2,
    timeout: float = 30.0,
    **kwargs,
) -> ScrapeResult:
    """One-liner universal scraper: fetch, then extract title, markdown, structured data and links."""
    async with OmniClient(allow_stealth=allow_stealth, retries=retries, timeout=timeout) as client:
        return await client.scrape(url, tier=tier, headers=headers, proxy=proxy, **kwargs)


def scrape_sync(url: str, **kwargs) -> ScrapeResult:
    """Synchronous wrapper for scrape()."""
    return asyncio.run(scrape(url, **kwargs))


async def scrape_product(url: str, **kwargs) -> Optional[Product]:
    """Specialized product extraction from an e-commerce URL."""
    res = await scrape(url, **kwargs)
    return res.product


async def scrape_article(url: str, **kwargs) -> Optional[Article]:
    """Specialized article extraction from a news/blog URL."""
    res = await scrape(url, **kwargs)
    return res.article
