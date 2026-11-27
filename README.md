<div align="center">

# OmniScrape

**An adaptive, fast, and AI-ready Python web scraping framework — from zero-config extraction and self-healing selectors to polite concurrent crawls and stealth browser rendering.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/loganathan-ai-dev/Omni-Scrape/actions/workflows/ci.yml/badge.svg)](https://github.com/loganathan-ai-dev/Omni-Scrape/actions/workflows/ci.yml)

</div>

OmniScrape unifies **HTTP/2 TLS-impersonated fetching**, **Playwright & Camoufox browser rendering**, **100%-accurate self-healing selectors**, **zero-config product/article/listing extraction**, **LLM-ready Markdown**, **polite resumable crawling**, and a built-in **MCP server** behind a single, fast Python API.

```python
import omniscrape

page = omniscrape.scrape_sync("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
page.product.title, page.product.price, page.product.currency   # ('A Light in the Attic', 51.77, 'GBP')
print(page.markdown)                                             # main content only, as clean Markdown
```

---

## Key Features

- **⚡ Fast, Lazy-Imported Core**: `import omniscrape` loads in **~5 ms** with **26.6 MB** base RSS.
- **🛡️ 3-Tier Progressive Fetching**: Starts on `curl_cffi` HTTP/2 with browser TLS fingerprints (`tier=1`), auto-escalates empty JS shells to Playwright Chromium (`tier=2`), and supports opt-in stealth (`tier=3`, Camoufox or hardened Chromium with `allow_stealth=True`).
- **🩹 Self-Healing Selectors (100% Recovery)**: Remembers 12+ structural, context, and content signals per element and relocates targets automatically across class renames, tag swaps, wrappers, attribute churn, and value updates — while rejecting ambiguous ties.
- **🧠 Zero-Config & Schema Extraction**: Extract `Product`, `Article`, repeated listing cards (`extract_listings`), JSON-LD (with `@id` graph resolution), Microdata, RDFa, OpenGraph, or declarative `Selector.extract(schema)` dicts.
- **📄 LLM-Ready Markdown**: Boilerplate-stripped `fit_markdown` with `0.31%` leakage, BM25 query filtering, numbered citations, and token-bounded `chunk_markdown`.
- **🕷️ Polite Resumable Crawling & Batch APIs**: `CrawlEngine` with `robots.txt` compliance, `Crawl-delay`, domain-wide `429 Retry-After` pauses, `ETag`/`If-Modified-Since` caching, sitemap seeding (`start_from_sitemap=True`), SQLite pause/resume, and `fetch_many` / `scrape_many`.
- **🤖 CLI & MCP Server**: Built-in `omniscrape` CLI and FastMCP server (`stdio` or streamable HTTP) for AI agents.

---

## Install

Requires Python 3.11 or newer.

```bash
pip install "omniscrape @ git+https://github.com/loganathan-ai-dev/Omni-Scrape.git"
```

Optional extras:

| Extra | Adds | Install |
|---|---|---|
| `browser` | Playwright Chromium rendering, actions, screenshots, PDF | `pip install "omniscrape[browser] @ git+https://github.com/loganathan-ai-dev/Omni-Scrape.git"` then `playwright install chromium` |
| `stealth` | Camoufox for opt-in stealth (`tier=3`) | `[stealth]` |
| `fast` | Opt-in `selectolax` Lexbor CSS backend (`backend="selectolax"`) | `[fast]` |
| `httpx` | Alternative HTTP/2 client (`tier="httpx"`) | `[httpx]` |
| `storage` | DuckDB analytical storage | `[storage]` |
| `markdown` | Exact token counts with `tiktoken` | `[markdown]` |
| `mcp` | MCP server for AI agents | `[mcp]` |
| `all` | Core browser, stealth, httpx, storage, markdown, and MCP extras | `[all]` |

From source: `pip install -e ".[all,dev]"`.

---

## Quick Start

### Single Page & Batch Scraping

```python
import asyncio
import omniscrape

async def main():
    page = await omniscrape.scrape("https://quotes.toscrape.com/")
    print(page.title)          # page title
    print(page.markdown[:300]) # main-content Markdown, boilerplate removed
    print(page.links[:5])      # absolute links
    print(page.metadata)       # title, author, dates, site name, description, language

    # Concurrent batch scraping with per-domain politeness
    pages = await omniscrape.scrape_many(
        ["https://quotes.toscrape.com/page/1/", "https://quotes.toscrape.com/page/2/"],
        concurrency=4,
        per_domain_concurrency=2,
    )

asyncio.run(main())
```

### Fetching, Sessions, Retries & Caching

```python
from omniscrape import OmniClient, ProxyPoolManager
from omniscrape.resilience import CircuitBreaker, DeadLetterQueue

async with OmniClient(
    retries=2,                        # retries transport errors, 429 (Retry-After), and 5xx
    timeout=30,
    cache_responses=True,             # ETag / Last-Modified conditional 304 caching
    headers={"Accept-Language": "en-GB"},
    proxy_pool=ProxyPoolManager(["http://user:pass@p1:8080", "http://p2:8080"], strategy="round_robin"),
    circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=30),
    dead_letter=DeadLetterQueue("failed.db"),
) as client:
    res = await client.fetch("https://example.com/a")
    pages = await client.scrape_many(["https://example.com/b", "https://example.com/c"], concurrency=4)
```

Custom fetchers can be registered at runtime with `register_fetcher("my-api", MyApiFetcher)`.

### Browser Rendering & Stealth Actions

Both `tier=2` (`DynamicFetcher`) and `tier=3` (`StealthFetcher`) share the same readiness and action runner (`wait_for`, `actions`, `screenshot`, `pdf`, and `capture_network`):

```python
res = await omniscrape.fetch(
    "https://example.com/products",
    tier=2,
    wait_for=".product-card",
    actions=[
        {"type": "click", "selector": "button.load-more"},
        {"type": "infinite_scroll", "max_scrolls": 5},
        {"type": "type", "selector": "input[name=q]", "text": "lamp"},
        {"type": "press", "key": "Enter"},
        {"type": "evaluate", "script": "() => document.querySelectorAll('.product-card').length"},
    ],
    screenshot=True,
    capture_network=True,
)
```

Supported actions: `click`, `type`/`write`/`fill`, `press`, `scroll`, `infinite_scroll`, `wait`, `evaluate`, `screenshot`, and `scrape` (pass `"optional": True` to continue if an action fails). Use `OmniClient(fetcher_options={2: {"isolate": False}})` to reuse a single browser context and pooled tabs across requests.

### Selectors, Schema & Self-Healing

```python
from omniscrape import Selector

page = Selector(html, url="https://shop.example/list")

page.css("div.card h3::text").getall()
page.css("div.card a::attr(href)").get()
page.css("span.price").re(r"\$([\d.]+)")
page.xpath("//div[@data-sku='B2']/h3/text()").get()

# Declarative schema extraction with built-in type/currency/date/unit normalizers
item = page.extract({
    "title": "div.pdp h1::text",
    "price": {"selector": "div.pdp .price::text", "type": "price"},
    "tags": {"selector": "ul.tags li::text", "all": True},
})
```

Self-healing selectors survive class renames, wrapper insertions, tag swaps, attribute churn, and value updates:

```python
# First run: save structural + context fingerprint
page = Selector(html_v1, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
page.css(".price-current", identifier="price", auto_save=True)

# Later: selector broke after redesign -> relocated automatically
page = Selector(html_v2, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
page.css(".price-current", identifier="price", adaptive=True)[0].text
```

For pure-CSS high-throughput pipelines with `omniscrape[fast]`, pass `Selector(html, backend="selectolax")`.

### Zero-Config Products, Articles, Listings & Markdown

```python
from omniscrape import extract_product, extract_listings, extract_metadata, fit_markdown, chunk_markdown

product = extract_product(html, url)              # Product model (JSON-LD, Microdata, RDFa, OG, Shopify JSON, DOM)
listings = extract_listings(category_html, url)   # Repeated cards on category/search pages
meta = extract_metadata(html, url)                # title, author (with JSON-LD @id resolution), dates, tags
md = fit_markdown(html, url=url, query="pricing", citations=True, max_tokens=2000)
chunks = chunk_markdown(md, max_tokens=512)
```

### Crawling, Storage, CLI & MCP

```python
import asyncio
from omniscrape import CrawlEngine, JSONLStorage, LinkExtractor, Request, Spider

links = LinkExtractor(same_domain=True)

class Books(Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    concurrency = 8

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield {"title": selector.css("h1::text").get(), "price": selector.css("p.price_color::text").get()}
        for url in links.extract(selector, response.url):
            yield Request(url)

stats = asyncio.run(CrawlEngine(
    Books(),
    storage=JSONLStorage("books.jsonl"),
    max_pages=200,
    start_from_sitemap=False,
    queue_path="books-queue.db",  # SQLite pause/resume
).run())
```

CLI & MCP server:

```bash
omniscrape get https://books.toscrape.com/
omniscrape get https://books.toscrape.com/ -f markdown
omniscrape mcp                              # stdio MCP server
omniscrape mcp --transport http --port 8000 # streamable HTTP MCP server
```

---

## Benchmarks

Every benchmark runs in an **isolated Python 3.12 virtual environment** per tool (`benchmarks/`) on Windows 11 against the same offline corpus and local `aiohttp` test server. Ground truth for real pages comes from each site's own markup, never from another tool's output.

Latest verified run: `20261127-111900-enhanced-final` (OmniScrape `0.1.0` vs Scrapling `0.5.1` and Trafilatura `2.4.0`; baseline multi-tool comparisons from `20261126-183935-final`).

### Self-Healing Selectors (1,377 Broken Cases Across 60 Pages)

| Tool | Recovered | Wrong Element | Missed | Time / Page | Peak RSS |
|---|---:|---:|---:|---:|---:|
| **OmniScrape** | **100.0% (1,377/1,377)** | **0.0% (0)** | **0** | **28.1 ms** | **50.4 MB** |
| Scrapling 0.5.1 | 85.33% (1,175/1,377) | 14.67% (202) | 0 | 46.9 ms | 50.3 MB |

| Mutation Category | OmniScrape | Scrapling 0.5.1 |
|---|---:|---:|
| All classes renamed (`class_rename`) | **100%** | 100% |
| Content changed (`content_update`) | **100%** | 100% |
| IDs & data-* churned (`attr_churn`) | **100%** | 96.6% |
| Look-alike siblings inserted (`sibling_insert`) | **100%** | 92.9% |
| Element wrapped (`wrapper_insert`) | **100%** | 92.2% |
| Tag swapped (`tag_change`) | **100%** | 60.1% |
| Combined redesign (`combined`) | **100%** | 57.1% |

### Parsing, Crawling & JavaScript Rendering

| Suite | Metric | OmniScrape | Scrapling 0.5.1 |
|---|---|---:|---:|
| **Startup** | Cold `import` time / base RSS | **0.005 s / 26.6 MB** | 0.160 s / 31.6 MB |
| **Parse** (143 docs × 5) | Throughput / peak RSS | **387.7 docs/s** *(up to 495.6)* / 52.2 MB | 294.9 docs/s *(up to 420.6)* / 47.0 MB |
| **Crawl** (300 pages, conc=8, robots=True, 10 flaky 500s) | Pages/s / peak RSS | **175.3 pages/s** / **45.0 MB** | 158.2 pages/s / 59.0 MB |
| **Live Crawl** (`quotes.toscrape.com`, 20 pages, conc=2) | Pages/s / peak RSS | **4.02 pages/s** / **48.6 MB** | 3.72 pages/s / 61.9 MB |
| **Live Crawl** (`books.toscrape.com`, 40 pages, conc=2) | Pages/s / peak RSS | 4.46 pages/s / **48.6 MB** | **5.11 pages/s** / 61.9 MB |
| **JS Render** (60 pages, conc=4, cold batch) | Pages/s / peak RSS | **14.21 pages/s** *(isolated)* / **604 MB** | 7.16 pages/s / 1,039 MB |

*Crawl correctness (`OmniScrape` and `Scrapling`): 100% coverage (`321/321`), 0 `robots.txt` violations, 0 duplicate requests, 10/10 flaky HTTP 500s recovered.*

### Main-Content Markdown & Zero-Config Extraction

| Suite | Metric | OmniScrape | Trafilatura 2.4.0 |
|---|---|---:|---:|
| **Markdown** (66 docs) | Overall F1 / Holdout F1 | **0.9903 / 0.9854** | 0.9807 / 0.9811 |
| **Markdown** | Handwritten F1 / Leakage | **0.9838 / 0.31%** | 0.9602 / 0.96% |
| **Markdown** | ms/doc / Peak RSS | **14.8 ms / 51.9 MB** | 23.9 ms / 57.4 MB |
| **Extract** (126 docs) | Product F1 (all / holdout) | **1.000 / 1.000** | not supported |
| **Extract** | Article F1 (all / holdout) | **0.9418 / 0.8966** | 0.9003 / 0.8479 |
| **Extract** | ms/doc / Peak RSS | **41.4 ms / 57.2 MB** | 75.7 ms / 101.3 MB |

### Reproducing Benchmarks

```bash
pip install -e ".[dev,bench]"
python -m benchmarks envs       # build isolated Python 3.12 environments per tool (requires uv)
python -m benchmarks run        # run all 7 suites and build HTML report
python -m benchmarks compare benchmarks/results/<old> benchmarks/results/<new>
```

---

## Repository Layout

```text
Omni-Scrape/
├── src/omniscrape/
│   ├── __init__.py          # Lazy public API exports
│   ├── client.py            # OmniClient (fetch, scrape, fetch_many, scrape_many, ETag cache)
│   ├── classifier/          # Page type & anti-bot detection + escalation policy
│   ├── fetchers/            # FastFetcher (curl_cffi), DynamicFetcher (Playwright), StealthFetcher, ProxyPool
│   ├── parsers/             # Selector (lxml + opt-in selectolax), AdaptiveEngine, SemanticExtractor, Structured
│   ├── content/             # Main-content extraction, Markdown, metadata, chunking, BM25 filtering
│   ├── extract/             # Zero-config Product and Listing extraction
│   ├── crawler/             # CrawlEngine, Spider, LinkExtractor, RobotsCache, DomainThrottle, Sitemaps
│   ├── normalizers/         # Currency, unit, date, and Markdown normalizers
│   ├── resilience/          # Retry, CircuitBreaker, DeadLetterQueue
│   ├── storage/             # JSONLStorage, DuckDBStorage
│   ├── cli/ & mcp/          # Click/Rich CLI and FastMCP server
├── tests/                   # Unit and local-server integration tests (95+ tests)
├── benchmarks/              # Isolated multi-tool benchmark harness & corpus
├── .github/workflows/ci.yml # GitHub Actions CI
├── pyproject.toml           # Package configuration & optional extras
├── CHANGELOG.md             # Release notes
└── LICENSE                  # MIT License
```

---

## Responsible Use

- **robots.txt**: `CrawlEngine` and `map_site` obey `robots.txt` (including `Crawl-delay`) by default.
- **Access restrictions**: Blocked responses are returned with `defense_detected` populated. OmniScrape does not solve CAPTCHAs or bypass interactive challenges; tier 3 (`StealthFetcher`) runs only when `allow_stealth=True` or `tier=3` is explicitly requested.
- **Rate limits & terms**: `DomainThrottle` coordinates `Retry-After` cooldowns across workers. Respect site terms and prefer official APIs when available.

---

## Development

```bash
git clone https://github.com/loganathan-ai-dev/Omni-Scrape.git && cd Omni-Scrape
pip install -e ".[dev,browser,mcp]" && playwright install chromium
pytest -v
```
