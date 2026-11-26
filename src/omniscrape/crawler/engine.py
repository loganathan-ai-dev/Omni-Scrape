"""Asynchronous concurrency crawl execution engine."""

import asyncio
from typing import Optional
from omniscrape.crawler.autothrottle import AutoThrottle
from omniscrape.crawler.checkpoint import CheckpointManager
from omniscrape.crawler.dedup import URLFilter
from omniscrape.crawler.spider import Request, Spider
from omniscrape.fetchers.http import FastFetcher
from omniscrape.models import FetchResult
from omniscrape.parsers.selector import Selector
from omniscrape.storage.base import BaseStorage
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.crawler.engine")


class CrawlEngine:
    """Orchestrates async spider execution, task queue, and storage pipelines."""

    def __init__(
        self,
        spider: Spider,
        storage: Optional[BaseStorage] = None,
        use_checkpoint: bool = True,
    ):
        self.spider = spider
        self.storage = storage
        self.queue: asyncio.Queue[Request] = asyncio.Queue()
        self.dedup = URLFilter()
        self.throttle = AutoThrottle()
        self.checkpoint = CheckpointManager(spider.name) if use_checkpoint else None
        self.fetcher = FastFetcher()

    async def run(self):
        logger.info(f"Starting crawl for spider '{self.spider.name}' (concurrency={self.spider.concurrency})")

        # Load start URLs
        for url in self.spider.start_urls:
            if self.checkpoint and self.checkpoint.is_completed(url):
                logger.info(f"Skipping already completed start URL: {url}")
                continue
            if self.dedup.add(url):
                await self.queue.put(Request(url=url, callback=self.spider.parse))

        workers = [
            asyncio.create_task(self._worker(f"worker-{i}"))
            for i in range(self.spider.concurrency)
        ]

        await self.queue.join()

        for w in workers:
            w.cancel()

        await self.fetcher.close()
        if self.storage:
            await self.storage.close()
        logger.info(f"Crawl finished for spider '{self.spider.name}'")

    async def _worker(self, name: str):
        while True:
            try:
                req = await self.queue.get()
            except asyncio.CancelledError:
                break

            try:
                await self.throttle.wait()
                result = await self.fetcher.fetch(req.url, method=req.method, headers=req.headers)
                self.throttle.record_latency(result.latency_ms)

                selector = Selector(result.html)
                callback = req.callback or self.spider.parse

                async for item in callback(result, selector):
                    if isinstance(item, Request):
                        if (not self.checkpoint or not self.checkpoint.is_completed(item.url)) and self.dedup.add(item.url):
                            await self.queue.put(item)
                    elif self.storage:
                        await self.storage.write(item)

                if self.checkpoint:
                    self.checkpoint.mark_completed(req.url)

            except Exception as exc:
                logger.error(f"Error processing {req.url}: {exc}")
                await self.spider.on_error(req, exc)
            finally:
                self.queue.task_done()
