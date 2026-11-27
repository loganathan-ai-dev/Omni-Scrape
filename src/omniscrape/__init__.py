"""OmniScrape - Universal Dynamic Web Scraping Framework.

Main package public entry points (lazily imported so ``import omniscrape`` stays fast).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from importlib import import_module
from typing import TYPE_CHECKING, Any, Optional, Union

from omniscrape._version import __version__

if TYPE_CHECKING:
    from omniscrape.classifier.detector import PageClassifier
    from omniscrape.classifier.strategies import EscalationStrategy
    from omniscrape.client import OmniClient, build_scrape_result
    from omniscrape.content import chunk_markdown, extract_main, extract_metadata, fit_markdown
    from omniscrape.crawler.engine import CrawlEngine, CrawlStats
    from omniscrape.crawler.links import LinkExtractor
    from omniscrape.crawler.sitemap import map_site
    from omniscrape.crawler.spider import Request, Spider
    from omniscrape.extract.listings import extract_listings
    from omniscrape.extract.product import extract_product
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

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "PageClassifier": ("omniscrape.classifier.detector", "PageClassifier"),
    "EscalationStrategy": ("omniscrape.classifier.strategies", "EscalationStrategy"),
    "OmniClient": ("omniscrape.client", "OmniClient"),
    "build_scrape_result": ("omniscrape.client", "build_scrape_result"),
    "chunk_markdown": ("omniscrape.content", "chunk_markdown"),
    "extract_main": ("omniscrape.content", "extract_main"),
    "extract_metadata": ("omniscrape.content", "extract_metadata"),
    "fit_markdown": ("omniscrape.content", "fit_markdown"),
    "CrawlEngine": ("omniscrape.crawler.engine", "CrawlEngine"),
    "CrawlStats": ("omniscrape.crawler.engine", "CrawlStats"),
    "LinkExtractor": ("omniscrape.crawler.links", "LinkExtractor"),
    "map_site": ("omniscrape.crawler.sitemap", "map_site"),
    "Request": ("omniscrape.crawler.spider", "Request"),
    "Spider": ("omniscrape.crawler.spider", "Spider"),
    "extract_listings": ("omniscrape.extract.listings", "extract_listings"),
    "extract_product": ("omniscrape.extract.product", "extract_product"),
    "BaseFetcher": ("omniscrape.fetchers.base", "BaseFetcher"),
    "DynamicFetcher": ("omniscrape.fetchers.browser", "DynamicFetcher"),
    "FastFetcher": ("omniscrape.fetchers.http", "FastFetcher"),
    "ProxyPoolManager": ("omniscrape.fetchers.pool", "ProxyPoolManager"),
    "available_fetchers": ("omniscrape.fetchers.registry", "available_fetchers"),
    "create_fetcher": ("omniscrape.fetchers.registry", "create_fetcher"),
    "register_fetcher": ("omniscrape.fetchers.registry", "register_fetcher"),
    "FetcherSession": ("omniscrape.fetchers.session", "FetcherSession"),
    "StealthFetcher": ("omniscrape.fetchers.stealth", "StealthFetcher"),
    "Article": ("omniscrape.models", "Article"),
    "FetchResult": ("omniscrape.models", "FetchResult"),
    "Product": ("omniscrape.models", "Product"),
    "ScrapeResult": ("omniscrape.models", "ScrapeResult"),
    "parse_price": ("omniscrape.normalizers.currency", "parse_price"),
    "parse_date": ("omniscrape.normalizers.dates", "parse_date"),
    "html_to_markdown": ("omniscrape.normalizers.markdown", "html_to_markdown"),
    "parse_unit": ("omniscrape.normalizers.units", "parse_unit"),
    "AdaptiveEngine": ("omniscrape.parsers.adaptive", "AdaptiveEngine"),
    "NodeFingerprint": ("omniscrape.parsers.adaptive", "NodeFingerprint"),
    "DensityAnalyzer": ("omniscrape.parsers.density", "DensityAnalyzer"),
    "Element": ("omniscrape.parsers.selector", "Element"),
    "Selector": ("omniscrape.parsers.selector", "Selector"),
    "SemanticExtractor": ("omniscrape.parsers.semantic", "SemanticExtractor"),
    "TableParser": ("omniscrape.parsers.tables", "TableParser"),
    "DuckDBStorage": ("omniscrape.storage.duckdb_backend", "DuckDBStorage"),
    "JSONLStorage": ("omniscrape.storage.jsonl_backend", "JSONLStorage"),
}

__all__ = [
    "__version__",
    "scrape",
    "scrape_sync",
    "fetch",
    "fetch_many",
    "scrape_many",
    "map_site",
    "extract_listings",
    "extract_product",
    "extract_main",
    "extract_metadata",
    "fit_markdown",
    "chunk_markdown",
    "LinkExtractor",
    "CrawlStats",
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


def __getattr__(name: str) -> Any:
    target = _LAZY_IMPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_name, attr = target
    val = getattr(import_module(mod_name), attr)
    globals()[name] = val
    return val


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


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
) -> "FetchResult":
    """Fetch a URL with automatic (``tier=None``) or forced tier/engine selection.

    Auto mode starts with the fast HTTP tier and escalates to browser rendering when the page is
    an empty JavaScript shell. Escalation to the stealth tier on a block happens only with
    ``allow_stealth=True``. For many requests, reuse an ``OmniClient`` instead.
    """
    from omniscrape.client import OmniClient

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
) -> "ScrapeResult":
    """One-liner universal scraper: fetch, then extract title, markdown, structured data and links."""
    from omniscrape.client import OmniClient

    async with OmniClient(allow_stealth=allow_stealth, retries=retries, timeout=timeout) as client:
        return await client.scrape(url, tier=tier, headers=headers, proxy=proxy, **kwargs)


def scrape_sync(url: str, **kwargs) -> "ScrapeResult":
    """Synchronous wrapper for scrape()."""
    return asyncio.run(scrape(url, **kwargs))


async def scrape_product(url: str, **kwargs) -> Optional["Product"]:
    """Specialized product extraction from an e-commerce URL."""
    res = await scrape(url, **kwargs)
    return res.product


async def scrape_article(url: str, **kwargs) -> Optional["Article"]:
    """Specialized article extraction from a news/blog URL."""
    res = await scrape(url, **kwargs)
    return res.article


async def fetch_many(
    urls: Sequence[str],
    *,
    concurrency: int = 8,
    per_domain_concurrency: int = 4,
    delay: float = 0.0,
    tier: Optional[Union[int, str]] = None,
    allow_stealth: bool = False,
    retries: int = 2,
    timeout: float = 30.0,
    return_exceptions: bool = False,
    **kwargs,
) -> list[Union["FetchResult", Exception]]:
    """Concurrently fetch multiple URLs using a shared ``OmniClient``."""
    from omniscrape.client import OmniClient

    async with OmniClient(allow_stealth=allow_stealth, retries=retries, timeout=timeout) as client:
        return await client.fetch_many(
            urls,
            concurrency=concurrency,
            per_domain_concurrency=per_domain_concurrency,
            delay=delay,
            tier=tier,
            return_exceptions=return_exceptions,
            **kwargs,
        )


async def scrape_many(
    urls: Sequence[str],
    *,
    concurrency: int = 8,
    per_domain_concurrency: int = 4,
    delay: float = 0.0,
    tier: Optional[Union[int, str]] = None,
    allow_stealth: bool = False,
    retries: int = 2,
    timeout: float = 30.0,
    return_exceptions: bool = False,
    **kwargs,
) -> list[Union["ScrapeResult", Exception]]:
    """Concurrently fetch and extract multiple URLs using a shared ``OmniClient``."""
    from omniscrape.client import OmniClient

    async with OmniClient(allow_stealth=allow_stealth, retries=retries, timeout=timeout) as client:
        return await client.scrape_many(
            urls,
            concurrency=concurrency,
            per_domain_concurrency=per_domain_concurrency,
            delay=delay,
            tier=tier,
            return_exceptions=return_exceptions,
            **kwargs,
        )
