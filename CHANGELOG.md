# Changelog

## 0.2.0

OmniScrape now implements its capabilities natively instead of being a thin prototype. Every
number quoted below comes from the benchmark in `benchmarks/` (see `python -m benchmarks --help`).

### Breaking changes

- **Stealth escalation is opt-in.** A 403 or challenge page is returned to you as an access
  restriction. Pass `allow_stealth=True` to `fetch()`, `scrape()` or `OmniClient` to escalate to
  the stealth tier.
- **Links are absolute.** `ScrapeResult.links` contains absolute URLs (`https://site/cart`, not `/cart`).
- **`Product.currency` is `None`** when the page shows no currency (it used to default to `"USD"`).
- **`ScrapeResult.markdown` is main-content Markdown** (boilerplate removed). The same text is in
  `ScrapeResult.fit_markdown`; use `omniscrape.content.html_to_markdown` for whole-page Markdown.
- **`CrawlEngine(use_checkpoint=...)` defaults to `False`.** Pass `queue_path=` (or
  `use_checkpoint=True`) for a persistent, resumable queue. Resuming now continues unfinished crawls
  instead of skipping completed start URLs.
- **robots.txt is obeyed by default** in `CrawlEngine` and `map_site` (`obey_robots=False` to disable).
- `storage/parquet_backend.py` was renamed to `storage/jsonl_backend.py` (the old import still works).

### Added

- `OmniClient`: one fetch path with retries (transport errors, 429 with `Retry-After`, 5xx), circuit
  breaker, health-aware proxy pool and dead-letter queue. Fetcher registry for custom engines
  (`register_fetcher`), plus an optional `httpx` fetcher.
- Content pipeline (`omniscrape.content`): main-content extraction, Markdown renderer (tables, nested
  lists, fenced code, citations), `fit_markdown`, article metadata, BM25 filtering, chunking,
  token counting.
- Structured data (`parsers/structured.py`): JSON-LD, Microdata, RDFa Lite, OpenGraph, Dublin Core.
- Zero-config product extraction (`omniscrape.extract.extract_product`).
- Crawler: priority queue with SQLite persistence and resume, robots.txt and Crawl-delay,
  per-domain concurrency and AutoThrottle, `allowed_domains` / `max_depth` / `max_pages`, item
  pipelines, `stream()`, `LinkExtractor`, sitemap parsing and `map_site()`.
- Browser tier: DOM-settle readiness, page actions (click, type, press, scroll, infinite scroll,
  wait, evaluate, screenshot), screenshots and PDF, XHR/fetch JSON capture, shared-context mode with
  tab reuse, CDP attach and persistent profiles.
- Selector: `::text` / `::attr()`, `get`/`getall`/`re`/`re_first`, navigation, `find`/`find_all`,
  `find_similar`, selector generation, and built-in self-healing (`adaptive=True`, `auto_save`).
- Benchmark harness comparing OmniScrape with Scrapling, Crawl4AI, Scrapy, Crawlee, Trafilatura,
  Parsel, selectolax, BeautifulSoup, markdownify and html2text in isolated environments.

### Fixed

- Pages behind Cloudflare that load normally are no longer treated as blocked.
- Concurrent first requests no longer start one browser each.
- SQLite connections are closed (Windows file locks).
- Percent-encoded proxy credentials work in browser tiers.
- DNS and TLS failures are not retried; the circuit breaker counts blocked responses.
- `omniscrape.resilience` imports on Python 3.11 to 3.13.
