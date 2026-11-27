# OmniScrape API Cheatsheet

Parameter reference for `src/omniscrape/` (omni-scraper 0.1.0). Install name `omni-scraper`; import `omniscrape`.

## Package Extras

- `browser`: `playwright>=1.48.0` (run `playwright install chromium` after install)
- `stealth`: `camoufox>=0.4.0`
- `fast`: `selectolax>=0.3.20` (`Selector(..., backend="selectolax")`)
- `httpx`: `httpx[http2]>=0.27.0` (`tier="httpx"`)
- `storage`: `duckdb>=1.1.0` (`DuckDBStorage`)
- `markdown`: `tiktoken>=0.7.0` (exact token counting in `fit_markdown` / `chunk_markdown`)
- `mcp`: `fastmcp>=2.3.0` (`omniscrape mcp`)
- `shell`: `ipython>=8` (`omniscrape shell` uses IPython when installed)
- `all`: `browser,stealth,httpx,storage,markdown,mcp,fast,shell`

## Top-Level Helpers (`omniscrape`)

- `fetch(url, tier=None, headers=None, proxy=None, timeout=30.0, *, allow_stealth=False, retries=2, **kwargs) -> FetchResult`
- `scrape(url, tier=None, headers=None, proxy=None, *, allow_stealth=False, retries=2, timeout=30.0, **kwargs) -> ScrapeResult`
- `scrape_sync(url, **kwargs) -> ScrapeResult`
- `fetch_many(urls, *, concurrency=8, per_domain_concurrency=4, delay=0.0, tier=None, allow_stealth=False, retries=2, timeout=30.0, return_exceptions=False, **kwargs)`
- `scrape_many(urls, *, concurrency=8, per_domain_concurrency=4, delay=0.0, tier=None, allow_stealth=False, retries=2, timeout=30.0, return_exceptions=False, **kwargs)`
- `scrape_product(url, **kwargs) -> Optional[Product]`
- `scrape_article(url, **kwargs) -> Optional[Article]`
- `map_site(url, client=None, limit=5000, search=None, include_subdomains=False, obey_robots=True, use_sitemaps=True) -> list[str]`

## `OmniClient` & Registry

```python
OmniClient(
    *,
    allow_stealth: bool = False,
    retries: int = 2,
    retry_delay: float = 1.0,
    timeout: float = 30.0,
    headers: Optional[dict[str, str]] = None,
    proxy: Optional[str] = None,
    proxy_pool: Optional[ProxyPoolManager] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
    dead_letter: Optional[DeadLetterQueue] = None,
    fetcher_options: Optional[dict[Union[int, str], dict[str, Any]]] = None,
    cache_responses: bool = False,
)
```

Built-in fetcher names & aliases (`register_fetcher` adds custom engines):
- `"http"` (`tier=1`, aliases: `fast`, `fastfetcher`, `curl`)
- `"browser"` (`tier=2`, aliases: `dynamic`, `dynamicfetcher`, `playwright`)
- `"stealth"` (`tier=3`, aliases: `stealthfetcher`, `camoufox`)
- `"httpx"` (alias: `h2`)

## Browser `actions` (`tier=2` or `tier=3`)

Pass `wait_for=".css"`, `screenshot=True`, `pdf=True`, `capture_network=True`, and `actions=[...]`:
- `{"type": "click", "selector": "..."}`
- `{"type": "type" | "write" | "fill", "selector": "...", "text": "..."}`
- `{"type": "press", "key": "Enter"}`
- `{"type": "scroll", "direction": "down" | "up", "amount": 800}` or `{"type": "scroll", "to": "top" | "bottom"}`; `{"type": "infinite_scroll", "max_scrolls": 5}`
- `{"type": "wait", "milliseconds": 500}` or `{"type": "wait", "selector": ".x"}`
- `{"type": "evaluate", "script": "() => ..."}` (appends return value to `res.action_results`)
- `{"type": "screenshot"}`
- `{"type": "scrape"}`
- Add `"optional": True` to any step so failures log to `res.actions_log` without aborting.

