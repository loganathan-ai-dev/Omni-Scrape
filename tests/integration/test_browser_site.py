"""Browser integration tests (tier 2 and tier 3) against the local test site. Marked ``browser``."""

import asyncio

import pytest

from omniscrape.client import OmniClient
from omniscrape.fetchers.browser import DynamicFetcher

pytestmark = pytest.mark.browser


async def test_auto_mode_escalates_js_shell_to_browser(site):
    async with OmniClient(retries=0) as client:
        res = await client.fetch(site.base + "/js/3")
    assert res.fetcher_tier == 2
    assert "Hydrated content for page 3" in res.html


async def test_concurrent_renders_share_one_browser(site):
    fetcher = DynamicFetcher()
    try:
        results = await asyncio.gather(*(fetcher.fetch(f"{site.base}/js/{i}") for i in range(6)))
        assert all(f"Hydrated content for page {i}" in r.html for i, r in enumerate(results))
        assert fetcher._browser is not None and len(fetcher._browser.contexts) == 0  # isolated contexts closed
    finally:
        await fetcher.close()


async def test_actions_click_type_and_screenshot(site):
    fetcher = DynamicFetcher()
    try:
        res = await fetcher.fetch(site.base + "/interactive", actions=[
            {"type": "click", "selector": "#more"},
            {"type": "type", "selector": "#q", "text": "lamps"},
            {"type": "click", "selector": "#go"},
            {"type": "evaluate", "script": "() => document.querySelectorAll('.deal').length"},
        ], screenshot=True)
        assert "Secret deal unlocked" in res.html and "You searched: lamps" in res.html
        assert res.action_results == [1]
        assert all(step["ok"] for step in res.actions_log)
        assert res.screenshot and res.screenshot[:8] == b"\x89PNG\r\n\x1a\n"
    finally:
        await fetcher.close()


async def test_failed_action_is_reported_not_raised(site):
    fetcher = DynamicFetcher()
    try:
        res = await fetcher.fetch(site.base + "/interactive",
                                  actions=[{"type": "click", "selector": "#does-not-exist", "optional": False}],
                                  timeout=3)
        assert res.actions_log[0]["ok"] is False and "Timeout" in res.actions_log[0]["error"]
    finally:
        await fetcher.close()


async def test_infinite_scroll_loads_more_items(site):
    fetcher = DynamicFetcher()
    try:
        res = await fetcher.fetch(site.base + "/infinite", actions=[{"type": "infinite_scroll", "max_scrolls": 8}])
        assert res.html.count('class="item"') > 10
    finally:
        await fetcher.close()


async def test_network_capture_returns_api_json(site):
    fetcher = DynamicFetcher(capture_network=True)
    try:
        res = await fetcher.fetch(site.base + "/spa", wait_for=".product")
        assert "Lamp 4" in res.html
        api = [n for n in res.network if n["url"].endswith("/api/items")]
        assert api and api[0]["json"]["items"][0]["name"] == "Lamp 0"
    finally:
        await fetcher.close()


async def test_shared_context_mode_is_reused(site):
    fetcher = DynamicFetcher(isolate=False)
    try:
        await fetcher.fetch(site.base + "/js/1")
        await fetcher.fetch(site.base + "/js/2")
        assert len(fetcher._contexts) == 1
    finally:
        await fetcher.close()


async def test_stealth_tier_renders_local_page(site):
    async with OmniClient(retries=0) as client:
        res = await client.fetch(site.base + "/js/5", tier=3)
    assert res.fetcher_tier == 3 and "Hydrated content for page 5" in res.html
