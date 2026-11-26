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
    suites = frozenset({"parse", "adaptive", "crawl", "live"})

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

    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        from scrapling.spiders import Spider

        host = urlsplit(start_url).hostname
        pages: list[dict[str, Any]] = []

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
                if len(pages) >= max_pages:
                    return
                for href in response.css("a::attr(href)").getall():
                    if href and not href.startswith("#"):
                        yield response.follow(href.split("#")[0])

        BenchSpider().start()
        return pages
