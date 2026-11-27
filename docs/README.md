# OmniScrape Documentation

Welcome to the OmniScrape user and developer documentation.

OmniScrape is structured around five composable layers under `src/omniscrape/` with PEP 562 lazy imports so cold `import omniscrape` stays around ~5 ms:

```text
  URL / HTML
      │
      ▼
  [1. Fetch & Escalate]   OmniClient · FastFetcher (tier 1) · DynamicFetcher (tier 2) · StealthFetcher (tier 3)
      │
      ▼
  [2. Classify & Detect]  PageClassifier · SPA shell & WAF/soft-block detection · EscalationStrategy
      │
      ▼
  [3. Parse & Extract]    Selector (CSS/XPath/selectolax) · AdaptiveEngine · Product/Article/Listings · Normalizers
      │
      ▼
  [4. LLM Content]        extract_main · fit_markdown · BM25 filter · chunk_markdown · citations
      │
      ▼
  [5. Crawl & Expose]     CrawlEngine · Spider · LinkExtractor · map_site · JSONL/DuckDB · CLI & FastMCP
```

## Guides

1. **[Fetching, Sessions & Stealth](fetching-and-stealth.md)** — Tier 1/2/3 engines, auto-escalation, `OmniClient`, `fetch_many` / `scrape_many`, conditional `ETag`/`304` caching, proxy rotation, circuit breakers, DLQ, browser actions, and custom fetchers.
2. **[Selectors, Schemas & Extraction](selectors-and-extraction.md)** — CSS/XPath pseudo-elements, opt-in `selectolax` backend, self-healing `adaptive=True` selectors, declarative `Selector.extract(schema)`, zero-config `extract_product`, `extract_listings`, `extract_metadata`, and normalizers.
3. **[Crawling, Sitemaps & Storage](crawling-and-storage.md)** — Building `Spider` classes, `CrawlEngine`, `LinkExtractor`, `map_site`, `robots.txt` & `Crawl-delay`, domain-wide `429 Retry-After` pauses, SQLite checkpoint/resume, and `JSONLStorage` / `DuckDBStorage`.
4. **[LLM Markdown, CLI & AI Agent Skills](markdown-and-agents.md)** — Main-content `fit_markdown`, BM25 query filtering, `chunk_markdown`, CLI commands, FastMCP server (`stdio` / HTTP), and repository skills for Antigravity (`.agents/skills/omniscrape/`) and Claude Code (`.claude/skills/omniscrape/`).

## Quick Install Reference

```bash
pip install "omniscrape @ git+https://github.com/loganathan-ai-dev/Omni-Scrape.git"
```

| Extra | Purpose |
|---|---|
| `[browser]` | Playwright Chromium rendering (`DynamicFetcher`) — run `playwright install chromium` |
| `[stealth]` | Camoufox engine (`StealthFetcher`) |
| `[fast]` | `selectolax` Lexbor CSS backend (`Selector(..., backend="selectolax")`) |
| `[httpx]` | Optional `httpx` HTTP/2 fetcher (`tier="httpx"`) |
| `[storage]` | `DuckDBStorage` analytical storage |
| `[markdown]` | Exact token counting via `tiktoken` |
| `[mcp]` | FastMCP server (`omniscrape mcp`) |
| `[all]` | Browser, stealth, httpx, storage, markdown, and MCP extras |
| `[dev]` | Test dependencies (`pytest`, `pytest-asyncio`, `aiohttp`) |
