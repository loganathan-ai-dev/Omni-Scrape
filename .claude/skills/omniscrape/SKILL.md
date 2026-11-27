---
name: omniscrape
description: Use OmniScrape cleanly for web fetching, JS browser rendering, stealth escalation, self-healing CSS/XPath selectors, structured extraction (products, articles, listings, schemas), LLM-ready Markdown, polite resumable crawling, CLI usage, and MCP server integration. Activate whenever writing or debugging code that scrapes pages, parses HTML, runs spiders, or connects Claude Code / MCP agents to OmniScrape.
---

# OmniScrape Skill (Claude Code)

Use OmniScrape as a layered pipeline: pick the lightest tier that works for the target site, reuse `OmniClient` or batch helpers across multiple URLs, and rely on built-in extractors before hand-writing brittle regexes.

See [references/api_cheatsheet.md](./references/api_cheatsheet.md) for verified parameters across `OmniClient`, browser `actions`, `Selector.extract`, `CrawlEngine`, and MCP tools.

---

## 1. Pick the Right Entry Point

| Task | Recommended API / Command | Why |
|---|---|---|
| Single async page scrape | `await omniscrape.scrape(url)` | Auto-escalates empty JS shells from tier 1 → tier 2 |
| Single sync page scrape | `omniscrape.scrape_sync(url)` | Convenience wrapper over `asyncio.run(scrape(...))` |
| Concurrent batch URLs | `await omniscrape.fetch_many(urls)` / `scrape_many(urls)` | Shares one `OmniClient` + per-domain throttling |
| Session reuse / caching / proxies | `async with OmniClient(...) as client:` | Reuses TLS & Playwright browser; supports `cache_responses=True` (304) |
| Custom DOM parsing | `Selector(html, url=url)` | `::text`, `::attr(href)`, `.re()`, `.extract(schema)`, `adaptive=True` |
| High-speed CSS-only parsing | `Selector(html, backend="selectolax")` | Requires `omniscrape[fast]` |
| E-commerce / articles | `extract_product(html, url)`, `extract_listings(html, url)`, `scrape_article(url)` | JSON-LD (`@id` resolved), Microdata, RDFa, OG, Shopify JSON, DOM |
| LLM / RAG Markdown | `fit_markdown(html, url=url, query=..., citations=True, max_tokens=...)` + `chunk_markdown(md)` | Removes boilerplate + optional BM25 filtering |
| Resumable site crawl | `CrawlEngine(spider, storage=..., max_pages=..., queue_path=...)` | Obeys `robots.txt`, `Crawl-delay`, dedup, SQLite checkpointing |
| Sitemap / URL discovery | `await omniscrape.map_site(url, search=..., limit=...)` | Uses `robots.txt` sitemaps + `/sitemap.xml` + links |
| Terminal & MCP server | `omniscrape get <url> -f markdown` / `omniscrape mcp` | Exposes `scrape_url`, `scrape_product`, `scrape_article`, `get_markdown`, `map_site` |

---

## 2. Fetching Tiers & Resilience

- **Tier 1 (`tier=1` / `"http"` — `FastFetcher`)**: `curl_cffi` HTTP/2 with browser TLS fingerprints. Default starting point.
- **Tier 2 (`tier=2` / `"browser"` — `DynamicFetcher`)**: Playwright Chromium. Auto mode escalates here if Tier 1 gets an empty JS shell. One browser per fetcher, fresh context per request (`fetcher_options={2: {"isolate": False}}` shares one context for extra speed).
- **Tier 3 (`tier=3` / `"stealth"` — `StealthFetcher`)**: Camoufox (with `omniscrape[stealth]`) or hardened Chromium. Only used on blocks when `allow_stealth=True` or explicitly requested via `tier=3`.

```python
from omniscrape import OmniClient, ProxyPoolManager
from omniscrape.resilience import CircuitBreaker, DeadLetterQueue

async with OmniClient(
    retries=2,
    timeout=30.0,
    cache_responses=True,
    proxy_pool=ProxyPoolManager(["http://user:pass@p1:8080", "http://p2:8080"], strategy="round_robin"),
    circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=30),
    dead_letter=DeadLetterQueue("failed.db"),
) as client:
    res = await client.fetch("https://example.com/app", tier=2, wait_for=".item-card", screenshot=True)
```

### Guardrails
- Do **not** use OmniScrape to bypass authentication, paywalls, or CAPTCHA / anti-bot challenges. If `res.defense_detected != DefenseSystem.NONE` persists under `allow_stealth=True`, stop and surface the access restriction.
- Avoid calling `omniscrape.scrape()` inside loops; reuse one `OmniClient` or use `fetch_many` / `scrape_many`.

---

## 3. Selectors, Schemas & Self-Healing

```python
from omniscrape import Selector

sel = Selector(html, url="https://shop.example/p/1")
title = sel.css("h1::text").get()
hrefs = sel.css("a.product::attr(href)").getall()

item = sel.extract({
    "title": "h1::text",
    "price": {"selector": ".price::text", "type": "price"},
    "published": {"selector": "time::attr(datetime)", "type": "date"},
    "tags": {"selector": "ul.tags li::text", "all": True},
})
```

Self-healing selectors survive class renames, tag swaps, wrapper elements, and attribute churn:

```python
s1 = Selector(html_v1, url=url, adaptive=True, storage="fingerprints.db")
s1.css(".price-box .now", identifier="price", auto_save=True)

s2 = Selector(html_v2, url=url, adaptive=True, storage="fingerprints.db")
price_el = s2.css(".price-box .now", identifier="price", adaptive=True)[0]
```

---

## 4. Crawling & Storage

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
        queue_path="catalog-queue.db",
    ).run()
)
```

---

## 5. Claude Code MCP Setup

Add OmniScrape as an MCP server for Claude Code after installing `pip install "omniscrape[mcp]"`:

```bash
claude mcp add omniscrape -- omniscrape mcp
```

Or run the streamable HTTP server at `http://127.0.0.1:8000/mcp`:

```bash
omniscrape mcp --transport http --port 8000
```
