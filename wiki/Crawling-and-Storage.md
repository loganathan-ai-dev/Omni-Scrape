# Crawling, Sitemaps & Storage

OmniScrape's async crawler pairs [`Spider`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/crawler/spider.py) and [`CrawlEngine`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/crawler/engine.py) with `OmniClient` so every crawl inherits retries, proxy rotation and TLS fingerprinting (see [[Fetching-and-Stealth]]). Crawls use a fixed fetcher tier (default `tier=1`, plain HTTP); pass `tier=2` to `CrawlEngine` (or `--tier 2` to `omniscrape crawl`) for JavaScript-rendered sites, or set `Request(tier=...)` per request. Automatic escalation applies to `scrape()` and `OmniClient`, not to crawls.

---

## Basic Spider Example

```python
import asyncio
from omniscrape import CrawlEngine, JSONLStorage, LinkExtractor, Request, Spider

links = LinkExtractor(same_domain=True)

class BooksSpider(Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    allowed_domains = ["books.toscrape.com"]
    concurrency = 8
    max_depth = 3

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield selector.extract({
                "title": "h1::text",
                "price": {"selector": "p.price_color::text", "type": "price"},
            })
        for url in links.extract(selector, response.url):
            yield Request(url)

stats = asyncio.run(
    CrawlEngine(
        BooksSpider(),
        storage=JSONLStorage("books.jsonl"),
        max_pages=200,
        queue_path="books-queue.db",
    ).run()
)
print(stats.to_dict())
```

---

## Key `CrawlEngine` Options

- **Politeness**: `obey_robots=True` (honors `robots.txt` rules and `Crawl-delay`), `per_domain_concurrency`, `download_delay`, `autothrottle=True`, plus automatic domain-wide `429 Retry-After` pauses via `DomainThrottle`.
- **Scope & budget**: `max_pages`, `max_depth`, `allowed_domains`.
- **Sitemap seeding**: Pass `start_from_sitemap=True` to seed the queue from the target site's sitemaps automatically, or call [`map_site`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/crawler/sitemap.py) standalone:
  ```python
  urls = await omniscrape.map_site("https://example.com", search="pricing", limit=200)
  ```
- **Pause & resume**: Pass `queue_path="crawl.db"` (or `use_checkpoint=True`) to persist the priority request queue and dedup state in SQLite (`resume=True` by default).
- **Item pipelines**: Pass `pipelines=[fn1, fn2]` to transform or drop (`return None`) yielded items before storage.
- **Streaming**: Use `async for item in engine.stream(): ...` instead of `.run()`.

From the command line, `omniscrape crawl URL --resume` turns on the same persistence; see [[CLI-Reference]].

---

## `LinkExtractor` Filtering

`LinkExtractor` outputs canonicalized, deduplicated absolute URLs while preserving directory trailing slashes to avoid unnecessary redirects:

```python
links = LinkExtractor(
    allow=[r"/products/"],
    deny=[r"/cart", r"/login"],
    restrict_css=["main", "nav.pagination"],
    same_domain=True,
    pages_only=True,
)
```

---

## Storage Backends

- **[`JSONLStorage`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/storage/jsonl_backend.py)**: Zero-dependency line-delimited JSON writer (`JSONLStorage("out.jsonl")`).
- **[`DuckDBStorage`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/storage/duckdb_backend.py)**: Analytical columnar storage (`pip install "omni-scraper[storage]"`), auto-creating tables from dict/Pydantic keys (`DuckDBStorage("out.duckdb", table_name="items")`).

---

## See also

- [[Selectors-and-Extraction]]: schemas to use inside `parse`.
- [[FAQ-and-Troubleshooting]]: `robots.txt` blocks and resuming crawls.

## Multi-Session Spiders

One spider can mix fetch configurations: fast HTTP for listing pages, a real browser for JavaScript pages, another
browser identity or proxy for a particular section. Declare named sessions and pick one per request:

```python
from omniscrape import Request, Spider, find_next_page, build_scrape_result

class Shop(Spider):
    name = "shop"
    start_urls = ["https://shop.example/catalog"]
    sessions = {
        "http": {"tier": 1, "impersonate": "chrome"},
        "browser": {"tier": 2, "wait_for": ".price"},
        "mobile": {"tier": 1, "impersonate": "safari_ios", "proxy": "http://p:8080"},
    }
    default_session = "http"

    async def parse(self, response, selector):
        for href in selector.css("a.product::attr(href)").getall():
            yield Request(href, session="browser", callback=self.parse_product)
        if (nxt := find_next_page(response.html, response.url)):
            yield Request(nxt)

    async def parse_product(self, response, selector):
        yield build_scrape_result(response).product
```

A session is a dict of `OmniClient.fetch` options: `tier`, `headers`, `proxy`, `timeout`, `allow_stealth`, and any
fetcher option (`impersonate`, `http_version`, `wait_for`, `actions`, ...). `Request(tier=...)` and request headers
still override the session. A misspelt `default_session` raises `ConfigError` before any request is sent, and the
session of every pending request is saved in the queue, so `--resume` keeps it.
