"""End-to-end crawler tests against the local test site (no internet needed)."""

import asyncio
import tempfile

from omniscrape.crawler.engine import CrawlEngine
from omniscrape.crawler.links import LinkExtractor
from omniscrape.crawler.sitemap import map_site
from omniscrape.crawler.spider import Request, Spider


def make_spider(base: str, seen: list):
    links = LinkExtractor(same_domain=True)

    class SiteSpider(Spider):
        name = "it-site"
        start_urls = [base + "/"]
        concurrency = 8

        async def parse(self, response, selector):
            seen.append(response.url)
            titles = selector.css("title")  # /sitemap.xml (linked from the nav) has no <title>
            yield {"url": response.url, "title": titles[0].text if titles else ""}
            for url in links.extract(selector, response.url):
                yield Request(url)

    return SiteSpider()


async def test_full_crawl_obeys_robots_recovers_flaky_pages_and_never_repeats(site):
    seen: list = []
    stats = await CrawlEngine(make_spider(site.base, seen)).run()
    server = site.get("/__stats")
    assert server["coverage"] == 1.0
    assert server["robots_violations"] == 0
    assert server["duplicate_requests"] == 0
    assert server["flaky_recovered"] == server["flaky_seen"] > 0
    # the nav also links /sitemap.xml, which the site's expected-page count leaves out
    assert stats.robots_blocked > 0 and stats.items == stats.pages >= server["expected_allowed"]


async def test_page_budget_and_depth_limit(site):
    seen: list = []
    stats = await CrawlEngine(make_spider(site.base, seen), max_pages=10).run()
    assert stats.pages <= 10 and site.get("/__stats")["total_requests"] <= 12  # + robots.txt
    site.get("/__reset")
    seen2: list = []
    stats2 = await CrawlEngine(make_spider(site.base, seen2), max_depth=1).run()
    assert stats2.filtered_depth > 0 and stats2.pages < site.get("/__meta")["expected_allowed"]


async def test_graceful_stop_then_resume_loses_and_repeats_nothing(site):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        qpath = f"{tmp}/queue.db"
        first: list = []
        # stop early via the page budget, leaving pending requests in the persistent queue
        await CrawlEngine(make_spider(site.base, first), queue_path=qpath, max_pages=15).run()
        assert 0 < len(first) <= 15
        second: list = []
        await CrawlEngine(make_spider(site.base, second), queue_path=qpath).run()
        server = site.get("/__stats")
        assert server["coverage"] == 1.0
        assert server["duplicate_requests"] == 0
        assert not set(first) & set(second)


async def test_hard_kill_then_resume_loses_nothing(site):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        qpath = f"{tmp}/queue.db"
        seen: list = []
        engine = CrawlEngine(make_spider(site.base, seen), queue_path=qpath)
        task = asyncio.create_task(engine.run())
        while len(seen) < 12:
            await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await CrawlEngine(make_spider(site.base, []), queue_path=qpath).run()
        server = site.get("/__stats")
        assert server["coverage"] == 1.0
        # at-least-once: only requests in flight at the moment of the kill can be fetched twice
        assert server["duplicate_requests"] <= engine.concurrency


async def test_stream_yields_items(site):
    seen: list = []
    engine = CrawlEngine(make_spider(site.base, seen), max_pages=5)
    items = [item async for item in engine.stream()]
    assert len(items) == 5 and all("title" in i for i in items)


async def test_map_site_uses_sitemap_and_respects_robots(site):
    urls = await map_site(site.base + "/")
    expected = site.get("/__meta")["expected_allowed"]
    assert len(urls) >= expected - 1
    assert not any("/private/" in u for u in urls)
    ranked = await map_site(site.base + "/", search="flaky")
    assert "/flaky/" in ranked[0]
