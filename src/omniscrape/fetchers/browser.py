"""Tier 2: Playwright Chromium for JavaScript-rendered pages.

* One browser per fetcher (launched once, even under concurrent first requests).
* Readiness: ``wait_until`` + optional ``wait_for`` selector + DOM settle (mutation-quiet), not a fixed sleep.
* ``isolate=True`` (default) gives every fetch a fresh context (no shared cookies); ``isolate=False``
  reuses one context per proxy/header set, which is faster for crawls of public pages.
* Page actions, infinite scroll, screenshots, PDF and capture of XHR/fetch JSON responses.
* ``cdp_url`` attaches to a running Chromium-compatible browser (e.g. Lightpanda, remote Chrome);
  ``user_data_dir`` keeps a persistent profile (logins, cookies).
"""

import asyncio
import time
from typing import Any, Optional

from omniscrape.classifier.detector import detect_defense
from omniscrape.fetchers.actions import run_playwright_fetch
from omniscrape.fetchers.base import DEFAULT_USER_AGENT, BaseFetcher, playwright_proxy
from omniscrape.fetchers.http import wrap_network_error
from omniscrape.models import FetchResult
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.browser")

BLOCKED_TYPES = {"image", "media", "font"}
LAUNCH_ARGS = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
               "--disable-blink-features=AutomationControlled"]


class DynamicFetcher(BaseFetcher):
    tier = 2

    def __init__(
        self,
        headless: bool = True,
        block_resources: bool = True,
        wait_until: str = "load",
        settle_ms: int = 40,
        max_settle_ms: int = 3000,
        isolate: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        viewport: Optional[dict[str, int]] = None,
        executable_path: Optional[str] = None,
        cdp_url: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        capture_network: bool = False,
        max_idle_pages: int = 4,
        recycle_after: int = 25,
    ):
        self.headless = headless
        self.block_resources = block_resources
        self.wait_until = wait_until
        self.settle_ms = settle_ms
        self.max_settle_ms = max_settle_ms
        self.isolate = isolate and not user_data_dir
        self.user_agent = user_agent
        self.viewport = viewport or {"width": 1366, "height": 900}
        self.executable_path = executable_path
        self.cdp_url = cdp_url
        self.user_data_dir = user_data_dir
        self.capture_network = capture_network
        self.max_idle_pages = max_idle_pages
        self.recycle_after = recycle_after
        self._idle_pages: dict[int, list[Any]] = {}   # shared-context mode: reusable tabs per context
        self._page_uses: dict[int, int] = {}
        self._playwright: Any = None
        self._browser: Any = None
        self._persistent: Any = None
        self._contexts: dict[tuple, Any] = {}
        self._launch_lock = asyncio.Lock()

    # ------------------------------------------------------------------ lifecycle
    async def _init_browser(self) -> None:
        if self._browser is not None or self._persistent is not None:
            return
        async with self._launch_lock:  # concurrent first requests must share one browser
            if self._browser is None and self._persistent is None:
                await self._launch()

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        if self.cdp_url:
            self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
        elif self.user_data_dir:
            self._persistent = await self._playwright.chromium.launch_persistent_context(
                self.user_data_dir, headless=self.headless, args=LAUNCH_ARGS, user_agent=self.user_agent,
                viewport=self.viewport, executable_path=self.executable_path)
            await self._install_blocking(self._persistent)
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless, args=LAUNCH_ARGS, executable_path=self.executable_path)

    async def _install_blocking(self, context: Any) -> None:
        if not self.block_resources:
            return

        async def route_filter(route: Any) -> None:
            if route.request.resource_type in BLOCKED_TYPES:
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", route_filter)

    async def _new_context(self, proxy: Optional[str], headers: Optional[dict[str, str]]) -> Any:
        context = await self._browser.new_context(
            proxy=playwright_proxy(proxy), extra_http_headers=headers or {}, user_agent=self.user_agent,
            viewport=self.viewport)
        await self._install_blocking(context)
        return context

    async def _context_for(self, proxy: Optional[str], headers: Optional[dict[str, str]]) -> tuple[Any, bool]:
        """Return (context, owned). Owned contexts are closed after the fetch."""
        if self._persistent is not None:
            return self._persistent, False
        if self.isolate:
            return await self._new_context(proxy, headers), True
        key = (proxy, tuple(sorted((headers or {}).items())))
        if key not in self._contexts:
            self._contexts[key] = await self._new_context(proxy, headers)
        return self._contexts[key], False

    # ------------------------------------------------------------------ fetch
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
        wait_until: Optional[str] = None,
        wait_for: Optional[str] = None,
        actions: Optional[list[dict[str, Any]]] = None,
        screenshot: bool = False,
        full_page: bool = True,
        pdf: bool = False,
        capture_network: Optional[bool] = None,
        **kwargs: Any,
    ) -> FetchResult:
        await self._init_browser()
        start = time.perf_counter()
        context, owned = await self._context_for(proxy, headers)
        page = None
        try:
            if cookies:
                await context.add_cookies([{"name": k, "value": v, "url": url} for k, v in cookies.items()])
            page = self._take_idle_page(context) if not owned else None
            page = page or await context.new_page()
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
            global_metrics.inc("fetch_tier2_errors")
            raise wrap_network_error(2, url, exc) from exc
        finally:
            if page is not None:
                await self._release_page(context, page, owned)
            if owned:
                await context.close()

        elapsed_ms = (time.perf_counter() - start) * 1000
        global_metrics.inc("fetch_tier2_requests")
        global_metrics.observe_latency("fetch_tier2_latency", elapsed_ms)
        return FetchResult(
            url=data["url"],
            status_code=data["status_code"],
            headers=data["headers"],
            html=data["html"],
            cookies=data["cookies"],
            latency_ms=round(elapsed_ms, 2),
            fetcher_tier=2,
            defense_detected=detect_defense(data["status_code"], data["headers"], data["html"]),
            screenshot=data["screenshot"],
            pdf=data["pdf"],
            network=data["network"],
            actions_log=data["actions_log"],
            action_results=data["action_results"],
        )

    def _take_idle_page(self, context: Any) -> Optional[Any]:
        pool = self._idle_pages.get(id(context), [])
        while pool:
            page = pool.pop()
            if not page.is_closed():
                return page
        return None

    async def _release_page(self, context: Any, page: Any, owned: bool) -> None:
        """Return a tab to the pool (shared-context mode) or close it."""
        try:
            pid = id(page)
            uses = self._page_uses.get(pid, 0) + 1
            pool = self._idle_pages.setdefault(id(context), [])
            if (not owned and not page.is_closed() and len(pool) < self.max_idle_pages
                    and uses < self.recycle_after):
                self._page_uses[pid] = uses
                pool.append(page)
            else:
                self._page_uses.pop(pid, None)
                await page.close()
        except Exception:
            pass  # the page or browser is already gone

    async def close(self) -> None:
        self._idle_pages.clear()
        self._page_uses.clear()
        try:
            for ctx in self._contexts.values():
                try:
                    await ctx.close()
                except Exception:
                    pass
            if self._persistent is not None:
                await self._persistent.close()
            if self._browser is not None:
                await self._browser.close()
            if self._playwright is not None:
                await self._playwright.stop()
        finally:
            self._contexts.clear()
            self._browser = self._persistent = self._playwright = None
