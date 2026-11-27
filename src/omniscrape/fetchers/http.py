"""Tier 1: High-speed HTTP/2 (and optional HTTP/3) fetcher with browser TLS fingerprints (curl_cffi).

Each request impersonates a real browser end to end: TLS/JA3 and HTTP/2 fingerprints *and* the matching
User-Agent and client-hint headers come from the same curl_cffi profile, so they never contradict each other.
Pass several profiles to rotate between them (sticky per domain by default).
"""

import itertools
import time
import zlib
from typing import Any, Optional, Sequence, Union, cast
from urllib.parse import urlsplit

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

# Browser families curl_cffi can impersonate; each alias tracks the newest version of that browser it ships.
BROWSER_PROFILES = ("chrome", "edge", "safari", "firefox", "chrome_android", "safari_ios")
_HTTP_VERSIONS = {"1": "v1", "1.1": "v1", "http1": "v1", "v1": "v1", "2": "v2", "h2": "v2", "http2": "v2", "v2": "v2",
                  "3": "v3", "h3": "v3", "http3": "v3", "v3": "v3", "3only": "v3only", "v3only": "v3only"}

# Extra headers sent on top of the impersonated browser's own headers (curl_cffi supplies User-Agent,
# Accept, Sec-Ch-Ua, Sec-Fetch-* to match each profile).
BASE_HEADERS = {"Accept-Language": "en-US,en;q=0.9"}

# Legacy fixed Chrome 124 header set, kept for callers that import it; no longer sent by default.
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


def normalize_http_version(value: Any) -> Optional[str]:
    """``3`` / ``"h3"`` / ``"http3"`` -> ``"v3"`` (curl_cffi's spelling); ``None`` keeps the default (HTTP/2)."""
    if value is None or value == "":
        return None
    key = str(value).strip().lower()
    if key not in _HTTP_VERSIONS:
        raise ValueError(f"unknown http_version {value!r}; use 1.1, 2, 3 or 3only")
    return _HTTP_VERSIONS[key]


class FastFetcher(BaseFetcher):
    """Tier 1: curl_cffi fetcher with browser impersonation, profile rotation and connection reuse.

    ``impersonate`` is one curl_cffi profile (``"chrome"``, ``"safari"``, ``"firefox"``, ``"edge"``,
    ``"chrome_android"``, ``"safari_ios"`` or a pinned version such as ``"chrome131"``) or a list of them.
    With a list, ``rotate="domain"`` (default) gives each host one stable browser identity and
    ``rotate="request"`` cycles through the list on every request. ``http_version="3"`` enables HTTP/3.
    Per request, ``fetch(url, impersonate="safari", http_version="3")`` overrides both.
    """

    tier = 1

    def __init__(
        self,
        impersonate: Union[str, Sequence[str]] = "chrome",
        max_connections: int = 25,
        default_headers: Optional[dict[str, str]] = None,
        verify: bool = True,
        rotate: str = "domain",
        http_version: Any = None,
    ):
        profiles = [impersonate] if isinstance(impersonate, str) else [p for p in impersonate if p]
        if not profiles:
            raise ValueError("impersonate needs at least one browser profile")
        if rotate not in ("domain", "request"):
            raise ValueError("rotate must be 'domain' or 'request'")
        self.profiles = profiles
        self.impersonate = profiles[0]
        self.rotate = rotate
        self.http_version = normalize_http_version(http_version)
        self.max_connections = max_connections
        self.default_headers = dict(BASE_HEADERS if default_headers is None else default_headers)
        self.verify = verify
        self._cycle = itertools.cycle(profiles)
        self._session: Optional[AsyncSession] = None

    def profile_for(self, url: str) -> str:
        """The browser profile this fetcher uses for ``url``."""
        if len(self.profiles) == 1:
            return self.profiles[0]
        if self.rotate == "request":
            return next(self._cycle)
        host = (urlsplit(url).hostname or "").lower()
        return self.profiles[zlib.crc32(host.encode()) % len(self.profiles)]

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
        profile = kwargs.pop("impersonate", None) or self.profile_for(url)
        http_version = normalize_http_version(kwargs.pop("http_version", None)) or self.http_version
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
                impersonate=cast(Any, profile),        # validated by curl_cffi at request time
                http_version=cast(Any, http_version),
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
