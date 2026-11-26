# Changelog

## 0.1.0 — first release

### Fetching
- Three fetch tiers: curl_cffi HTTP with browser TLS fingerprints, Playwright Chromium, and an opt-in
  stealth tier (Camoufox or hardened Chromium). Automatic escalation from HTTP to the browser for
  JavaScript-only pages; escalation to stealth only with `allow_stealth=True`.
- `OmniClient`: reusable client with retries (transport errors, HTTP 429 with `Retry-After`, 5xx),
  circuit breaker, health-aware proxy pool and dead-letter queue.
- Fetcher registry for custom engines (`register_fetcher`) and an optional httpx fetcher.

### Browser
- Readiness based on the page settling, not fixed sleeps; `wait_for` selectors.
- Page actions: click, type, press, scroll, infinite scroll, wait, evaluate, screenshot, HTML snapshots.
- Screenshots, PDF, capture of the JSON a page loads from its API.
- Shared-context mode with tab reuse, CDP attach, persistent profiles.

### Parsing and extraction
- `Selector` with CSS (`::text`, `::attr()`) and XPath, `get`/`getall`/`re`, navigation,
  `find`/`find_all`, `find_similar` and selector generation.
- Self-healing selectors (`adaptive=True`, `auto_save=True`) that survive class renames, wrappers and
  tag changes, and refuse ambiguous matches.
- Structured data: JSON-LD, Microdata, RDFa, OpenGraph, Dublin Core.
- Zero-config product extraction and article metadata.
- Main-content Markdown (`fit_markdown`), whole-page Markdown, citations, BM25 query filtering,
  chunking and token counting.

### Crawling
- `CrawlEngine` with robots.txt (on by default), priority queue, SQLite persistence and resume,
  per-domain concurrency and AutoThrottle, depth/page/domain limits, pipelines and streaming.
- `LinkExtractor`, URL canonicalization, sitemap parsing and `map_site()`.

### Interfaces
- `omniscrape get` command line, and an MCP server (`omniscrape mcp`) over stdio or HTTP with
  `scrape_url`, `scrape_product`, `scrape_article`, `get_markdown` and `map_site` tools.
- JSONL and DuckDB storage.

### Benchmarks
- `benchmarks/`: a reproducible comparison with Scrapling, Crawl4AI, Scrapy, Crawlee, Trafilatura,
  Parsel, selectolax, BeautifulSoup, markdownify and html2text, each in an isolated environment.
  Results are in the README.
