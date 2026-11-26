"""Scrapling adapter: parser, adaptive selectors (auto_save/adaptive) and Spider crawling."""

import logging
from typing import Any, Optional
from urllib.parse import urlsplit

from benchmarks.adapters.base import ToolAdapter


def _text(el: Any) -> str:
    root = getattr(el, "_root", None)
    if root is not None and hasattr(root, "text_content"):
        return root.text_content()
    return el.get_all_text(separator=" ")


class ScraplingAdapter(ToolAdapter):
    package = "scrapling"
    suites = frozenset({"parse", "adaptive", "render", "crawl", "live"})

    def prepare(self) -> None:
        from scrapling.parser import Selector  # noqa: F401

    def select_texts(self, html, selectors):
        from scrapling.parser import Selector

        page = Selector(html)
        return [[_text(el) for el in page.css(sel)] for sel in selectors]

    def _page(self, html: str, url: str, storage_dir: str):
        from scrapling.parser import Selector

        return Selector(html, url=url, adaptive=True,
                        storage_args={"storage_file": f"{storage_dir}/scrapling.db", "url": url})

    def adaptive_save(self, html, url, selectors, storage_dir):
        page = self._page(html, url, storage_dir)
        for name, sel in selectors.items():
            page.css(sel, identifier=name, auto_save=True)

    def adaptive_find(self, html, url, selectors, storage_dir) -> dict[str, Optional[str]]:
        page = self._page(html, url, storage_dir)
        out: dict[str, Optional[str]] = {}
        for name, sel in selectors.items():
            found = page.css(sel, identifier=name, adaptive=True)
            out[name] = _text(found[0]) if found else None
        return out

    def render(self, urls, concurrency):
        import asyncio

        from scrapling.fetchers import AsyncStealthySession

        async def main():
            sem = asyncio.Semaphore(concurrency)
            session = AsyncStealthySession(headless=True, max_pages=concurrency)
            await session.start()
            try:
                async def one(url):
                    async with sem:
                        try:
                            resp = await session.fetch(url)
                            return {"url": url, "status": resp.status, "html": str(resp.html_content)}
                        except Exception as exc:
                            return {"url": url, "status": 0, "html": "", "error": str(exc)[:200]}

                return list(await asyncio.gather(*(one(u) for u in urls)))
            finally:
                await session.close()

        return asyncio.run(main())

    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        from scrapling.spiders import Spider

        host = urlsplit(start_url).netloc  # Scrapling compares host:port, so a bare hostname drops local-port links
        pages: list[dict[str, Any]] = []
        scheduled = {start_url}

        class BenchSpider(Spider):
            name = "bench"
            start_urls = [start_url]
            allowed_domains = {host}
            robots_txt_obey = obey_robots
            concurrent_requests = concurrency
            logging_level = logging.ERROR

            async def parse(self, response):
                pages.append({"url": str(response.url), "status": response.status,
                              "title": response.css("title::text").get() or ""})
                for href in response.css("a::attr(href)").getall():
                    if not href or href.startswith("#"):
                        continue
                    target = response.urljoin(href.split("#")[0])
                    if urlsplit(target).netloc != host or target in scheduled:
                        continue
                    if len(scheduled) < max_pages:
                        scheduled.add(target)  # hard cap on scheduled URLs
                        yield response.follow(target)

        BenchSpider().start()
        return pages
