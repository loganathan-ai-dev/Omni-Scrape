"""Tier 3: Hardened browser fetcher (Camoufox if installed, otherwise Playwright Chromium).

Escalation to this tier is opt-in (``allow_stealth=True``). It does not solve CAPTCHAs; if a
challenge is still present after loading, the result is returned with ``defense_detected`` set
so the caller can treat it as an access restriction.
"""

import asyncio
import time
from typing import Any, Optional

from omniscrape.classifier.detector import detect_defense
from omniscrape.fetchers.actions import run_playwright_fetch
from omniscrape.fetchers.base import DEFAULT_USER_AGENT, BaseFetcher, playwright_proxy
from omniscrape.fetchers.browser import BLOCKED_TYPES
from omniscrape.fetchers.http import wrap_network_error
from omniscrape.models import FetchResult
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.stealth")

_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
"""


class StealthFetcher(BaseFetcher):
    """Tier 3: one long-lived hardened browser; a fresh context per request."""

    tier = 3

    def __init__(
        self,
        headless: bool = True,
        block_resources: bool = False,
        wait_until: str = "domcontentloaded",
        settle_ms: int = 120,
        max_settle_ms: int = 2500,
        capture_network: bool = False,
    ):
        self.headless = headless
        self.block_resources = block_resources
        self.wait_until = wait_until
        self.settle_ms = settle_ms
        self.max_settle_ms = max_settle_ms
        self.capture_network = capture_network
        self._camoufox_cm: Any = None
        self._playwright: Any = None
        self._browser: Any = None
        self._launch_lock = asyncio.Lock()
        try:
            import camoufox  # noqa: F401

            self._camoufox_available = True
        except ImportError:
            self._camoufox_available = False

    async def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        async with self._launch_lock:  # concurrent first requests must share one browser
            if self._browser is None:
                await self._launch()

    async def _launch(self) -> None:
        if self._camoufox_available:
            from camoufox.async_api import AsyncCamoufox

            self._camoufox_cm = AsyncCamoufox(headless=self.headless)
            self._browser = await self._camoufox_cm.__aenter__()
        else:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            )

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        proxy: Optional[str] = None,
        timeout: float = 45.0,
        follow_redirects: bool = True,
        wait_until: Optional[str] = None,
        wait_for: Optional[str] = None,
        actions: Optional[list[dict[str, Any]]] = None,
        screenshot: bool = False,
        full_page: bool = True,
        pdf: bool = False,
        capture_network: Optional[bool] = None,
        **kwargs: Any,
    ) -> FetchResult:
        await self._ensure_browser()
        start_time = time.perf_counter()

        context_args: dict[str, Any] = {"proxy": playwright_proxy(proxy), "extra_http_headers": headers or {}}
        if not self._camoufox_available:
            context_args["user_agent"] = DEFAULT_USER_AGENT
        context = await self._browser.new_context(**context_args)
        try:
            if not self._camoufox_available:
                await context.add_init_script(_INIT_SCRIPT)
            if self.block_resources:
                async def route_filter(route: Any) -> None:
                    if route.request.resource_type in BLOCKED_TYPES:
                        await route.abort()
                    else:
                        await route.continue_()

                await context.route("**/*", route_filter)
            if cookies:
                await context.add_cookies([{"name": k, "value": v, "url": url} for k, v in cookies.items()])

            page = await context.new_page()
            data = await run_playwright_fetch(
                context,
                page,
                url,
                timeout=timeout,
                wait_until=wait_until or self.wait_until,
                wait_for=wait_for,
                settle_ms=self.settle_ms,
                max_settle_ms=self.max_settle_ms,
                actions=actions,
                screenshot=screenshot,
                full_page=full_page,
                pdf=pdf,
                headless=self.headless,
                capture_network=capture_network if capture_network is not None else self.capture_network,
            )
        except Exception as exc:
            global_metrics.inc("fetch_tier3_errors")
            raise wrap_network_error(3, url, exc) from exc
        finally:
            await context.close()

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        global_metrics.inc("fetch_tier3_requests")
        global_metrics.observe_latency("fetch_tier3_latency", elapsed_ms)
        return FetchResult(
            url=data["url"],
            status_code=data["status_code"],
            headers=data["headers"],
            html=data["html"],
            cookies=data["cookies"],
            latency_ms=round(elapsed_ms, 2),
            fetcher_tier=3,
            defense_detected=detect_defense(data["status_code"], data["headers"], data["html"]),
            screenshot=data["screenshot"],
            pdf=data["pdf"],
            network=data["network"],
            actions_log=data["actions_log"],
            action_results=data["action_results"],
        )

    async def close(self) -> None:
        try:
            if self._camoufox_cm is not None:
                await self._camoufox_cm.__aexit__(None, None, None)
            elif self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._camoufox_cm = self._browser = self._playwright = None
