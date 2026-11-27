# Fetching, Retries & Stealth

OmniScrape routes all HTTP and browser requests through [`OmniClient`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/client.py), reusing long-lived fetcher instances across requests.

---

## Progressive Fetching Tiers

| Tier | Name / Aliases | Backend | When it is used |
|---|---|---|---|
| `1` | `"http"`, `"fast"`, `"fastfetcher"`, `"curl"` | `FastFetcher` (`curl_cffi`) | Default starting tier with HTTP/2 & browser TLS fingerprinting |
| `2` | `"browser"`, `"dynamic"`, `"dynamicfetcher"`, `"playwright"` | `DynamicFetcher` (`playwright`) | Auto-escalated when tier 1 returns an empty JS/SPA shell, or forced with `tier=2` |
| `3` | `"stealth"`, `"stealthfetcher"`, `"camoufox"` | `StealthFetcher` (`camoufox` or hardened Chromium) | Only used on blocks with `allow_stealth=True`, or forced with `tier=3` |
| — | `"httpx"`, `"h2"` | `HttpxFetcher` (`httpx[http2]`) | Opt-in HTTP/2 alternative (`[httpx]` extra) |

> [!WARNING]
> Tier 3 (`allow_stealth=True`) does **not** solve CAPTCHAs or bypass authentication gates. If a target returns an interactive challenge, `FetchResult.defense_detected` records the detected system (`cloudflare`, `datadome`, `akamai`, `perimeterx`, `kasada`, `aws_waf`).

---

## Top-Level Helpers vs `OmniClient`

Use top-level functions for one-off calls, and `OmniClient` (or `fetch_many` / `scrape_many`) for multiple URLs:

```python
import asyncio
import omniscrape
from omniscrape import OmniClient, ProxyPoolManager
from omniscrape.resilience import CircuitBreaker, DeadLetterQueue

async def run():
    # One-off call
    page = await omniscrape.scrape("https://example.com")

    # Concurrent batch with built-in per-domain concurrency and optional delay
    pages = await omniscrape.scrape_many(
        ["https://example.com/a", "https://example.com/b"],
        concurrency=8,
        per_domain_concurrency=4,
        delay=0.0,
    )

    # Long-lived reusable client
    async with OmniClient(
        allow_stealth=False,
        retries=2,
        retry_delay=1.0,
        timeout=30.0,
        cache_responses=True,  # ETag / Last-Modified 304 conditional cache
        proxy_pool=ProxyPoolManager(
            ["http://user:pass@p1:8080", "http://p2:8080"],
            strategy="round_robin",
        ),
        circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=30),
        dead_letter=DeadLetterQueue("failed.db"),
    ) as client:
        res = await client.fetch("https://example.com/a")

asyncio.run(run())
```

---

## Retries, Errors & Caching

- **Automatic retries**: Transport timeouts/connection errors, HTTP `429` (honoring `Retry-After` headers when present), and status codes `408, 500, 502, 503, 504, 520, 521, 522, 523, 524`.
- **Non-retried errors**: `DNSResolutionError` and `SSLHandshakeError` fail immediately instead of wasting retry budget.
- **Conditional 304 cache**: Enable `OmniClient(cache_responses=True)` to automatically send `If-None-Match` / `If-Modified-Since` and reuse cached bodies on `304 Not Modified`.

---

## Browser Actions, Wait & Network Capture

Both `tier=2` (`DynamicFetcher`) and `tier=3` (`StealthFetcher`) share [`run_playwright_fetch`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/fetchers/actions.py):

```python
res = await omniscrape.fetch(
    "https://example.com/shop",
    tier=2,
    wait_for=".product-card",
    actions=[
        {"type": "click", "selector": "button.load-more"},
        {"type": "infinite_scroll", "max_scrolls": 5},
        {"type": "type", "selector": "input[name=q]", "text": "lamp"},
        {"type": "press", "key": "Enter"},
        {"type": "wait", "milliseconds": 400},
        {"type": "evaluate", "script": "() => document.querySelectorAll('.product-card').length"},
    ],
    screenshot=True,
    pdf=False,
    capture_network=True,
)
print(res.action_results)  # evaluation outputs
print(res.actions_log)     # step-by-step ok/error log
print(res.network)         # captured JSON XHR/fetch payloads
```

- Pass `"optional": True` on any action dict so failure is recorded in `actions_log` rather than aborting.
- Reuse a single pooled browser context across requests with `OmniClient(fetcher_options={2: {"isolate": False}})`.

Browser tiers need the `browser` extra and `playwright install chromium`; see [[Installation]].

---

## Registering Custom Fetchers

```python
from omniscrape import register_fetcher, BaseFetcher, FetchResult

class MyApiFetcher(BaseFetcher):
    tier = 1
    async def fetch(self, url: str, **kwargs) -> FetchResult:
        return FetchResult(url=url, status_code=200, html="<html><body>ok</body></html>")
    async def close(self) -> None:
        pass

register_fetcher("my-api", MyApiFetcher, aliases=["myapi"])
```

---

## See also

- [[Crawling-and-Storage]]: every crawl goes through `OmniClient`, so it inherits these retries, proxies and tiers.
- [[CLI-Reference]]: `--tier`, `--stealth`, `--proxy`, `--header`, `--wait-for`.
- [[FAQ-and-Troubleshooting]]: empty pages and anti-bot blocks.

## Browser Identity, HTTP/3 and curl Import

The HTTP tier impersonates a real browser end to end: the TLS/HTTP2 fingerprint **and** the User-Agent and client
hints come from the same curl_cffi profile, so they never contradict each other.

```python
await omniscrape.fetch(url, impersonate="safari")              # one request as Safari
await omniscrape.fetch(url, http_version="3")                  # HTTP/3 ("1.1", "2", "3", "3only")

from omniscrape import OmniClient
OmniClient(fetcher_options={1: {"impersonate": ["chrome", "safari", "firefox"]}})          # one identity per host
OmniClient(fetcher_options={1: {"impersonate": ["chrome", "edge"], "rotate": "request"}})  # cycle per request
```

Profiles: `chrome` (default), `edge`, `safari`, `firefox`, `chrome_android`, `safari_ios`, or a pinned version such
as `chrome131`. On the CLI: `--impersonate safari --http-version 3`.

Replay a request copied from the browser's dev tools (*Copy as cURL*, bash or Windows `cmd` style):

```python
from omniscrape import parse_curl, fetch_curl

parse_curl("curl 'https://api.example.com/items?page=2' -H 'accept: application/json' -b 'sid=abc'")
res = await fetch_curl(command)                     # FetchResult via the HTTP tier; fetch_curl(command, tier=2) for a browser
```

`omniscrape curl "curl ..." -f json` does the same from the terminal, and `omniscrape shell` has `curl()` and `uncurl()`.
