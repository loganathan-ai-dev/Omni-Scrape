"""Crawl4AI adapter: markdown generation (raw / pruned "fit") and BFS deep crawling."""

import asyncio
from typing import Any

from benchmarks.adapters.base import ToolAdapter


class Crawl4AIAdapter(ToolAdapter):
    package = "crawl4ai"
    suites = frozenset({"markdown", "render", "crawl"})

    def __init__(self, fit: bool = False):
        self.fit = fit
        self._scraper = None

    def prepare(self) -> None:
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        try:
            from crawl4ai import LXMLWebScrapingStrategy as Scraper
        except ImportError:  # older releases
            from crawl4ai.content_scraping_strategy import WebScrapingStrategy as Scraper
        self._scraper = Scraper()
        self._gen = DefaultMarkdownGenerator(content_filter=PruningContentFilter() if self.fit else None)

    def markdown(self, html: str, url: str) -> str:
        # Same pipeline as AsyncWebCrawler: scraping strategy -> cleaned_html -> markdown generator.
        scraped = self._scraper.scrap(url, html)
        cleaned = getattr(scraped, "cleaned_html", None) or (scraped.get("cleaned_html") if isinstance(scraped, dict) else html)
        result = self._gen.generate_markdown(input_html=cleaned, base_url=url)
        if self.fit:
            return result.fit_markdown or ""
        return result.raw_markdown or ""

    def render(self, urls, concurrency):
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

        async def main():
            config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, semaphore_count=concurrency, verbose=False)
            async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
                results = await crawler.arun_many(urls, config=config)
            return [{"url": r.url, "status": r.status_code or 0, "html": r.html or ""} for r in results]

        return asyncio.run(main())

    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

        async def main() -> list[dict[str, Any]]:
            config = CrawlerRunConfig(
                deep_crawl_strategy=BFSDeepCrawlStrategy(max_depth=100, include_external=False, max_pages=max_pages),
                check_robots_txt=obey_robots,
                cache_mode=CacheMode.BYPASS,
                semaphore_count=concurrency,
                verbose=False,
            )
            async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
                results = await crawler.arun(start_url, config=config)
            return [{"url": r.url, "status": r.status_code, "title": (r.metadata or {}).get("title", "")}
                    for r in results]

        return asyncio.run(main())
