"""Tier 1: High-speed HTTP/2 and TLS fingerprint impersonation fetcher."""

import time
from typing import Optional
from curl_cffi.requests import AsyncSession
from omniscrape.exceptions import ConnectionTimeoutError, NetworkError, ServerError, AntiBot403Error
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.models import FetchResult, DefenseSystem
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.http")


class FastFetcher(BaseFetcher):
    """Tier 1: High-speed curl_cffi fetcher with TLS browser impersonation."""

    def __init__(
        self,
        impersonate: str = "chrome124",
        max_connections: int = 25,
        default_headers: Optional[dict[str, str]] = None,
    ):
        self.impersonate = impersonate
        self.max_connections = max_connections
        self.default_headers = default_headers or {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        self._session: Optional[AsyncSession] = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(
                impersonate=self.impersonate,
                headers=self.default_headers,
            )
        return self._session

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        proxy: Optional[str] = None,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        **kwargs,
    ) -> FetchResult:
        session = await self._get_session()
        start_time = time.perf_counter()
        proxies = {"all": proxy} if proxy else None

        req_headers = dict(self.default_headers)
        if headers:
            req_headers.update(headers)

        try:
            resp = await session.request(
                method=method,
                url=url,
                headers=req_headers,
                cookies=cookies,
                proxies=proxies,
                timeout=timeout,
                allow_redirects=follow_redirects,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            global_metrics.inc("fetch_tier1_requests")
            global_metrics.observe_latency("fetch_tier1_latency", elapsed_ms)

            # Detect basic anti-bot signals in response headers
            defense = DefenseSystem.NONE
            header_keys = {k.lower(): v for k, v in resp.headers.items()}
            if "cf-ray" in header_keys or "server" in header_keys and "cloudflare" in header_keys["server"].lower():
                defense = DefenseSystem.CLOUDFLARE
            elif "x-datadome" in header_keys or any(k.startswith("x-dd-") for k in header_keys):
                defense = DefenseSystem.DATADOME

            html_text = resp.text or ""

            return FetchResult(
                url=str(resp.url),
                status_code=resp.status_code,
                headers=dict(resp.headers),
                html=html_text,
                cookies=dict(resp.cookies),
                latency_ms=round(elapsed_ms, 2),
                fetcher_tier=1,
                defense_detected=defense,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            global_metrics.inc("fetch_tier1_errors")
            msg = str(exc)
            if "timeout" in msg.lower():
                raise ConnectionTimeoutError(f"Tier 1 fetch timeout for {url}: {msg}") from exc
            raise NetworkError(f"Tier 1 fetch network error for {url}: {msg}") from exc

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
