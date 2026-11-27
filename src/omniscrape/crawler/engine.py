"""Asynchronous crawl engine.

Every request goes through ``OmniClient`` (retries, circuit breaker, proxy pool, tier escalation).
On top of that the engine adds: robots.txt (on by default) with Crawl-delay, a priority queue
with fingerprint dedup and optional SQLite persistence (pause/resume), per-domain concurrency and
AutoThrottle, scope limits (domains, depth, page budget), item pipelines and streaming.
"""

import asyncio
import inspect
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional, Union
from urllib.parse import urljoin, urlsplit

from omniscrape.crawler.links import domain_allowed
from omniscrape.crawler.queue import RequestQueue
from omniscrape.crawler.robots import RobotsCache
from omniscrape.crawler.spider import Request, Spider
from omniscrape.crawler.throttle import DomainThrottle
from omniscrape.models import FetchResult
from omniscrape.observability.logging import get_logger
from omniscrape.parsers.selector import Selector
from omniscrape.storage.base import BaseStorage

logger = get_logger("omniscrape.crawler.engine")

Pipeline = Callable[[Any], Any]  # returns the (possibly changed) item, or None to drop it
_DONE = object()


@dataclass
class CrawlStats:
    started: float = field(default_factory=time.time)
    finished: Optional[float] = None
    pages: int = 0
    items: int = 0
    failed: int = 0
    dropped_items: int = 0
    robots_blocked: int = 0
    filtered_offsite: int = 0
    filtered_depth: int = 0
    filtered_budget: int = 0
    duplicates: int = 0
    status_counts: Counter = field(default_factory=Counter)

    @property
    def elapsed(self) -> float:
        return (self.finished or time.time()) - self.started

    @property
    def pages_per_sec(self) -> float:
        return self.pages / self.elapsed if self.elapsed else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"pages": self.pages, "items": self.items, "failed": self.failed, "dropped_items": self.dropped_items,
                "robots_blocked": self.robots_blocked, "filtered_offsite": self.filtered_offsite,
                "filtered_depth": self.filtered_depth, "filtered_budget": self.filtered_budget,
                "duplicates": self.duplicates, "status_counts": dict(self.status_counts),
                "elapsed_s": round(self.elapsed, 3), "pages_per_sec": round(self.pages_per_sec, 2)}