## `Selector.extract(schema)` Field Specs

Each schema value can be:
- A CSS string: `"h1::text"` (uses `.get()`)
- A dict:
  - `"selector"`: CSS selector string (required)
  - `"all"`: `bool` (default `False`; returns list via `.getall()`)
  - `"type"`: `"price"` (via `parse_price`), `"date"` (via `parse_date`), `"unit"` (via `parse_unit`), `"int"`, `"float"`, `"bool"`, `"str"`
  - `"default"`: fallback value when nothing matches

## Content & Structured Extraction

- `extract_product(html, url) -> Optional[Product]`
- `extract_listings(html_or_root, url="", *, min_repetition=3) -> list[dict[str, Any]]`
- `extract_metadata(html, url="") -> dict[str, Any]`
- `extract_main(html, url="") -> MainContent`
- `html_to_markdown(html, max_tokens=None, url="", main_content=True, links=True) -> str` (top-level export; main content by default). The whole-page converter with `images`/`citations` is `omniscrape.content.markdown.html_to_markdown(html, url="", links=True, images=True, citations=False, max_tokens=None)`.
- `fit_markdown(html, url="", query=None, links=False, images=False, citations=False, title=True, max_tokens=None, main=None) -> str`
- `chunk_markdown(md, max_tokens=512, overlap_blocks=0) -> list[Chunk]` (`Chunk.text`, `.headings`, `.tokens`)

## `CrawlEngine` & Storage

```python
CrawlEngine(
    spider,
    storage=None,                 # JSONLStorage("out.jsonl") or DuckDBStorage("out.duckdb")
    use_checkpoint=False,         # saves queue to ~/.omniscrape/queues/<spider.name>.db
    *,
    client=None,
    obey_robots=True,
    max_pages=None,
    max_depth=None,
    allowed_domains=None,
    concurrency=None,
    per_domain_concurrency=None,
    download_delay=0.0,
    autothrottle=False,
    queue_path=None,
    resume=True,
    tier=1,
    user_agent="omniscrape",
    pipelines=None,               # list[Callable[[item], item | None]]
    retries=2,
    start_from_sitemap=False,
)
```

Use `await engine.run() -> CrawlStats` or `async for item in engine.stream(): ...`.

## MCP Server Tools (`omniscrape mcp`)

- `scrape_url(url: str, allow_stealth: bool = False) -> str` (JSON without raw `html` or `structured_data`)
- `scrape_product(url: str) -> str`
- `scrape_article(url: str) -> str`
- `extract_entities(url, allow_stealth=False)` -> `{url, content_type, entities}`
- `extract_schema(url, schema: dict, allow_stealth=False)` -> JSON of `Selector.extract(schema)`
- `extract_listings(url, allow_stealth=False)` -> cards `[{title, url, price, currency, image}]`
- `get_links(url, same_domain=True, pattern=None, limit=200, allow_stealth=False)`
- `crawl_site(url, max_pages=20, pattern=None)` (same domain, robots.txt obeyed, at most 50 pages)
- `screenshot(url, full_page=False, wait_for=None)` -> PNG image (needs the `browser` extra)
- Error and anti-bot pages (including challenge pages served with HTTP 200) never reach the agent as content: `scrape_url`, `scrape_product`, `scrape_article`, `extract_*`, `get_links` and `screenshot` return a tool error, `get_markdown` returns a message starting with `Error:`, and `crawl_site` lists such pages with an `error` field instead of their content.
- `get_markdown(url: str, query: Optional[str] = None, max_tokens: Optional[int] = None, allow_stealth: bool = False) -> str` (returns an `Error: ... HTTP <status>` message for non-2xx responses)
- `map_site(url: str, search: Optional[str] = None, limit: int = 200) -> str`

## Crawler details

- Callbacks are `parse(response, selector)`; `selector` is built with the page URL, so `urljoin` and adaptive keys work.
- `Request(url, callback=None, meta={...}, priority=0, tier=None)`: `meta` is persisted and delivered as `response.meta`.
- `FetchResult.meta` is only filled by the crawler.
- `robots.txt` rules honour `*` and `$` wildcards and `Crawl-delay`.

