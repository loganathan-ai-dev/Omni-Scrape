"""Scrapy adapter: CrawlSpider + LinkExtractor (runs once per worker process: Twisted reactor)."""

from typing import Any
from urllib.parse import urlsplit

from benchmarks.adapters.base import ToolAdapter


class ScrapyAdapter(ToolAdapter):
    package = "scrapy"
    suites = frozenset({"crawl", "live"})

    def prepare(self) -> None:
        import scrapy  # noqa: F401

    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        from scrapy.crawler import CrawlerProcess
        from scrapy.linkextractors import LinkExtractor
        from scrapy.spiders import CrawlSpider, Rule

        pages: list[dict[str, Any]] = []
        host = urlsplit(start_url).hostname

        class BenchSpider(CrawlSpider):
            name = "bench"
            allowed_domains = [host]
            start_urls = [start_url]
            rules = (Rule(LinkExtractor(), callback="parse_item", follow=True),)

            def parse_start_url(self, response, **kwargs):
                return self.parse_item(response)

            def parse_item(self, response):
                pages.append({"url": response.url, "status": response.status,
                              "title": response.css("title::text").get() or ""})
                return []

        process = CrawlerProcess(settings={
            "ROBOTSTXT_OBEY": obey_robots,
            "CONCURRENT_REQUESTS": concurrency,
            "CONCURRENT_REQUESTS_PER_DOMAIN": concurrency,
            "CLOSESPIDER_PAGECOUNT": max_pages,
            "RETRY_TIMES": 2,
            "DOWNLOAD_DELAY": 0,
            "AUTOTHROTTLE_ENABLED": False,
            "LOG_LEVEL": "ERROR",
            "TELNETCONSOLE_ENABLED": False,
            "USER_AGENT": "omniscrape-benchmark/0.2 (scrapy)",
            "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        })
        process.crawl(BenchSpider)
        process.start()
        return pages