class CrawlEngine:
    def __init__(
        self,
        spider: Spider,
        storage: Optional[BaseStorage] = None,
        use_checkpoint: bool = False,
        *,
        client: Optional[Any] = None,
        obey_robots: bool = True,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        allowed_domains: Optional[list[str]] = None,
        concurrency: Optional[int] = None,
        per_domain_concurrency: Optional[int] = None,
        download_delay: float = 0.0,
        autothrottle: bool = False,
        queue_path: Optional[str] = None,
        resume: bool = True,
        tier: Optional[Union[int, str]] = 1,
        user_agent: str = "omniscrape",
        pipelines: Optional[list[Pipeline]] = None,
        retries: int = 2,
    ):
        self.spider = spider
        self.storage = storage
        self.client = client
        self._owns_client = client is None
        self.obey_robots = obey_robots
        self.max_pages = max_pages
        self.max_depth = max_depth if max_depth is not None else getattr(spider, "max_depth", None)
        self.allowed_domains = list(allowed_domains if allowed_domains is not None else getattr(spider, "allowed_domains", []) or [])
        self._allowed_domains_norm = [d.lower().lstrip(".") for d in self.allowed_domains if d]
        self.concurrency = concurrency or getattr(spider, "concurrency", 10)
        self.throttle = DomainThrottle(per_domain_concurrency or self.concurrency, download_delay, autothrottle)
        if use_checkpoint and not queue_path:
            folder = Path.home() / ".omniscrape" / "queues"
            folder.mkdir(parents=True, exist_ok=True)
            queue_path = str(folder / f"{spider.name}.db")
        self.queue_path = queue_path
        self.resume = resume
        self.tier = tier
        self.user_agent = user_agent
        self.pipelines = list(pipelines or [])
        self.retries = retries
        self.stats = CrawlStats()
        self._scheduled = 0
        self._cond: Optional[asyncio.Condition] = None
        self._waiting_workers = 0
        self._in_flight = 0
        self._started_fetches = 0
        self._stop = False
        self._item_queue: Optional[asyncio.Queue] = None

    # ------------------------------------------------------------------ public
    async def run(self) -> CrawlStats:
        from omniscrape.client import OmniClient

        self.client = self.client or OmniClient(retries=self.retries, retry_delay=0.1)
        self.queue = RequestQueue(self.queue_path)
        self.robots = RobotsCache(self.client, self.user_agent) if self.obey_robots else None
        self._robots_origin_rules: dict[str, Any] = {}
        self._cond = asyncio.Condition()
        self.stats = CrawlStats()
        try:
            if self.queue.has_unfinished() and self.resume:
                logger.info(f"Resuming '{self.spider.name}' with {len(self.queue)} pending requests")
                self._scheduled = sum(self.queue.counts().values())
            else:
                self.queue.reset()
                async for req in self.spider.start_requests():
                    await self.schedule(req)
            logger.info(f"Crawl '{self.spider.name}' started (concurrency={self.concurrency}, robots={self.obey_robots})")
            workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]
            await asyncio.gather(*workers)
        finally:
            self.stats.finished = time.time()
            self.queue.close()
            if self._owns_client:
                await self.client.close()
            if self.storage:
                await self.storage.close()
            if self._item_queue is not None:
                await self._item_queue.put(_DONE)
        logger.info(f"Crawl '{self.spider.name}' finished: {self.stats.to_dict()}")
        return self.stats

    async def stream(self) -> AsyncIterator[Any]:
        """Run the crawl and yield items as they are scraped."""
        self._item_queue = asyncio.Queue()
        task = asyncio.create_task(self.run())
        while True:
            item = await self._item_queue.get()
            if item is _DONE:
                break
            yield item
        await task

    async def schedule(self, req: Request) -> bool:
        parts = urlsplit(req.url)
        if parts.scheme not in ("http", "https"):
            return False
        if self._allowed_domains_norm:
            host = (parts.hostname or "").lower()
            netloc = parts.netloc.lower()
            if not any(host == d or host.endswith("." + d) or netloc == d for d in self._allowed_domains_norm):
                self.stats.filtered_offsite += 1
                return False
        if self.max_depth is not None and req.depth > self.max_depth:
            self.stats.filtered_depth += 1
            return False
        # Without persistence, stop collecting links once the budget is reached (saves memory).
        # With a persistent queue, keep every link as pending so a budget stop is a resumable pause;
        # the budget then limits fetches in _worker only.
        if self.max_pages is not None and self.queue_path is None and self._scheduled >= self.max_pages:
            self.stats.filtered_budget += 1
            return False
        if not self.queue.add(req):
            self.stats.duplicates += 1
            return False
        self._scheduled += 1
        if self._waiting_workers > 0:
            async with self._cond:
                self._cond.notify()
        return True

    # ------------------------------------------------------------------ internals
    async def _worker(self) -> None:
        while True:
            async with self._cond:
                while True:
                    if self._stop:
                        return
                    budget_left = self.max_pages is None or self._started_fetches < self.max_pages
                    popped = self.queue.pop() if budget_left else None
                    if popped:
                        self._in_flight += 1
                        self._started_fetches += 1
                        break
                    if self._in_flight == 0:
                        self._stop = True
                        self._cond.notify_all()
                        return
                    self._waiting_workers += 1
                    try:
                        await self._cond.wait()
                    finally:
                        self._waiting_workers -= 1
            fp, req = popped
            try:
                await self._process(fp, req)
            except Exception as exc:  # never let one page kill a worker
                logger.error(f"Unhandled error processing {req.url}: {exc}")
                self.stats.failed += 1
                self.queue.mark_failed(fp)
            finally:
                async with self._cond:
                    self._in_flight -= 1
                    self._cond.notify_all()

    async def _process(self, fp: str, req: Request) -> None:
        parts = urlsplit(req.url)
        domain = parts.netloc.lower()
        if self.robots is not None:
            orig = f"{parts.scheme}://{parts.netloc}"
            rules = self._robots_origin_rules.get(orig)
            if rules is None:
                rules = await self.robots.rules_for(req.url)
                self._robots_origin_rules[orig] = rules
            if not rules.allowed(self.user_agent, req.url):
                self.stats.robots_blocked += 1
                self.queue.mark_done(fp)
                return
            delay = rules.crawl_delay(self.user_agent)
            if delay:
                self.throttle.set_floor(domain, delay)

        await self.throttle.acquire(domain)
        started = time.perf_counter() if self.throttle.autothrottle else 0.0
        status: Optional[int] = None
        try:
            result: FetchResult = await self.client.fetch(
                req.url, tier=req.tier if req.tier is not None else self.tier,
                headers=req.headers or None, method=req.method,
            )
            status = result.status_code
        except Exception as exc:
            self.stats.failed += 1
            self.queue.mark_failed(fp)
            await self.spider.on_error(req, exc)
            return
        finally:
            elapsed_s = (time.perf_counter() - started) if started else None
            self.throttle.release(domain, elapsed_s, status)

        self.stats.status_counts[result.status_code] += 1
        if not 200 <= result.status_code < 300:
            self.stats.failed += 1
            self.queue.mark_failed(fp)
            return
        self.stats.pages += 1

        callback = req.callback
        if callback is None and req.callback_name:
            callback = getattr(self.spider, req.callback_name, None)
        callback = callback or self.spider.parse
        output = callback(result, Selector(result.html))
        if inspect.isasyncgen(output):
            async for out in output:
                await self._handle_output(out, req, result)
        elif inspect.isawaitable(output):
            for out in (await output) or []:
                await self._handle_output(out, req, result)
        else:
            for out in output or []:
                await self._handle_output(out, req, result)
        self.queue.mark_done(fp)

    async def _handle_output(self, out: Any, parent: Request, response: FetchResult) -> None:
        if out is None:
            return
        if isinstance(out, Request):
            if not out.url.startswith(("http://", "https://")):
                out.url = urljoin(response.url, out.url)
            if not out.depth:
                out.depth = parent.depth + 1
            await self.schedule(out)
            return
        item = out
        for pipe in self.pipelines:
            item = pipe(item)
            if inspect.isawaitable(item):
                item = await item
            if item is None:
                self.stats.dropped_items += 1
                return
        self.stats.items += 1
        if self.storage:
            await self.storage.write(item)
        if self._item_queue is not None:
            await self._item_queue.put(item)
