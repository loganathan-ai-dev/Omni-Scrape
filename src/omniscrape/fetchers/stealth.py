"""Tier 3: Stealth anti-bot evasion fetcher (Camoufox or stealth Playwright fallback)."""

import time
from typing import Optional
from omniscrape.exceptions import ConnectionTimeoutError, NetworkError, AntiBot403Error
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.models import FetchResult, DefenseSystem
from omniscrape.observability.logging import get_logger
from omniscrape.observability.metrics import global_metrics

logger = get_logger("omniscrape.fetchers.stealth")


class StealthFetcher(BaseFetcher):
    """Tier 3: Anti-bot warfare browser designed to bypass Cloudflare Turnstile, DataDome, and PerimeterX."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._camoufox_available = False
        try:
            import camoufox
            self._camoufox_available = True
        except ImportError:
            self._camoufox_available = False

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
        **kwargs,
    ) -> FetchResult:
        start_time = time.perf_counter()

        if self._camoufox_available:
            return await self._fetch_camoufox(url, headers, cookies, proxy, timeout, start_time)
        else:
            return await self._fetch_stealth_playwright(url, headers, cookies, proxy, timeout, start_time)

    async def _fetch_camoufox(self, url, headers, cookies, proxy, timeout, start_time) -> FetchResult:
        from camoufox.async_api import AsyncCamoufox
        proxy_config = {"server": proxy} if proxy else None

        async with AsyncCamoufox(headless=self.headless, proxy=proxy_config) as browser:
            page = await browser.new_page()
            if headers:
                await page.set_extra_http_headers(headers)
            resp = await page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
            # Wait for any challenge clearance
            await page.wait_for_timeout(2000)

            content = await page.content()
            status = resp.status if resp else 200
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            global_metrics.inc("fetch_tier3_requests")
            return FetchResult(
                url=page.url,
                status_code=status,
                headers={},
                html=content,
                cookies={},
                latency_ms=round(elapsed_ms, 2),
                fetcher_tier=3,
                defense_detected=DefenseSystem.CLOUDFLARE,
            )

    async def _fetch_stealth_playwright(self, url, headers, cookies, proxy, timeout, start_time) -> FetchResult:
        from playwright.async_api import async_playwright
        proxy_config = {"server": proxy} if proxy else None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = await browser.new_context(
                proxy=proxy_config,
                extra_http_headers=headers or {},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            # Inject anti-detection evasions
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)

            page = await context.new_page()
            try:
                resp = await page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
                # Wait for interstitial challenge or turnstile to clear
                await page.wait_for_timeout(2500)

                content = await page.content()
                status = resp.status if resp else 200
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                global_metrics.inc("fetch_tier3_requests")
                return FetchResult(
                    url=page.url,
                    status_code=status,
                    headers=await resp.all_headers() if resp else {},
                    html=content,
                    cookies={c["name"]: c["value"] for c in await context.cookies()},
                    latency_ms=round(elapsed_ms, 2),
                    fetcher_tier=3,
                    defense_detected=DefenseSystem.CLOUDFLARE,
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                global_metrics.inc("fetch_tier3_errors")
                if "timeout" in str(exc).lower():
                    raise ConnectionTimeoutError(f"Tier 3 stealth timeout for {url}: {exc}") from exc
                raise NetworkError(f"Tier 3 stealth error for {url}: {exc}") from exc
            finally:
                await browser.close()

    async def close(self) -> None:
        pass
