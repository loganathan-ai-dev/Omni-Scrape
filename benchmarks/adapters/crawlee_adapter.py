"""Crawlee (Python) adapter: ParselCrawler with same-hostname link enqueueing."""

import asyncio
import os
from typing import Any

from benchmarks.adapters.base import ToolAdapter


class CrawleeAdapter(ToolAdapter):
    package = "crawlee"
    suites = frozenset({"crawl", "live"})

    def prepare(self) -> None:
        import crawlee  # noqa: F401

    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        os.chdir(workdir)  # crawlee keeps request queues/datasets under ./storage
        os.environ.setdefault("CRAWLEE_PURGE_ON_START", "1")
        from crawlee import ConcurrencySettings
        from crawlee.crawlers import ParselCrawler, ParselCrawlingContext

        pages: list[dict[str, Any]] = []

        async def main() -> None:
            kwargs: dict[str, Any] = dict(
                max_requests_per_crawl=max_pages,
                max_request_retries=2,
                concurrency_settings=ConcurrencySettings(
                    min_concurrency=1, desired_concurrency=concurrency, max_concurrency=concurrency),
            )
            try:
                crawler = ParselCrawler(respect_robots_txt_file=obey_robots, **kwargs)
            except TypeError:  # older crawlee without robots support
                crawler = ParselCrawler(**kwargs)

            @crawler.router.default_handler
            async def handler(ctx: ParselCrawlingContext) -> None:
                pages.append({"url": ctx.request.url, "status": ctx.http_response.status_code,
                              "title": ctx.selector.css("title::text").get() or ""})
                await ctx.enqueue_links(strategy="same-hostname")

            await crawler.run([start_url])

        asyncio.run(main())
        return pages