## CLI (`omniscrape`)

- `get URL [-f summary|json|markdown|html|text] [--impersonate PROFILE] [--http-version 1.1|2|3] [--css SEL (incl. ::text / ::attr(x))] [-o FILE] [-t TIER] [--stealth] [--proxy URL] [-H "K: v"] [--timeout S] [--wait-for SEL]`
- `crawl URL [--max-pages N] [--depth N] [-c N] [--delay S] [-o FILE.jsonl|.duckdb] [--allow RE] [--deny RE] [--resume] [--append] [--no-robots] [--sitemap] [-t TIER]`
- `map URL [-q TERMS] [--limit N] [-f text|json]`
- `extract URL --schema schema.json [-o FILE] [-t TIER] ...` (schema = `Selector.extract` dict as JSON)
- `curl "curl ..." [-f ...] [-o FILE] [-t TIER] [--impersonate PROFILE]`: replay a *Copy as cURL* command
- `shell [URL] [--plain]`: REPL with `omniscrape`, `Selector`, `fetch_sync`, `scrape_sync`, `curl(cmd)`, `uncurl(cmd)`, `entities(html, url)` (and `response`, `page` when URL given)
- `get -o page.md|.json|.html|.txt` picks the format from the extension when `-f` is not given.
- `mcp [--transport stdio|http] [--host H] [-p PORT]`

`crawl` replaces an existing output file unless `--resume` or `--append` is given; output must be `.jsonl`, `.ndjson` or `.duckdb`.

Data goes to stdout; logs and tables go to stderr, so `omniscrape get URL -f json | jq .` is safe.

## Page entities and page type (`omniscrape.extract.entities`)

- `extract_entities(html_or_root, url="", structured=None) -> PageEntities`
  (`recipe`, `events`, `jobs`, `reviews`, `rating`, `rating_count`, `faq`, `organization`, `breadcrumbs`, `next_page`, `tables`)
- `detect_content_type(html_or_root, url="", structured=None, *, entities=None, product=..., article=...) -> str`
  one of `product, article, recipe, event, job, listing, faq, organization, other`
- `extract_recipe`, `extract_events`, `extract_jobs`, `extract_faq`, `extract_organization`, `extract_breadcrumbs`
  take `(html_or_root, url="", structured=None)`; `extract_reviews(...)` returns `(reviews, rating, rating_count)`
- `find_next_page(html_or_root, url="") -> Optional[str]`; `extract_tables(html_or_root, max_tables=10, max_rows=200)`
- `ScrapeResult.content_type` and `ScrapeResult.entities` carry the same data.

## Browser profiles (`FastFetcher`, tier 1)

`FastFetcher(impersonate="chrome" | [profiles], rotate="domain" | "request", http_version=None | "1.1" | "2" | "3", verify=True)`;
per request `fetch(url, impersonate=..., http_version=...)`. Configure on a client with
`OmniClient(fetcher_options={1: {"impersonate": [...], "rotate": "request"}})`.

## Multi-session spiders

`Spider.sessions: dict[str, dict]` (keys: `tier`, `headers`, `proxy`, `timeout`, `allow_stealth`, plus fetcher options such as
`impersonate`, `http_version`, `wait_for`, `actions`), `Spider.default_session`, `Request(url, session="name")`.
An unknown `default_session` raises `ConfigError` before any request; sessions persist with `--resume` / `queue_path`.

## curl import (`omniscrape.curl`)

- `parse_curl(command) -> {url, method, headers, cookies, data, proxy, timeout, http_version, insecure}`
- `await fetch_curl(command, **overrides) -> FetchResult` (tier 1 by default; `overrides` such as `impersonate="safari"`, `retries=`; browser tiers replay GET only; non-GET/HEAD/OPTIONS requests are not retried unless you pass `retries=`)
- Supports `-X -H -b -d/--data* --data-urlencode --json -A -e -u -x -G -I -m -k --http1.1/2/3 --url`; rejects `-d @file` and `-F`.
