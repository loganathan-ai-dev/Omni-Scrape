# Changelog

## 0.1.0 — Initial Release

### Fetching & Client
- Three progressive fetch tiers: `curl_cffi` HTTP/2 with browser TLS fingerprints (`tier=1`), Playwright Chromium (`tier=2`), and opt-in `StealthFetcher` (`tier=3`, Camoufox or hardened Chromium via `allow_stealth=True`).
- `OmniClient` with exponential backoff retries (`429 Retry-After` and `5xx`), per-domain circuit breaker, health-aware `ProxyPoolManager`, dead-letter queue, conditional `ETag`/`Last-Modified` (`304`) caching, and concurrent `fetch_many` / `scrape_many` / `iter_scrape` batch APIs.
- Lazy top-level package exports (`~5 ms` import time) and pluggable custom fetcher registry (`register_fetcher`).

### Browser & Stealth
- Shared Playwright runner for both `DynamicFetcher` and `StealthFetcher` supporting DOM settle readiness, `wait_for`, firecrawl-style `actions`, screenshots, PDF export, and XHR/fetch JSON network capture.
- Context reuse with bounded tab pooling (`max_idle_pages=4`, `recycle_after=25`), CDP attach, and persistent profiles.
- Soft-block detection for Cloudflare, DataDome, PerimeterX, Akamai, Kasada, and AWS WAF.

### Parsing, Self-Healing & Extraction
- `Selector` with cached CSS (`::text`, `::attr()`) and XPath queries, traversal, `find`/`find_all`, `find_similar`, declarative `Selector.extract(schema)`, and optional `backend="selectolax"` (`[fast]` extra).
- `AdaptiveEngine` with single-pass top-down DFS similarity relocation and in-memory fingerprint caching (`100%` recovery across 1,377 redesign test cases).
- Structured data extraction (JSON-LD with `@graph`/`@id` resolution, Microdata, RDFa, OpenGraph, Dublin Core), zero-config `extract_product`, `extract_listings`, `extract_metadata`, `fit_markdown`, BM25 filtering, and `chunk_markdown`.

### Crawling, Storage, CLI & MCP
- `CrawlEngine` with `robots.txt` compliance, domain-wide `429`/`503` `Retry-After` pauses, priority queue with SQLite pause/resume, `AutoThrottle`, `start_from_sitemap`, `LinkExtractor` (preserving trailing slashes to avoid redirect roundtrips), pipelines, and streaming.
- JSONL and DuckDB storage backends, Click/Rich CLI (`omniscrape get`, `omniscrape mcp`), and FastMCP server over stdio or streamable HTTP.
