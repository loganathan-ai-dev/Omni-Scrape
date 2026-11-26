# OmniScrape

OmniScrape is a Python web scraping framework. It fetches pages over HTTP or in a real browser,
extracts products, articles and structured data without per-site selectors, turns pages into clean
Markdown for LLMs, re-finds elements after a site redesign, and crawls whole sites politely.

Every capability is implemented in OmniScrape itself and measured against specialist tools
(Scrapling, Crawl4AI, Trafilatura, Scrapy, Crawlee and others) in the included benchmark.
See [Benchmarks](#benchmarks).

```python
import omniscrape

page = omniscrape.scrape_sync("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
page.product.title, page.product.price, page.product.currency   # ('A Light in the Attic', 51.77, 'GBP')
print(page.markdown)                                             # main content only, as Markdown
```

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Fetching pages](#fetching-pages)
- [Browser rendering and page actions](#browser-rendering-and-page-actions)
- [Selectors](#selectors)
- [Self-healing selectors](#self-healing-selectors)
- [Products, articles and structured data](#products-articles-and-structured-data)
- [Markdown for LLMs](#markdown-for-llms)
- [Crawling](#crawling)
- [Storage](#storage)
- [Command line](#command-line)
- [MCP server for AI agents](#mcp-server-for-ai-agents)
- [Utilities](#utilities)
- [Benchmarks](#benchmarks)
- [Responsible use](#responsible-use)
- [Development](#development)

## Install

OmniScrape needs Python 3.11 or newer.

```bash
pip install "omniscrape @ git+https://github.com/loganathan-ai-dev/Omni-Scrape.git"
```

Optional extras add features on top of the core install:

| Extra | Adds | Install |
|---|---|---|
| `browser` | JavaScript rendering, page actions, screenshots (Playwright) | `pip install "omniscrape[browser] @ git+https://github.com/loganathan-ai-dev/Omni-Scrape.git"` then `playwright install chromium` |
| `stealth` | Camoufox for the opt-in stealth tier | `[stealth]` |
| `httpx` | An alternative HTTP/2 client (`tier="httpx"`) | `[httpx]` |
| `storage` | DuckDB storage | `[storage]` |
| `markdown` | Exact token counts with tiktoken | `[markdown]` |
| `mcp` | MCP server for AI agents | `[mcp]` |
| `all` | Everything above | `[all]` |

From a clone: `pip install -e ".[all]"`.

## Quick start

```python
import asyncio
import omniscrape

async def main():
    page = await omniscrape.scrape("https://quotes.toscrape.com/")
    print(page.title)            # page title
    print(page.markdown[:300])   # main-content Markdown, boilerplate removed
    print(page.links[:5])        # absolute links
    print(page.metadata)         # title, author, dates, site name, description, language

asyncio.run(main())
```

`scrape_sync(url)` does the same without `asyncio`. `scrape_product(url)` and `scrape_article(url)`
return just the product or article.

A `ScrapeResult` contains:

| Field | Meaning |
|---|---|
| `title` | The page's `<title>` (or `og:title`) |
| `markdown`, `fit_markdown` | Main-content Markdown (the same text) |
| `product` | A `Product` (title, price, currency, brand, sku, rating, review_count, availability, images, ...) or `None` |
| `article` | An `Article` (title, author, published_date, modified_date, body_text, tags, ...) or `None` |
| `metadata` | Article-style metadata for any page |
| `structured_data` | JSON-LD, Microdata, RDFa, OpenGraph, meta tags, Dublin Core |
| `links` | Up to 100 absolute links |
| `html`, `status_code`, `latency_ms`, `fetcher_tier` | The raw response and how it was fetched |

## Fetching pages

OmniScrape has three fetch tiers:

| Tier | Name | Engine | Use |
|---|---|---|---|
| 1 | `http` | curl_cffi with browser TLS fingerprints | Most pages; fast |
| 2 | `browser` | Playwright Chromium | Pages built by JavaScript |
| 3 | `stealth` | Camoufox, or hardened Chromium | Opt-in only (`allow_stealth=True`) |

By default (`tier=None`) OmniScrape starts with tier 1 and moves to tier 2 when the page is an empty
JavaScript shell. A blocked response (403, challenge page) is returned to you as is, with
`defense_detected` set. It escalates to tier 3 only if you pass `allow_stealth=True`.

```python
res = await omniscrape.fetch("https://example.com")            # automatic
res = await omniscrape.fetch("https://example.com", tier=2)    # force the browser
res.status_code, res.html, res.headers, res.cookies, res.fetcher_tier, res.defense_detected, res.ok
```

For more than one request, reuse an `OmniClient`. It keeps connections and browsers open and adds
retries, a circuit breaker, a proxy pool and a dead-letter log of failed URLs:

```python
from omniscrape import OmniClient, ProxyPoolManager
from omniscrape.resilience import CircuitBreaker, DeadLetterQueue

async with OmniClient(
    retries=2,                                   # transport errors, HTTP 429 (honours Retry-After), 5xx
    timeout=30,
    headers={"Accept-Language": "en-GB"},
    proxy_pool=ProxyPoolManager(["http://user:pass@p1:8080", "http://p2:8080"], strategy="round_robin"),
    circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=30),
    dead_letter=DeadLetterQueue("failed.db"),
) as client:
    res = await client.fetch("https://example.com/a")
    page = await client.scrape("https://example.com/b")
```

- `ProxyPoolManager` strategies are `round_robin`, `random` and `sticky` (one proxy per domain). It
  stops using a proxy whose failure rate is too high.
- DNS and TLS errors are not retried.
- A domain that keeps failing or blocking trips the circuit breaker.

You can plug in your own fetcher:

```python
from omniscrape import register_fetcher
from omniscrape.fetchers.base import BaseFetcher

class MyApiFetcher(BaseFetcher):
    async def fetch(self, url, **kwargs): ...   # return a FetchResult
    async def close(self): ...

register_fetcher("my-api", MyApiFetcher)
res = await omniscrape.fetch("https://example.com", tier="my-api")
```

## Browser rendering and page actions

Install the `browser` extra first. The browser tier waits for the page's `load` event, then until the
DOM stops changing, instead of sleeping a fixed time.

```python
res = await omniscrape.fetch(
    "https://example.com/products",
    tier=2,
    wait_for=".product-card",               # also wait for this selector
    actions=[
        {"type": "click", "selector": "button.load-more"},
        {"type": "infinite_scroll", "max_scrolls": 5},
        {"type": "type", "selector": "input[name=q]", "text": "lamp"},
        {"type": "press", "key": "Enter"},
        {"type": "evaluate", "script": "() => document.querySelectorAll('.product-card').length"},
    ],
    screenshot=True,                         # PNG bytes in res.screenshot
    capture_network=True,                    # JSON the page fetched from its API, in res.network
)
res.action_results    # [42]  values returned by "evaluate" actions
res.actions_log       # one entry per action, with ok/error; a failed action is reported, not raised
```

| Action | Fields |
|---|---|
| `click` | `selector` |
| `type` (or `write`) | `selector`, `text` |
| `press` | `key` |
| `scroll` | `direction` (`down`/`up`) and `amount`, or `to` (`bottom`/`top`) |
| `infinite_scroll` | `max_scrolls`, `pause_ms` |
| `wait` | `milliseconds`, or `selector` |
| `evaluate` | `script` |
| `screenshot` | `full_page` |
| `scrape` | (none): saves the HTML at that point |

Add `"optional": True` to an action to continue when it fails. Other fetch options are `pdf=True`,
`wait_until` (`"load"`, `"domcontentloaded"`, `"networkidle"`) and `cookies`.

Browser settings go to the fetcher through `OmniClient(fetcher_options=...)`:

```python
async with OmniClient(fetcher_options={2: {
    "isolate": False,               # share one context and reuse tabs (faster); default True = fresh context per page
    "block_resources": True,        # skip images, fonts and media (default)
    "cdp_url": None,                # attach to a running Chromium-compatible browser instead of launching one
    "user_data_dir": None,          # a persistent profile that keeps logins and cookies
    "headless": True,
}}) as client:
    res = await client.fetch("https://example.com", tier=2)
```

## Selectors

`Selector` follows the Parsel/Scrapy API with Scrapling-style navigation:

```python
from omniscrape import Selector

page = Selector(html, url="https://shop.example/list")

page.css("div.card h3::text").getall()            # ['Lamp', 'Desk', 'Chair']
page.css("div.card a::attr(href)").get()          # '/p/a1'
page.css("span.price").re(r"\$([\d.]+)")          # ['10.00', '120.50', '75.00']
page.css("span.price::text").re_first(r"[\d.]+")  # '10.00'
page.xpath("//div[@data-sku='B2']/h3/text()").get()
page.css("div.card").css("h3::text").getall()     # chain queries on a result list

card = page.css_first("div.card")
card.text, card.own_text, card.html, card.attrib, card.get("data-sku")
card.next, card.previous, card.siblings, card.parent(), card.children()
card.find_similar()                                # the other cards in the grid
card.generate_css_selector(), card.generate_xpath()
page.find("div", class_="card", data_sku="C3")      # BeautifulSoup-style search
page.find_all("a", text="View")
page.find_by_text("Free shipping"), page.find_by_regex(r"\d+ in stock")
card.css_first("a").urljoin("/p/a1")              # 'https://shop.example/p/a1'
```

Result lists are normal Python lists. `.get()` on a list returns the first result as text (an
element as HTML); `.get("attr")` on an element returns that attribute. An invalid selector returns an
empty list.

## Self-healing selectors

Save an element once. After a redesign breaks your selector, OmniScrape finds the element again
from its fingerprint: tag path, position, attributes, text and the labels around it.

```python
from omniscrape import Selector

# First run: remember the element
page = Selector(html_v1, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
page.css(".price-current", identifier="price", auto_save=True)

# Later: classes renamed, element wrapped, tag changed...
page = Selector(html_v2, url="https://shop.example/item/1", adaptive=True, storage="fingerprints.db")
page.css(".price-current", identifier="price", adaptive=True)[0].text   # '₹85,000'
```

- If the selector still matches, its result is returned as usual.
- When the best candidate is not clearly better than the runner-up, OmniScrape returns nothing
  rather than guessing. A missed element is easier to notice than a wrong one.
- `storage` defaults to `~/.omniscrape/fingerprints.db`. Fingerprints are kept per domain and
  `identifier` (or per selector, if you give no identifier).

## Products, articles and structured data

These work on HTML you already have, with no network access:

```python
from omniscrape import extract_product, extract_metadata, SemanticExtractor
from omniscrape.parsers.structured import extract_structured

product = extract_product(html, url)          # Product or None
product.title, product.price, product.currency, product.brand, product.sku
product.availability, product.rating, product.review_count, product.images
product.metadata["sources"]                   # which layer found each field

meta = extract_metadata(html, url)            # dict: title, author, published_date, modified_date,
                                              # site_name, description, language, tags, image
data = extract_structured(html, url)          # {"json-ld", "microdata", "rdfa", "opengraph", "meta", "dublincore"}
SemanticExtractor(html, url).extract_article()
```

Product extraction tries each source in turn and fills only the fields still missing:

1. JSON-LD, Microdata or RDFa `Product` data.
2. OpenGraph and `product:*` meta tags.
3. Store JSON embedded in the page (for example Shopify's `ProductJson`).
4. The page itself. Price candidates are scored, and struck-through "was" prices, "M.R.P."
   labels and prices in related-product carousels are skipped. Split prices such as
   `₹<span>7,799</span>.<span>00</span>` are joined back together.

`currency` is `None` when the page shows no currency.

## Markdown for LLMs

```python
from omniscrape import fit_markdown, chunk_markdown, html_to_markdown
from omniscrape.content import count_tokens

md = fit_markdown(html, url=url)                         # main content only, no links or images
md = fit_markdown(html, url=url, query="return policy")  # keep only blocks relevant to the query (BM25)
md = fit_markdown(html, url=url, links=True, citations=True, max_tokens=2000)
full = html_to_markdown(html, url=url, main_content=False)   # whole page, links resolved

for chunk in chunk_markdown(md, max_tokens=512):          # retrieval-sized chunks
    chunk.text, chunk.headings, chunk.tokens              # headings = section path, e.g. ['Guide', 'Pricing']
count_tokens(md)                                         # tiktoken if installed, else an estimate
```

- **Main content.** Navigation, footers, sidebars, cookie banners, share bars, comment sections and
  promos are removed.
- **Kept structure.** The Markdown keeps headings, nested lists, tables, fenced code blocks (with
  the language when the page names it), quotes and emphasis.
- **Citations.** With `citations=True`, links become numbered references listed at the end.

## Crawling

Write a `Spider` and run it with a `CrawlEngine`:

```python
import asyncio
from omniscrape import CrawlEngine, JSONLStorage, LinkExtractor, Request, Spider

links = LinkExtractor(same_domain=True)

class Books(Spider):
    name = "books"
    start_urls = ["https://books.toscrape.com/"]
    concurrency = 4

    async def parse(self, response, selector):
        if selector.css("div.product_main"):
            yield {"title": selector.css("h1::text").get(),
                   "price": selector.css("p.price_color::text").get(),
                   "url": response.url}
        for url in links.extract(selector, response.url):
            yield Request(url)

stats = asyncio.run(CrawlEngine(
    Books(),
    storage=JSONLStorage("books.jsonl"),
    max_pages=200,
    queue_path="books-queue.db",     # persistent queue: run again to resume
).run())
print(stats.to_dict())               # pages, items, failed, robots_blocked, duplicates, pages_per_sec, ...
```

`parse` receives the `FetchResult` and a `Selector`. It yields items (dicts or Pydantic models) and
`Request`s; relative URLs are resolved.

| `CrawlEngine` option | Default | Meaning |
|---|---|---|
| `obey_robots` | `True` | Follow robots.txt, including `Crawl-delay` |
| `max_pages` | none | Stop after this many pages |
| `max_depth` | none | Maximum link depth from the start URLs |
| `allowed_domains` | none | Only crawl these domains (or set `Spider.allowed_domains`) |
| `concurrency`, `per_domain_concurrency` | `Spider.concurrency` | Parallel requests overall and per domain |
| `download_delay` | `0` | Minimum seconds between requests to one domain |
| `autothrottle` | `False` | Adapt the delay to the site's response time |
| `queue_path` | none | SQLite file for a resumable queue |
| `tier` | `1` | Fetch tier for every request (`None` = automatic; a `Request` can override it) |
| `pipelines` | `[]` | Functions that receive each item and return it, a changed copy or `None` to drop it |
| `storage` | none | Where items are written |
| `client` | new `OmniClient` | Pass your own for proxies, headers or browser settings |

- **Resuming.** With `queue_path`, stopping a crawl (or reaching `max_pages`) leaves the rest of the
  queue saved, and the next run continues without repeating pages. If the process is killed, only
  the requests in flight at that moment can be fetched again.
- **Streaming.** Use `async for item in engine.stream(): ...` to handle items as they arrive.
- **Priority and per-request settings.** `Request(url, callback=self.parse_detail, priority=10, meta={...})`
  sets these for one request.
- **Link extraction.** `LinkExtractor(allow=[r"/catalogue/"], deny=[r"/login"], restrict_css="main",
  same_domain=True)` canonicalizes and de-duplicates links and skips images, archives and other
  files.

To discover a site's URLs without crawling it:

```python
from omniscrape import map_site

urls = await map_site("https://example.com", search="pricing", limit=500)
```

`map_site` reads the sitemaps listed in robots.txt (or `/sitemap.xml`) plus the start page's links,
respects robots.txt, and with `search` puts the best-matching URLs first.

## Storage

```python
from omniscrape import JSONLStorage, DuckDBStorage

storage = JSONLStorage("items.jsonl")                       # one JSON object per line
storage = DuckDBStorage("items.duckdb", table_name="items")  # needs the storage extra
await storage.write({"title": "Lamp", "price": 10.0})
await storage.write_batch([...])
await storage.close()
```

To add a backend, subclass `omniscrape.storage.base.BaseStorage` (`write`, `write_batch`, `flush`, `close`).

## Command line

```bash
omniscrape get https://books.toscrape.com/                 # summary table
omniscrape get https://books.toscrape.com/ -f markdown     # main-content Markdown
omniscrape get https://books.toscrape.com/ -f json         # the full ScrapeResult
omniscrape get https://example.com/app --tier 2            # force the browser tier
```

## MCP server for AI agents

Install the `mcp` extra, then:

```bash
omniscrape mcp                                   # stdio, for desktop agents
omniscrape mcp --transport http --port 8000      # streamable HTTP at http://127.0.0.1:8000/mcp
```

For a desktop agent, add this to its MCP configuration:

```json
{"mcpServers": {"omniscrape": {"command": "omniscrape", "args": ["mcp"]}}}
```

| Tool | Returns |
|---|---|
| `scrape_url(url, allow_stealth=False)` | Title, main-content Markdown, product, article, metadata and links (no raw HTML) |
| `scrape_product(url)` | Product fields |
| `scrape_article(url)` | Article fields |
| `get_markdown(url, query=None, max_tokens=None)` | Main-content Markdown, optionally filtered by a query |
| `map_site(url, search=None, limit=200)` | A list of the site's URLs |

## Utilities

```python
from omniscrape import parse_price, parse_date, parse_unit
from omniscrape.normalizers.currency import parse_money

parse_money("₹1,29,999")      # (129999.0, 'INR')  Indian digit grouping
parse_money("1.299,00 €")     # (1299.0, 'EUR')
parse_money("Price: 7,799")   # (7799.0, None)     no currency shown
parse_price("$49.99")         # (49.99, 'USD')     like parse_money, but defaults to USD
parse_date("Nov 23, 2026")    # '2026-11-23T00:00:00'
```

## Benchmarks

The `benchmarks/` folder compares OmniScrape with other tools on the same pages and the same local
test site. Each tool runs in its own Python 3.12 environment and its own process, so a tool's
dependencies and memory never affect another's.

**Setup for the results below:**

- **Machine.** Windows 11 on an Intel Core 12-thread CPU with 12 GB RAM.
- **Code.** OmniScrape commit `acb9456`.
- **Tool versions.** Scrapling 0.5.1, Crawl4AI 0.9.6, Scrapy 2.20.0, Crawlee 1.11.3,
  Trafilatura 2.4.0, Parsel 1.12.1, selectolax 1.0.2, lxml 6.1.3, BeautifulSoup 4.15.0,
  markdownify 1.2.4 and html2text 2025.4.15.

**Test pages.** OmniScrape was tuned only on a separate development set. The holdout below was
never used for tuning. It has 37 real-world pages: product pages from scraping practice shops
(books.toscrape.com, webscraper.io, scrapeme.live), Python PEPs, Go and Rust blog posts and GOV.UK
news. It also has generated pages in three page layouts not used for tuning. Ground truth for the
real pages comes from each site's own markup, not from any tool's output.

### Main-content Markdown (article pages)

F1 is the balance of precision (how much of the output is real article text) and recall (how much
of the article was found). Leakage is the share of output words that come from menus, footers, ads
and comments.

| Tool | F1 (holdout) | F1 (hand-written pages) | Boilerplate leakage | Peak MB |
|---|---|---|---|---|
| **OmniScrape** | **0.985** | **0.984** | **0.3%** | 59 |
| Trafilatura | 0.981 | 0.960 | 1.0% | 57 |
| Crawl4AI (fit Markdown) | 0.831 | 0.561 | 10.7% | 123 |
| markdownify (whole page) | 0.767 | 0.607 | 18.2% | 52 |
| html2text (whole page) | 0.716 | 0.522 | 14.8% | 27 |
| Crawl4AI (raw Markdown) | 0.689 | 0.510 | 14.4% | 111 |

### Zero-config extraction (no per-site selectors)

| Tool | Product fields F1 (holdout) | Article metadata F1 (holdout) |
|---|---|---|
| **OmniScrape** | **1.000** | **0.897** |
| Trafilatura | not supported | 0.848 |

Product fields are title, price, currency, brand, SKU, rating, review count and availability.
Article fields are title, author and publication date. For OmniScrape, titles scored 1.000,
authors 0.833 and dates 0.831.

### Self-healing selectors

There are 1,377 cases where a saved selector no longer matched after the page changed. Recovered
means the right element was found; wrong element means a different element was returned, which is
a silent data error.

| Tool | Recovered | Wrong element | Missed | Time per page |
|---|---|---|---|---|
| **OmniScrape** | **99.6%** | **0.4%** | 0 | 29 ms |
| Scrapling | 85.3% | 14.7% | 0 | 40 ms |

| Page change | OmniScrape | Scrapling |
|---|---|---|
| All classes renamed | 100% | 100% |
| IDs and data attributes changed | 100% | 96.5% |
| Element wrapped in a new container | 100% | 92.2% |
| Look-alike siblings inserted | 100% | 92.9% |
| Tag changed (for example span to div) | 100% | 60.1% |
| Text changed (for example a new price) | 97.0% | 100% |
| Several changes at once | 100% | 57.1% |

### Parsing speed

Parse each page and run its CSS selectors, over the whole corpus. All tools return the same counts.

| Tool | Documents/s | Peak MB |
|---|---|---|
| selectolax (C engine) | 1,889 | 34 |
| **OmniScrape** | **455** | 57 |
| Scrapling | 421 | 46 |
| lxml | 386 | 39 |
| Parsel | 252 | 45 |
| BeautifulSoup + lxml | 72 | 60 |
| BeautifulSoup + html.parser | 66 | 58 |

### Crawling a local test site

The site has 300 pages with 5–25 ms latency per request and 8 requests at a time. robots.txt is
obeyed, and 10 pages fail once with HTTP 500. Coverage, duplicates and robots violations are counted
by the server.

| Tool | Pages/s | Coverage | Robots violations | Duplicates | Flaky pages recovered | Peak MB |
|---|---|---|---|---|---|---|
| Scrapling | 178.7 | 100% | 0 | 0 | 10/10 | 60 |
| **OmniScrape** | **150.5** | 100% | 0 | 0 | 10/10 | **46** |
| Scrapy | 122.7 | 100% | 0 | 1 | 10/10 | 81 |
| Crawlee | 74.3 | 100% | 0 | 0 | 10/10 | 61 |
| Crawl4AI (browser) | 13.0 | 100% | 0 | 1 | 0/10 | 1,308 |

### JavaScript rendering

60 pages rendered by script, 4 at a time. The times include starting the browser.

| Tool | Pages/s | Rendered | Peak MB |
|---|---|---|---|
| Scrapling | 14.5 | 100% | 1,141 |
| **OmniScrape (shared context)** | **13.2** | 100% | 897 |
| OmniScrape (isolated, the default) | 11.0 | 100% | **604** |
| Crawl4AI | 7.2 | 100% | 931 |

"Shared context" (`isolate=False`) reuses tabs in one browser context, like the other tools'
sessions. The default gives every page a fresh context with no shared cookies.

### Limits of these results

- The corpus is small: Trafilatura's own published evaluation uses 990 documents.
- The page changes for the self-healing test were written by OmniScrape's authors.
- Speed varies between runs and machines. Scrapling's parse speed ranged from 421 to 475 documents/s
  across our runs.
- Compiled tools such as Spider (Rust) and Lightpanda (Zig) are not compared.

### Reproducing

```bash
pip install -e ".[dev,bench]"
python -m benchmarks envs                 # build an isolated environment per tool (needs uv)
python -m benchmarks run                  # all suites; --suite parse,crawl and --tools omniscrape,scrapy to narrow
python -m benchmarks report               # HTML report of the latest run
python -m benchmarks compare <old> <new>  # what changed between two runs
```

The live suite makes a small number of requests to books.toscrape.com and quotes.toscrape.com
(about 40 and 20 pages per tool). Every other suite runs offline or against a local test server.

## Responsible use

- **robots.txt.** The crawler and `map_site` obey robots.txt by default.
- **Blocked pages.** A blocked response is returned to you as an access restriction. OmniScrape
  does not solve CAPTCHAs or Cloudflare challenges, and the stealth tier is used only when you ask
  for it.
- **Permission.** Check a site's terms, and prefer official APIs and feeds where they exist.

OmniScrape's features were written from the public documentation of other projects (Scrapling,
Crawl4AI, Firecrawl, Crawlee, Scrapy, Trafilatura, Extruct and others), not from their source code.

## Development

```bash
git clone https://github.com/loganathan-ai-dev/Omni-Scrape.git && cd Omni-Scrape
pip install -e ".[dev,browser,mcp]" && playwright install chromium
pytest                                  # unit and integration tests; no internet needed
python -m benchmarks.dev_eval           # extraction quality on the development set (for tuning)
```

The integration tests start a local test site, so crawling, robots.txt, retries, browser actions
and the MCP tools are tested without touching the internet. See [CHANGELOG.md](CHANGELOG.md) for
release notes.
