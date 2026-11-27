"""OmniClient: the single fetch/scrape path used by the public API, crawler, CLI, REST and MCP.

It owns long-lived fetchers (one per engine, reused across requests) and applies, in order:
circuit breaker -> proxy selection -> fetch -> retry on transport errors / 429 / 5xx ->
escalation (JS rendering automatically; stealth only with ``allow_stealth=True``) -> DLQ on
final failure.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from email.utils import parsedate_to_datetime
from typing import Any, Optional, Union
from urllib.parse import urljoin, urlsplit

from omniscrape.classifier.strategies import EscalationStrategy, is_blocked
from omniscrape.exceptions import NetworkError, RateLimitError, ServerError
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.fetchers.pool import ProxyPoolManager
from omniscrape.fetchers.registry import create_fetcher, get_spec
from omniscrape.models import DefenseSystem, FetchResult, ScrapeResult
from omniscrape.observability.logging import get_logger
from omniscrape.resilience.circuit_breaker import CircuitBreaker
from omniscrape.resilience.dead_letter import DeadLetterQueue
from omniscrape.resilience.retry import with_retry

logger = get_logger("omniscrape.client")

RETRY_STATUSES = {408, 500, 502, 503, 504, 520, 521, 522, 523, 524}
FetcherRef = Union[int, str]


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            from datetime import datetime, timezone

            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except Exception:
            return None


def domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


class OmniClient:
    """Reusable scraping client. Use as ``async with OmniClient() as client: ...``."""

    def __init__(
        self,
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
        fetcher_options: Optional[dict[FetcherRef, dict[str, Any]]] = None,
        cache_responses: bool = False,
    ):
        self.allow_stealth = allow_stealth
        self.retries = retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.proxy = proxy
        self.proxy_pool = proxy_pool
        self.circuit_breaker = circuit_breaker
        self.dead_letter = dead_letter
        self.fetcher_options = {get_spec(k).name: v for k, v in (fetcher_options or {}).items()}
        self.cache_responses = cache_responses
        self._response_cache: dict[str, tuple[Optional[str], Optional[str], FetchResult]] = {}
        self._fetchers: dict[str, BaseFetcher] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle
    async def __aenter__(self) -> "OmniClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        fetchers, self._fetchers = list(self._fetchers.values()), {}
        for fetcher in fetchers:
            try:
                await fetcher.close()
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                logger.warning(f"Error closing fetcher {fetcher!r}: {exc}")

    async def get_fetcher(self, ref: FetcherRef) -> BaseFetcher:
        """Return the shared fetcher instance for a tier number or registered name."""
        spec = get_spec(ref)
        async with self._lock:
            if spec.name not in self._fetchers:
                self._fetchers[spec.name] = create_fetcher(spec.name, **self.fetcher_options.get(spec.name, {}))
            return self._fetchers[spec.name]

    # ------------------------------------------------------------------ fetching
    async def fetch(
        self,
        url: str,
        tier: Optional[FetcherRef] = None,
        *,
        headers: Optional[dict[str, str]] = None,
        proxy: Optional[str] = None,
        timeout: Optional[float] = None,
        allow_stealth: Optional[bool] = None,
        **kwargs: Any,
    ) -> FetchResult:
        """Fetch ``url``. ``tier=None`` starts at tier 1 and escalates automatically."""
        allow_stealth = self.allow_stealth if allow_stealth is None else allow_stealth
        domain = domain_of(url)
        if self.circuit_breaker:
            self.circuit_breaker.check(domain)

        merged_headers = {**self.headers, **(headers or {})}
        current: FetcherRef = tier if tier is not None else 1
        tried: set[str] = set()
        while True:
            result = await self._fetch_once(current, url, merged_headers, proxy, timeout, domain, **kwargs)
            tried.add(get_spec(current).name)
            if tier is not None:
                return result
            nxt = EscalationStrategy.next_tier(result, allow_stealth=allow_stealth)
            if nxt is None or get_spec(nxt).name in tried:
                return result
            logger.info(f"Escalating {url} from tier {result.fetcher_tier} to tier {nxt}")
            current = nxt

    async def _fetch_once(
        self,
        ref: FetcherRef,
        url: str,
        headers: dict[str, str],
        proxy: Optional[str],
        timeout: Optional[float],
        domain: str,
        **kwargs: Any,
    ) -> FetchResult:
        fetcher = await self.get_fetcher(ref)
        last: dict[str, FetchResult] = {}

        async def attempt() -> FetchResult:
            chosen = proxy or self.proxy or (self.proxy_pool.get_proxy(domain) if self.proxy_pool else None)
            req_headers = headers
            cached_entry = self._response_cache.get(url) if self.cache_responses else None
            if cached_entry is not None:
                etag, last_mod, _ = cached_entry
                if etag or last_mod:
                    req_headers = dict(headers)
                    if etag:
                        req_headers.setdefault("If-None-Match", etag)
                    if last_mod:
                        req_headers.setdefault("If-Modified-Since", last_mod)
            try:
                res = await fetcher.fetch(
                    url, headers=req_headers or None, proxy=chosen, timeout=timeout or self.timeout, **kwargs
                )
            except NetworkError:
                if self.proxy_pool and chosen:
                    self.proxy_pool.record_result(chosen, False)
                raise
            if res.status_code == 304 and cached_entry is not None:
                res = cached_entry[2].model_copy(update={"latency_ms": res.latency_ms})
            elif self.cache_responses and res.status_code == 200:
                h_low = {k.lower(): v for k, v in res.headers.items()}
                etag = h_low.get("etag")
                last_mod = h_low.get("last-modified")
                if etag or last_mod:
                    self._response_cache[url] = (etag, last_mod, res)
            last["result"] = res
            if self.proxy_pool and chosen:
                self.proxy_pool.record_result(chosen, res.status_code < 400 or res.status_code == 404)
            if res.status_code == 429:
                raise RateLimitError(
                    f"HTTP 429 for {url}",
                    retry_after=_retry_after_seconds(res.headers.get("retry-after") or res.headers.get("Retry-After")),
                )
            if res.status_code in RETRY_STATUSES and res.defense_detected == DefenseSystem.NONE:
                raise ServerError(f"HTTP {res.status_code} for {url}", status_code=res.status_code)
            return res

        try:
            if self.retries == 0:
                result = await attempt()
            else:
                result = await with_retry(
                    attempt,
                    max_retries=self.retries,
                    initial_delay=self.retry_delay,
                    retry_on=(NetworkError, RateLimitError, ServerError),
                )
        except (ServerError, RateLimitError):
            # Retries exhausted on an HTTP status: hand back the last real response.
            self._record_failure(domain)
            return last["result"]
        except Exception as exc:
            self._record_failure(domain)
            if self.dead_letter:
                self.dead_letter.record(url, type(exc).__name__, str(exc))
            raise
        if self.circuit_breaker:
            blocked = (result.defense_detected != DefenseSystem.NONE or result.status_code >= 400) and is_blocked(result)
            if blocked:
                self.circuit_breaker.record_failure(domain)  # a site that blocks every request should trip it
            else:
                self.circuit_breaker.record_success(domain)
        return result

    def _record_failure(self, domain: str) -> None:
        if self.circuit_breaker:
            self.circuit_breaker.record_failure(domain)

    # ------------------------------------------------------------------ scraping
    async def scrape(self, url: str, tier: Optional[FetcherRef] = None, **kwargs: Any) -> ScrapeResult:
        """Fetch and extract title, markdown, structured data, product/article and links."""
        fetch_res = await self.fetch(url, tier=tier, **kwargs)
        return build_scrape_result(fetch_res, url)

    async def fetch_many(
        self,
        urls: Sequence[str],
        *,
        concurrency: int = 8,
        per_domain_concurrency: int = 4,
        delay: float = 0.0,
        tier: Optional[FetcherRef] = None,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> list[Union[FetchResult, Exception]]:
        """Fetch multiple URLs concurrently with global and per-domain politeness throttling."""
        from omniscrape.crawler.throttle import DomainThrottle

        sem = asyncio.Semaphore(max(1, concurrency))
        throttle = DomainThrottle(per_domain_concurrency=max(1, per_domain_concurrency), download_delay=delay)

        async def _one(u: str) -> Union[FetchResult, Exception]:
            dom = domain_of(u)
            async with sem:
                await throttle.acquire(dom)
                try:
                    return await self.fetch(u, tier=tier, **kwargs)
                except Exception as exc:
                    if return_exceptions:
                        return exc
                    raise
                finally:
                    throttle.release(dom)

        return list(await asyncio.gather(*(_one(u) for u in urls)))

    async def scrape_many(
        self,
        urls: Sequence[str],
        *,
        concurrency: int = 8,
        per_domain_concurrency: int = 4,
        delay: float = 0.0,
        tier: Optional[FetcherRef] = None,
        return_exceptions: bool = False,
        **kwargs: Any,
    ) -> list[Union[ScrapeResult, Exception]]:
        """Fetch and extract structured data + Markdown for multiple URLs concurrently."""
        results = await self.fetch_many(
            urls,
            concurrency=concurrency,
            per_domain_concurrency=per_domain_concurrency,
            delay=delay,
            tier=tier,
            return_exceptions=return_exceptions,
            **kwargs,
        )
        out: list[Union[ScrapeResult, Exception]] = []
        for u, res in zip(urls, results):
            out.append(res if isinstance(res, Exception) else build_scrape_result(res, u))
        return out

    async def iter_scrape(
        self,
        urls: Sequence[str],
        *,
        concurrency: int = 8,
        per_domain_concurrency: int = 4,
        delay: float = 0.0,
        tier: Optional[FetcherRef] = None,
        **kwargs: Any,
    ) -> AsyncIterator[tuple[str, ScrapeResult]]:
        """Yield ``(url, ScrapeResult)`` pairs as each URL finishes."""
        from omniscrape.crawler.throttle import DomainThrottle

        sem = asyncio.Semaphore(max(1, concurrency))
        throttle = DomainThrottle(per_domain_concurrency=max(1, per_domain_concurrency), download_delay=delay)

        async def _one(u: str) -> tuple[str, ScrapeResult]:
            dom = domain_of(u)
            async with sem:
                await throttle.acquire(dom)
                try:
                    res = await self.fetch(u, tier=tier, **kwargs)
                    return u, build_scrape_result(res, u)
                finally:
                    throttle.release(dom)

        tasks = [asyncio.create_task(_one(u)) for u in urls]
        for fut in asyncio.as_completed(tasks):
            yield await fut


def build_scrape_result(fetch_res: FetchResult, url: Optional[str] = None) -> ScrapeResult:
    """Turn a FetchResult into a ScrapeResult (no network access)."""
    from omniscrape.content.markdown import fit_markdown
    from omniscrape.parsers.selector import Selector
    from omniscrape.parsers.semantic import SemanticExtractor

    page_url = fetch_res.url or url or ""
    html = fetch_res.html
    selector = Selector(html)  # the page is parsed once; every extractor below shares this tree
    semantic = SemanticExtractor(html, url=page_url, root=selector.root)

    title_el = selector.css("title")
    title = title_el[0].text if title_el else ""
    if not title:
        title = semantic.extract_opengraph().get("og:title", "")
    fit = fit_markdown(selector.root, page_url, main=semantic.main)

    links: list[str] = []
    seen: set[str] = set()
    for el in selector.css("a[href]"):
        href = (el.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        absolute = urljoin(page_url, href)
        if absolute not in seen:
            seen.add(absolute)
            links.append(absolute)

    all_structured = semantic.extract_all()
    return ScrapeResult(
        url=url or page_url,
        status_code=fetch_res.status_code,
        title=title,
        html=html,
        markdown=fit,
        fit_markdown=fit,
        metadata=semantic.metadata,
        structured_data=all_structured,
        product=all_structured["product"],
        article=all_structured["article"],
        links=links[:100],
        latency_ms=fetch_res.latency_ms,
        fetcher_tier=fetch_res.fetcher_tier,
    )
