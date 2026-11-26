"""Tier 2: Dynamic headless Chromium JS execution fetcher."""

import time
from typing import Optional
from omniscrape.exceptions import ConnectionTimeoutError, NetworkError
from omniscrape.fetchers.base import BaseFetcher, playwright_proxy
from omniscrape.models import FetchResult, DefenseSystem
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.browser")


class DynamicFetcher(BaseFetcher):
    """Tier 2: Playwright-backed headless browser for Single Page Apps (SPA)."""

    def __init__(
        self,
        headless: bool = True,
        block_resources: bool = True,
    ):
        self.headless = headless
        self.block_resources = block_resources
        self._playwright = None
        self._browser = None

    async def _init_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

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
        wait_until: str = "domcontentloaded",
        **kwargs,
    ) -> FetchResult:
        await self._init_browser()
        start_time = time.perf_counter()

        proxy_config = playwright_proxy(proxy)

        context = await self._browser.new_context(
            proxy=proxy_config,
            extra_http_headers=headers or {},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )

        if cookies:
            cookie_list = [{"name": k, "value": v, "url": url} for k, v in cookies.items()]
            await context.add_cookies(cookie_list)

        page = await context.new_page()

        if self.block_resources:
            # Block images, fonts, and media to increase rendering speed
            async def route_filter(route):
                if route.request.resource_type in ["image", "media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", route_filter)

        try:
            resp = await page.goto(url, timeout=int(timeout * 1000), wait_until=wait_until)
            # Give short window for SPA hydration
            await page.wait_for_timeout(500)

            content = await page.content()
            status = resp.status if resp else 200
            resp_headers = await resp.all_headers() if resp else {}
            curr_cookies = {c["name"]: c["value"] for c in await context.cookies()}
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            global_metrics.inc("fetch_tier2_requests")
            global_metrics.observe_latency("fetch_tier2_latency", elapsed_ms)

            return FetchResult(
                url=page.url,
                status_code=status,
                headers=resp_headers,
                html=content,
                cookies=curr_cookies,
                latency_ms=round(elapsed_ms, 2),
                fetcher_tier=2,
                defense_detected=DefenseSystem.NONE,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            global_metrics.inc("fetch_tier2_errors")
            if "timeout" in str(exc).lower():
                raise ConnectionTimeoutError(f"Tier 2 browser timeout for {url}: {exc}") from exc
            raise NetworkError(f"Tier 2 browser error for {url}: {exc}") from exc
        finally:
            await context.close()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
