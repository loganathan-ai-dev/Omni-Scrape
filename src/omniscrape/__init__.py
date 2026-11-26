"""OmniScrape - Universal Dynamic Web Scraping Framework.

Main package public entry points.
"""

import asyncio
from typing import Optional, Union

from omniscrape._version import __version__
from omniscrape.classifier.detector import PageClassifier
from omniscrape.classifier.strategies import EscalationStrategy
from omniscrape.crawler.engine import CrawlEngine
from omniscrape.crawler.spider import Request, Spider
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.fetchers.browser import DynamicFetcher
from omniscrape.fetchers.http import FastFetcher
from omniscrape.fetchers.pool import ProxyPoolManager
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
from omniscrape.storage.parquet_backend import JSONLStorage

__all__ = [
    "__version__",
    "scrape",
    "scrape_sync",
    "fetch",
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
    tier: Optional[int] = None,
    headers: Optional[dict[str, str]] = None,
    proxy: Optional[str] = None,
    timeout: float = 30.0,
    **kwargs,
) -> FetchResult:
    """Fetches raw HTML from a URL with automatic or forced tier selection."""
    if tier == 1:
        fetcher = FastFetcher()
    elif tier == 2:
        fetcher = DynamicFetcher()
    elif tier == 3:
        fetcher = StealthFetcher()
    else:
        # Dynamic classifier
        classifier = PageClassifier()
        classification = await classifier.probe(url)
        fetcher = EscalationStrategy.get_initial_fetcher(classification)

    try:
        result = await fetcher.fetch(url, headers=headers, proxy=proxy, timeout=timeout, **kwargs)

        # Check if auto-escalation is needed
        next_tier = EscalationStrategy.should_escalate(result)
        if next_tier and tier is None:
            await fetcher.close()
            if next_tier == "StealthFetcher":
                fetcher = StealthFetcher()
            else:
                fetcher = DynamicFetcher()
            result = await fetcher.fetch(url, headers=headers, proxy=proxy, timeout=timeout, **kwargs)

        return result
    finally:
        await fetcher.close()


async def scrape(
    url: str,
    tier: Optional[int] = None,
    headers: Optional[dict[str, str]] = None,
    proxy: Optional[str] = None,
    **kwargs,
) -> ScrapeResult:
    """One-liner universal scraper: fetches, classifies, parses, and extracts structured data."""
    fetch_res = await fetch(url, tier=tier, headers=headers, proxy=proxy, **kwargs)
    html = fetch_res.html

    semantic = SemanticExtractor(html, url=url)
    density = DensityAnalyzer(html)
    selector = Selector(html)

    # Title detection
    title = ""
    title_el = selector.css("title")
    if title_el:
        title = title_el[0].text
    if not title:
        title = semantic.extract_opengraph().get("og:title", "")

    # Structured extraction
    product = semantic.extract_product()
    article = semantic.extract_article()
    markdown = html_to_markdown(html)

    # Collect links
    links = [el.get("href") for el in selector.css("a[href]") if el.get("href")]

    return ScrapeResult(
        url=url,
        status_code=fetch_res.status_code,
        title=title,
        html=html,
        markdown=markdown,
        structured_data=semantic.extract_all(),
        product=product,
        article=article,
        links=links[:100],
        latency_ms=fetch_res.latency_ms,
        fetcher_tier=fetch_res.fetcher_tier,
    )


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
