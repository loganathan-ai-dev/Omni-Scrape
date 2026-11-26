"""OmniScrape adapter. Uses only the public API; newer capabilities are used when available."""

import asyncio
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

from benchmarks.adapters.base import ToolAdapter


class OmniScrapeAdapter(ToolAdapter):
    package = "omniscrape"
    suites = frozenset({"parse", "extract", "markdown", "adaptive", "render", "crawl", "live"})

    def __init__(self, isolate: bool = False):
        # render suite: isolate=False shares one browser context and reuses tabs (like the other tools'
        # sessions); isolate=True is OmniScrape's default: a fresh context per page.
        self.isolate = isolate

    def prepare(self) -> None:
        import omniscrape  # noqa: F401

    # -------------------------------------------------------------- parse
    def select_texts(self, html, selectors):
        from omniscrape.parsers.selector import Selector

        page = Selector(html)
        return [[el.text for el in page.css(sel)] for sel in selectors]

    # -------------------------------------------------------------- extract
    def extract(self, html: str, url: str, kind: str) -> dict[str, Any]:
        from omniscrape.client import build_scrape_result
        from omniscrape.models import FetchResult

        res = build_scrape_result(FetchResult(url=url, status_code=200, html=html), url)
        if kind == "product":
            p = res.product
            if p is None:
                return {"title": res.title or None}
            availability = p.availability
            if availability and "/" in availability:
                availability = availability.rsplit("/", 1)[-1]
            return {"title": p.title, "price": p.price, "currency": p.currency, "brand": p.brand, "sku": p.sku,
                    "rating": p.rating, "review_count": p.review_count, "availability": availability}
        a = res.article
        if a is None:
            return {"title": res.title or None}
        return {"title": a.title, "author": a.author, "published_date": a.published_date}

    # -------------------------------------------------------------- markdown
    def markdown(self, html: str, url: str) -> str:
        from omniscrape.normalizers import markdown as md

        if hasattr(md, "fit_markdown"):  # main-content markdown (added in Phase 3)
            return md.fit_markdown(html, url=url)
        return md.html_to_markdown(html)

    # -------------------------------------------------------------- adaptive
    def _engine(self, storage_dir: str):
        from omniscrape.parsers.adaptive import AdaptiveEngine

        return AdaptiveEngine(db_path=f"{storage_dir}/omniscrape_fp.db")

    def adaptive_save(self, html, url, selectors, storage_dir):
        from omniscrape.parsers.adaptive import NodeFingerprint
        from omniscrape.parsers.selector import Selector

        engine, page, domain = self._engine(storage_dir), Selector(html), urlsplit(url).hostname
        for name, sel in selectors.items():
            found = page.css(sel)
            if found:
                engine.save_fingerprint(domain, name, NodeFingerprint.from_element(found[0]))

    def adaptive_find(self, html, url, selectors, storage_dir) -> dict[str, Optional[str]]:
        from omniscrape.parsers.selector import Selector

        engine, page, domain = self._engine(storage_dir), Selector(html), urlsplit(url).hostname
        out: dict[str, Optional[str]] = {}
        for name, sel in selectors.items():
            found = page.css(sel)
            if found:
                out[name] = found[0].text
                continue
            fp = engine.load_fingerprint(domain, name)
            el = engine.relocate(page, fp) if fp else None
            out[name] = el.text if el is not None else None
        return out

    # -------------------------------------------------------------- render
    def render(self, urls, concurrency):
        from omniscrape import OmniClient

        async def main():
            sem = asyncio.Semaphore(concurrency)
            async with OmniClient(retries=1, fetcher_options={2: {"isolate": self.isolate}}) as client:
                async def one(url):
                    async with sem:
                        try:
                            res = await client.fetch(url, tier=2)
                            return {"url": url, "status": res.status_code, "html": res.html}
                        except Exception as exc:
                            return {"url": url, "status": 0, "html": "", "error": str(exc)[:200]}

                return list(await asyncio.gather(*(one(u) for u in urls)))

        return asyncio.run(main())

    # -------------------------------------------------------------- crawl
    def crawl(self, start_url, max_pages, concurrency, obey_robots, workdir):
        from omniscrape.crawler.engine import CrawlEngine
        from omniscrape.crawler.links import LinkExtractor
        from omniscrape.crawler.spider import Request, Spider

        pages: list[dict[str, Any]] = []
        links = LinkExtractor(same_domain=True)

        class BenchSpider(Spider):
            name = "bench"
            start_urls = [start_url]

            async def parse(self, response, selector):
                titles = selector.css("title")
                pages.append({"url": response.url, "status": response.status_code,
                              "title": titles[0].text if titles else ""})
                for url in links.extract(selector, response.url):
                    yield Request(url=url)

        BenchSpider.concurrency = concurrency
        engine = CrawlEngine(BenchSpider(), obey_robots=obey_robots, max_pages=max_pages,
                             allowed_domains=[urlsplit(start_url).netloc])
        asyncio.run(engine.run())
        return pages
