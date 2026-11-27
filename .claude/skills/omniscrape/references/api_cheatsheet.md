# OmniScrape API Cheatsheet

Verified parameter reference from `src/omniscrape/`.

## Package Extras

- `browser`: `playwright>=1.48.0` (run `playwright install chromium` after install)
- `stealth`: `camoufox>=0.4.0`
- `fast`: `selectolax>=0.3.20` (`Selector(..., backend="selectolax")`)
- `httpx`: `httpx[http2]>=0.27.0` (`tier="httpx"`)
- `storage`: `duckdb>=1.1.0` (`DuckDBStorage`)
- `markdown`: `tiktoken>=0.7.0` (exact token counting in `fit_markdown` / `chunk_markdown`)
- `mcp`: `fastmcp>=2.3.0` (`omniscrape mcp`)
- `all`: `browser,stealth,httpx,storage,markdown,mcp`

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
- `{"type": "scroll", "x": 0, "y": 800}` or `{"type": "infinite_scroll", "max_scrolls": 5}`
- `{"type": "wait", "ms": 500}` or selector wait
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
- `html_to_markdown(html, url="", links=True, images=True, citations=False, max_tokens=None) -> str`
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
- `get_markdown(url: str, query: Optional[str] = None, max_tokens: Optional[int] = None) -> str`
- `map_site(url: str, search: Optional[str] = None, limit: int = 200) -> str`
