# OmniScrape

A Python web scraping framework that fetches, renders, crawls and extracts without depending on
other scraping frameworks. Every capability is implemented natively and measured against the
specialist tools in a reproducible benchmark (`benchmarks/`).

## Install

```bash
pip install -e .                     # core: HTTP fetching, parsing, extraction, crawling
pip install -e ".[browser]"          # + JavaScript rendering (then: playwright install chromium)
pip install -e ".[all]"              # everything optional
```

Python 3.11 or newer.

## Quick start

```python
import asyncio, omniscrape

async def main():
    page = await omniscrape.scrape("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
    print(page.title)
    print(page.product)          # zero-config product: title, price, currency, availability, ...
    print(page.markdown[:500])   # main-content Markdown, boilerplate removed

asyncio.run(main())
```

### Selectors (Parsel/Scrapling style) and self-healing

```python
from omniscrape import Selector

page = Selector(html, url="https://shop.example/item", adaptive=True)
page.css("h1::text").get()
page.css("span.price").re_first(r"[\d.,]+")
page.css(".price", auto_save=True)          # remember the element
# ... after a redesign renames classes or changes tags:
page.css(".price", adaptive=True)           # relocated from its stored fingerprint
```

### Crawling

```python
from omniscrape import CrawlEngine, LinkExtractor, Request, Spider, JSONLStorage

links = LinkExtractor(same_domain=True)

class Books(Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    concurrency = 4

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield {"title": selector.css("h1::text").get(), "price": selector.css("p.price_color::text").get()}
        for url in links.extract(selector, response.url):
            yield Request(url)

stats = asyncio.run(CrawlEngine(Books(), storage=JSONLStorage("books.jsonl"), max_pages=200,
                                queue_path="books-queue.db").run())   # resumable
```

robots.txt is obeyed by default. Other building blocks: `map_site(url)` for fast URL discovery,
`fit_markdown(html, query=...)`, `chunk_markdown(md)`, `extract_metadata(html)`.

### Browser rendering and page actions

```python
res = await omniscrape.fetch("https://example.com/app", tier=2, wait_for=".loaded", actions=[
    {"type": "click", "selector": "button.more"},
    {"type": "infinite_scroll", "max_scrolls": 5},
], screenshot=True, capture_network=True)
res.network        # JSON responses the page loaded from its API
```

## What it does

| Area | Capabilities |
|---|---|
| Fetching | `curl_cffi` HTTP with browser TLS fingerprints; Playwright rendering; opt-in stealth tier; automatic escalation for JavaScript-only pages; retries, circuit breaker, proxy pool, dead-letter queue |
| Browser | DOM-settle readiness, page actions, screenshots and PDF, API JSON capture, shared-context mode with tab reuse, CDP attach, persistent profiles |
| Parsing | CSS (`::text`, `::attr()`) and XPath, `get`/`getall`/`re`, navigation, `find`/`find_all`, `find_similar`, selector generation |
| Self-healing | Structural fingerprints, relocation across class renames, wrapper insertion, tag changes; ambiguous matches are rejected |
| Extraction | JSON-LD, Microdata, RDFa, OpenGraph, Dublin Core; zero-config products; article metadata |
| Content | Main-content extraction, Markdown (tables, code, citations), BM25 filtering, chunking, token counting |
| Crawling | Priority queue, persistence and resume, robots.txt and Crawl-delay, per-domain throttling, scope limits, pipelines, streaming, sitemaps |

## Benchmark (run `python -m benchmarks run`)

Measured on Windows 11, each tool in its own Python 3.12 environment and process, at commit
`acb9456`. "Holdout" pages were never used for tuning: 37 real-world pages from scraping sandboxes,
public-domain and openly licensed sites, plus generated pages in layouts not used for tuning.

| Task | OmniScrape | Best other tool |
|---|---|---|
| Product extraction F1 (holdout) | **1.000** | none of the compared tools extracts products without selectors |
| Article metadata F1 (holdout) | **0.897** | Trafilatura 0.848 |
| Main-content Markdown F1 (holdout) | **0.985** | Trafilatura 0.981 |
| Boilerplate leakage | **0.3%** | Trafilatura 1.0% |
| Self-healing: element recovered after a redesign | **99.6%** (0.4% wrong) | Scrapling 85.3% (14.7% wrong) |
| CSS parse + select | 455 docs/s | selectolax 1,889; Scrapling 421–475 across runs; lxml 386 |
| Crawl, 300-page local site (concurrency 8) | 150 pages/s, 46 MB | Scrapling 179 pages/s; Scrapy 123 |
| Crawl correctness | 100% coverage, 0 robots violations, 0 duplicates, 10/10 flaky pages recovered | same for Scrapling, Crawlee |
| JavaScript rendering (60 pages, concurrency 4) | 13.3 pages/s shared context; 11.0 isolated (604 MB) | Scrapling 14.5; Crawl4AI 7.2 |

Limits of these numbers: the corpus is small next to published extractor evaluations (Trafilatura's
uses 990 documents); the mutation cases for self-healing were written by the OmniScrape authors;
timings vary between runs and machines. Compiled tools (for example Spider in Rust, Lightpanda in Zig)
are not compared.

Features were rebuilt from the public documentation of other projects (Scrapling, Crawl4AI,
Firecrawl, Crawlee, Scrapy, Trafilatura, Extruct and others), not from their source code.

## Not included

No CAPTCHA or Cloudflare challenge solving. The stealth tier is opt-in (`allow_stealth=True`) and a
blocked response is returned to you as an access restriction.

## Development

```bash
pip install -e ".[dev,browser]" && playwright install chromium
pytest                                # unit + integration tests (local test site, no internet)
python -m benchmarks envs             # isolated competitor environments (uv)
python -m benchmarks run --quick      # benchmark smoke run
python -m benchmarks.dev_eval         # tune extractors on the dev split only
```
