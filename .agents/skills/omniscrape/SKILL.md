---
name: omniscrape
description: Use OmniScrape cleanly for web fetching, JS browser rendering, stealth escalation, self-healing CSS/XPath selectors, structured extraction (products, articles, listings, schemas), LLM-ready Markdown, polite resumable crawling, CLI usage, and MCP server integration. Activate whenever writing or debugging code that scrapes pages, parses HTML, runs spiders, or connects AI agents to OmniScrape.
---

# OmniScrape Skill

Use OmniScrape as a layered pipeline: pick the lightest tool that solves the target site, reuse sessions/clients for multiple URLs, and rely on built-in extractors before writing custom regexes.

Read [references/api_cheatsheet.md](./references/api_cheatsheet.md) when you need full parameter lists for `OmniClient`, browser `actions`, `Selector.extract` schemas, `CrawlEngine`, or MCP tool signatures.

---

## 1. Choose the Right Entry Point

| Goal | Best API / Command | Notes |
|---|---|---|
| One-off async scrape | `await omniscrape.scrape(url)` | Auto-escalates empty JS shells from tier 1 → tier 2 |
| One-off sync scrape | `omniscrape.scrape_sync(url)` | Wraps `asyncio.run(scrape(...))` |
| Many URLs concurrently | `await omniscrape.fetch_many(urls, ...)` / `scrape_many(...)` | Shares one `OmniClient` + per-domain throttling |
| Long-lived session / custom config | `async with OmniClient(...) as client:` | Reuses TLS session, browser instance, `cache_responses=True` (304) |
| Custom HTML parsing / CSS / XPath | `Selector(html, url=url)` | Supports `::text`, `::attr(href)`, `.re()`, `.extract(schema)`, `adaptive=True` |
| High-speed pure CSS parsing | `Selector(html, backend="selectolax")` | Requires `omniscrape[fast]` (`selectolax`) |
| Zero-config commerce / news | `extract_product(html, url)` / `extract_listings(html, url)` / `scrape_article(url)` | Uses JSON-LD (`@id` resolved), Microdata, RDFa, OG, Shopify JSON, DOM |
| RAG / LLM context | `fit_markdown(html, url=url, query=..., citations=True, max_tokens=...)` + `chunk_markdown(md)` | Strips nav/footer/boilerplate and filters blocks with BM25 |
| Multi-page crawl | `CrawlEngine(spider, storage=..., max_pages=..., queue_path=...)` | Obeys `robots.txt`, `Crawl-delay`, dedup, SQLite pause/resume |
| URL discovery | `await omniscrape.map_site(url, search=..., limit=...)` | Reads `robots.txt` sitemaps + `/sitemap.xml` + start page links |
| Quick CLI / Agent MCP | `omniscrape get <url> -f markdown` / `omniscrape mcp` | Tools: `scrape_url`, `scrape_product`, `scrape_article`, `get_markdown`, `map_site` |

---

## 2. Fetching Tiers & Resilience

OmniScrape has three progressive tiers (plus optional `httpx` HTTP/2):

- **Tier 1 (`tier=1` / `"http"` — `FastFetcher`)**: `curl_cffi` HTTP/2 with browser TLS impersonation. Always start here (or leave `tier=None` for auto mode).
- **Tier 2 (`tier=2` / `"browser"` — `DynamicFetcher`)**: Playwright Chromium. Auto mode escalates here automatically when Tier 1 returns an empty SPA shell. One browser launches lazily per fetcher, with isolated contexts per request (or `fetcher_options={2: {"isolate": False}}` for pooled shared-context speed).
- **Tier 3 (`tier=3` / `"stealth"` — `StealthFetcher`)**: Camoufox (if `omniscrape[stealth]` is installed) or hardened Playwright Chromium. Only triggered on blocks when `allow_stealth=True` or forced via `tier=3`.

```python
from omniscrape import OmniClient, ProxyPoolManager
from omniscrape.resilience import CircuitBreaker, DeadLetterQueue

async with OmniClient(
    retries=2,
    timeout=30.0,
    cache_responses=True,  # ETag / Last-Modified conditional 304 caching
    proxy_pool=ProxyPoolManager(["http://user:pass@p1:8080", "http://p2:8080"], strategy="round_robin"),
    circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=30),
    dead_letter=DeadLetterQueue("failed.db"),
) as client:
    res = await client.fetch("https://example.com/app", tier=2, wait_for=".item-card", screenshot=True)
```

### Guardrails
- **Never** bypass login walls, paywalls, or solve/bypass CAPTCHAs or anti-bot challenges. If `res.defense_detected != DefenseSystem.NONE` and `allow_stealth=True` still lands on a challenge, report the access restriction and stop.
- For multiple URLs, always reuse `OmniClient` or call `fetch_many` / `scrape_many` instead of calling `omniscrape.scrape()` in a loop (which tears down sessions and browsers on every URL).

---

## 3. Selectors, Schemas & Self-Healing

Prefer `Selector` over BeautifulSoup loops:

```python
from omniscrape import Selector

sel = Selector(html, url="https://shop.example/p/1")
title = sel.css("h1::text").get()
links = sel.css("a.product::attr(href)").getall()
prices = sel.css("span.price").re(r"[\d,.]+")

item = sel.extract({
    "title": "h1::text",
    "price": {"selector": ".price::text", "type": "price"},
    "published": {"selector": "time::attr(datetime)", "type": "date"},
    "tags": {"selector": "ul.tags li::text", "all": True},
})
```

For fragile targets across site redesigns, enable `adaptive=True` with persistent SQLite storage:

```python
# Baseline run: record 12+ element signals
s1 = Selector(html_v1, url=url, adaptive=True, storage="fingerprints.db")
s1.css(".price-box .now", identifier="price", auto_save=True)

# After markup changes: relocate automatically
s2 = Selector(html_v2, url=url, adaptive=True, storage="fingerprints.db")
price_el = s2.css(".price-box .now", identifier="price", adaptive=True)[0]
```

---

## 4. Crawling Pattern

Subclass `Spider`, keep `LinkExtractor(same_domain=True)` scoped, and pass `CrawlEngine` a storage backend and `queue_path` if pause/resume is needed:

```python
import asyncio
from omniscrape import CrawlEngine, JSONLStorage, LinkExtractor, Request, Spider

links = LinkExtractor(same_domain=True, allow=[r"/catalogue/"])

class CatalogSpider(Spider):
    name = "catalog"
    start_urls = ["https://books.toscrape.com/"]
    concurrency = 8

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield selector.extract({
                "title": "h1::text",
                "price": {"selector": "p.price_color::text", "type": "price"},
            })
        for next_url in links.extract(selector, response.url):
            yield Request(next_url)

stats = asyncio.run(
    CrawlEngine(
        CatalogSpider(),
        storage=JSONLStorage("out.jsonl"),
        max_pages=200,
        start_from_sitemap=False,
        queue_path="catalog-queue.db",
    ).run()
)
```

---

## 5. MCP & CLI Integration

Start the MCP server for Claude Desktop, Cursor, or Antigravity:

```bash
pip install "omniscrape[mcp]"
omniscrape mcp                              # stdio transport
omniscrape mcp --transport http --port 8000 # streamable HTTP at /mcp
```

Quick CLI inspection:

```bash
omniscrape get https://example.com -f markdown
omniscrape get https://example.com -f json --tier 2
```
