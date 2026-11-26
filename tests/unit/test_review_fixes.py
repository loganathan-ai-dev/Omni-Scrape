"""Regression tests for code-review findings on the Phase 0 fetch layer."""

import asyncio

import pytest

from omniscrape.classifier.detector import detect_defense
from omniscrape.client import OmniClient
from omniscrape.exceptions import CircuitBreakerOpenError, DNSResolutionError, SSLHandshakeError
from omniscrape.fetchers.base import playwright_proxy
from omniscrape.fetchers.browser import DynamicFetcher
from omniscrape.fetchers.stealth import StealthFetcher
from omniscrape.models import DefenseSystem
from omniscrape.resilience.circuit_breaker import CircuitBreaker
from tests.unit.test_client_and_fetch import ScriptedFetcher, install

TURNSTILE_FORM_PAGE = (
    "<html><head><title>Sign in</title><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script>"
    "</head><body><form><input name='email'><div class='cf-turnstile' data-sitekey='x'></div>"
    "<button>Sign in</button></form><p>Welcome back. Sign in to see your orders.</p></body></html>"
)


def test_turnstile_widget_on_normal_page_is_not_a_block():
    assert detect_defense(200, {"server": "cloudflare"}, TURNSTILE_FORM_PAGE) == DefenseSystem.NONE


def test_turnstile_on_block_status_is_still_detected():
    assert detect_defense(403, {}, TURNSTILE_FORM_PAGE) == DefenseSystem.CLOUDFLARE


def test_proxy_credentials_are_percent_decoded():
    cfg = playwright_proxy("http://us%3Aer:p%40ss%2Fword@10.0.0.1:3128")
    assert cfg == {"server": "http://10.0.0.1:3128", "username": "us:er", "password": "p@ss/word"}


@pytest.mark.parametrize("exc", [DNSResolutionError("no such host"), SSLHandshakeError("bad cert")])
async def test_dns_and_tls_failures_are_not_retried(exc):
    client = OmniClient(retries=3, retry_delay=0.001)
    fetcher = ScriptedFetcher([exc])
    install(client, t1=fetcher)
    with pytest.raises(type(exc)):
        await client.fetch("https://dead.example/", tier=1)
    assert len(fetcher.calls) == 1


async def test_circuit_breaker_trips_on_repeated_blocks():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
    client = OmniClient(retries=0, circuit_breaker=breaker)
    install(client, t1=ScriptedFetcher([(403, "<html>blocked</html>", {"cf-mitigated": "challenge"})]))
    for _ in range(2):
        res = await client.fetch("https://blocks.example/a", tier=1)
        assert res.status_code == 403
    with pytest.raises(CircuitBreakerOpenError):
        await client.fetch("https://blocks.example/b", tier=1)


@pytest.mark.parametrize("fetcher_cls, init", [(DynamicFetcher, "_init_browser"), (StealthFetcher, "_ensure_browser")])
async def test_concurrent_first_requests_launch_one_browser(fetcher_cls, init):
    fetcher = fetcher_cls()
    launches = 0

    async def fake_launch():
        nonlocal launches
        launches += 1
        await asyncio.sleep(0.02)  # launch latency opens the race window
        fetcher._browser = object()

    fetcher._launch = fake_launch
    await asyncio.gather(*(getattr(fetcher, init)() for _ in range(6)))
    assert launches == 1
