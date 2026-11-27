"""Tier 1: High-speed HTTP/2 fetcher with browser TLS fingerprints (curl_cffi)."""

import time
from typing import Any, Optional

from curl_cffi.requests import AsyncSession

from omniscrape.classifier.detector import detect_defense
from omniscrape.exceptions import (
    ConnectionTimeoutError,
    DNSResolutionError,
    NetworkError,
    SSLHandshakeError,
)
from omniscrape.fetchers.base import DEFAULT_USER_AGENT, BaseFetcher
from omniscrape.models import FetchResult
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.http")

DEFAULT_HEADERS = {
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
    "User-Agent": DEFAULT_USER_AGENT,
}


def wrap_network_error(tier: int, url: str, exc: Exception) -> NetworkError:
    """Map a transport exception to the OmniScrape error taxonomy."""
    msg = str(exc)
    low = msg.lower()
    if "timeout" in low or "timed out" in low:
        return ConnectionTimeoutError(f"Tier {tier} timeout for {url}: {msg}")
    if "resolve" in low or "getaddrinfo" in low or "name or service" in low:
        return DNSResolutionError(f"Tier {tier} DNS failure for {url}: {msg}")
    if "ssl" in low or "certificate" in low or "tls" in low:
        return SSLHandshakeError(f"Tier {tier} TLS failure for {url}: {msg}")
    return NetworkError(f"Tier {tier} network error for {url}: {msg}")


class FastFetcher(BaseFetcher):
    """Tier 1: curl_cffi fetcher with TLS browser impersonation and connection reuse."""

    tier = 1

    def __init__(
        self,
        impersonate: str = "chrome124",
        max_connections: int = 25,
        default_headers: Optional[dict[str, str]] = None,
        verify: bool = True,
    ):
        self.impersonate = impersonate
        self.max_connections = max_connections
        self.default_headers = dict(default_headers or DEFAULT_HEADERS)
        self.verify = verify
        self._session: Optional[AsyncSession] = None

    async def _get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = AsyncSession(
                impersonate=self.impersonate,
                headers=self.default_headers,
                max_clients=self.max_connections,
                verify=self.verify,
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
        data: Any = None,
        json: Any = None,
        params: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> FetchResult:
        session = await self._get_session()
        start_time = time.perf_counter()
        if headers:
            req_headers = dict(self.default_headers)
            req_headers.update(headers)
        else:
            req_headers = None

        try:
            resp = await session.request(
                method=method.upper(),
                url=url,
                headers=req_headers,
                cookies=cookies,
                proxies={"all": proxy} if proxy else None,
                timeout=timeout,
                allow_redirects=follow_redirects,
                data=data,
                json=json,
                params=params,
            )
        except Exception as exc:
            global_metrics.inc("fetch_tier1_errors")
            raise wrap_network_error(1, url, exc) from exc

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        global_metrics.inc("fetch_tier1_requests")
        global_metrics.observe_latency("fetch_tier1_latency", elapsed_ms)

        html_text = resp.text or ""
        resp_headers = dict(resp.headers)
        return FetchResult(
            url=str(resp.url),
            status_code=resp.status_code,
            headers=resp_headers,
            html=html_text,
            cookies=dict(resp.cookies),
            latency_ms=round(elapsed_ms, 2),
            fetcher_tier=1,
            defense_detected=detect_defense(resp.status_code, resp_headers, html_text),
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
