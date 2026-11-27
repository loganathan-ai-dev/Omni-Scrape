# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-27

First public release. Published on PyPI as **`omni-scraper`** (`import omniscrape`, command `omniscrape`).

### Added
- Three-tier fetching: `curl_cffi` HTTP with a browser TLS fingerprint, Playwright rendering with a shared
  action runner, and an opt-in stealth tier (Camoufox or hardened Chromium).
- Adaptive (self-healing) selectors with SQLite fingerprint storage.
- `Selector` with CSS, XPath, text/regex search, DOM navigation, `find_similar`, and declarative
  `extract(schema)` with price, date, unit and number normalizers. Optional `selectolax` CSS backend.
- Zero-config `Product`, `Article` and listing extraction; JSON-LD, Microdata, RDFa and OpenGraph parsing.
- LLM-ready Markdown: `fit_markdown`, BM25 query filtering, citations, `chunk_markdown`.
- `CrawlEngine` and `Spider`: concurrency, per-domain throttling, AutoThrottle, `robots.txt`, `Retry-After`,
  sitemap seeding, SQLite pause/resume, streaming, item pipelines, `JSONLStorage` and `DuckDBStorage`.
- Resilience: retries with backoff, circuit breaker, dead-letter queue, proxy pool (round-robin, random, sticky).
- CLI: `get`, `crawl`, `map`, `extract`, `shell`, `mcp`. MCP server with five tools.
- Agent skill (`.claude/skills`, `.agents/skills`), a Claude Code plugin (`.claude-plugin/`) that bundles the skill and the MCP server.
- Reproducible benchmark harness under `benchmarks/` with the published run in `benchmarks/published/`.

### Fixed
- Logging now goes to **stderr**; it previously wrote JSON log lines to stdout, which corrupted
  `omniscrape get -f json` and the MCP stdio transport.
- `robots.txt` matching supports `*` and `$` wildcards, picks the most specific user-agent group and merges
  repeated groups for it (RFC 9309), compares paths after percent-encoding normalisation, and reads
  `Crawl-delay` / `Request-rate` from the same group as the path rules.
- `TableParser.parse_table` no longer returns the `<thead>` header row as a data row.
- `Selector.find_by_text` / `find_by_regex` return the innermost matching elements instead of every ancestor.
- `Selector(backend="selectolax")`: root-level element methods no longer fail before the lxml tree is built.
- Crawler callbacks receive `Selector(..., url=...)` and `Request.meta` is delivered as `response.meta`.
- `fetch_many` cancels the remaining downloads when one fails and exceptions are not collected;
  `iter_scrape` does the same when a download fails or the caller stops iterating early.
- A resumed crawl keeps each request's `tier` override (it is now stored in the SQLite queue).
- MCP `get_markdown` reports HTTP errors and anti-bot challenge pages (including ones served with HTTP 200)
  instead of returning them as page content, and forwards `allow_stealth`.
- `JSONLStorage` is line-buffered and reusable after `close()`; `DuckDBStorage` accepts records whose keys
  differ from the first record's, including keys that differ only in letter case.
- `BaseFetcher` is now listed in `omniscrape.__all__`.

### Removed
- Unused code: `AutoThrottle` (superseded by `DomainThrottle`), `CheckpointManager`, `URLFilter`,
  `FetcherSession`, `DensityAnalyzer.extract_main_content`, `Spider.stealth`, and the never-populated
  `Product.original_price`, `discount_percent`, `specifications` and `category_path` fields.
- The unused core dependencies `orjson` and `beautifulsoup4`.

[Unreleased]: https://github.com/loganathan-ai-dev/Omni-Scrape/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/loganathan-ai-dev/Omni-Scrape/releases/tag/v0.1.0
