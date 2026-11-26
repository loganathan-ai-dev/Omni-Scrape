"""Optional httpx-based fetcher (HTTP/1.1 + HTTP/2). Requires ``pip install httpx[http2]``."""

import time
from typing import Any, Optional

from omniscrape.classifier.detector import detect_defense
from omniscrape.fetchers.base import DEFAULT_USER_AGENT, BaseFetcher
from omniscrape.fetchers.http import wrap_network_error
from omniscrape.models import FetchResult
from omniscrape.observability.metrics import global_metrics


class HttpxFetcher(BaseFetcher):
    """Plain httpx client: no TLS impersonation, standards-compliant, good for APIs and feeds."""

    tier = 1

    def __init__(self, http2: bool = True, max_connections: int = 50, verify: bool = True,
                 default_headers: Optional[dict[str, str]] = None):
        self.http2 = http2
        self.max_connections = max_connections
        self.verify = verify
        self.default_headers = default_headers or {"User-Agent": DEFAULT_USER_AGENT}
        self._clients: dict[Optional[str], Any] = {}

    def _client(self, proxy: Optional[str]) -> Any:
        import httpx

        if proxy not in self._clients:
            try:
                import h2  # noqa: F401

                http2 = self.http2
            except ImportError:
                http2 = False
            self._clients[proxy] = httpx.AsyncClient(
                http2=http2,
                proxy=proxy,
                verify=self.verify,
                headers=self.default_headers,
                limits=httpx.Limits(max_connections=self.max_connections),
            )
        return self._clients[proxy]

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
        client = self._client(proxy)
        start = time.perf_counter()
        try:
            resp = await client.request(
                method.upper(), url, headers=headers, cookies=cookies, timeout=timeout,
                follow_redirects=follow_redirects, data=data, json=json, params=params,
            )
        except Exception as exc:
            global_metrics.inc("fetch_httpx_errors")
            raise wrap_network_error(1, url, exc) from exc
        elapsed_ms = (time.perf_counter() - start) * 1000
        global_metrics.inc("fetch_httpx_requests")
        global_metrics.observe_latency("fetch_httpx_latency", elapsed_ms)
        resp_headers = dict(resp.headers)
        return FetchResult(
            url=str(resp.url),
            status_code=resp.status_code,
            headers=resp_headers,
            html=resp.text,
            cookies=dict(resp.cookies),
            latency_ms=round(elapsed_ms, 2),
            fetcher_tier=1,
            defense_detected=detect_defense(resp.status_code, resp_headers, resp.text),
        )

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
