"""Phase 0 regression tests: registry, defense detection, escalation policy, retries, resilience."""

import tempfile
from typing import Any, Optional

import pytest

from omniscrape.classifier.detector import classify_result, detect_defense, looks_like_spa
from omniscrape.classifier.strategies import EscalationStrategy
from omniscrape.client import OmniClient
from omniscrape.exceptions import CircuitBreakerOpenError, ConfigError, ConnectionTimeoutError
from omniscrape.fetchers.base import BaseFetcher, playwright_proxy
from omniscrape.fetchers.pool import ProxyPoolManager
from omniscrape.fetchers.registry import create_fetcher, get_spec, register_fetcher
from omniscrape.models import DefenseSystem, FetchResult, PageType
from omniscrape.resilience.circuit_breaker import CircuitBreaker
from omniscrape.resilience.dead_letter import DeadLetterQueue

CONTENT_HTML = "<html><head><title>Shop</title></head><body>" + "<p>Real content paragraph.</p>" * 40 + "</body></html>"
SPA_HTML = '<html><head><script src="/app.js"></script></head><body><div id="root"></div>' + " " * 600 + "</body></html>"
CF_CHALLENGE = "<html><head><title>Just a moment...</title></head><body><script src='/cdn-cgi/challenge-platform/x.js'></script></body></html>"


class ScriptedFetcher(BaseFetcher):
    """Fake fetcher that replays a script of results/exceptions and records calls."""

    tier = 1

    def __init__(self, script: Optional[list[Any]] = None, tier: int = 1):
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []
        self.tier = tier
        self.closed = False

    async def fetch(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        status, html, headers = item
        return FetchResult(url=url, status_code=status, html=html, headers=headers or {},
                           fetcher_tier=self.tier,
                           defense_detected=detect_defense(status, headers or {}, html))

    async def close(self):
        self.closed = True


def install(client: OmniClient, **by_tier: ScriptedFetcher) -> None:
    names = {"t1": "http", "t2": "browser", "t3": "stealth"}
    for key, fetcher in by_tier.items():
        client._fetchers[names[key]] = fetcher


# ----------------------------------------------------------------------------- detection
def test_cloudflare_header_on_normal_page_is_not_a_block():
    headers = {"cf-ray": "8a1b2c3d4e-BOM", "server": "cloudflare"}
    assert detect_defense(200, headers, CONTENT_HTML) == DefenseSystem.NONE
    assert classify_result(FetchResult(url="u", status_code=200, html=CONTENT_HTML, headers=headers)).page_type == PageType.STATIC


def test_cloudflare_challenge_and_waf_block_detected():
    assert detect_defense(403, {"server": "cloudflare"}, "<html>Sorry, you have been blocked</html>") == DefenseSystem.CLOUDFLARE
    assert detect_defense(200, {}, CF_CHALLENGE) == DefenseSystem.CLOUDFLARE
    assert detect_defense(403, {"x-datadome": "protected"}, "") == DefenseSystem.DATADOME
    assert detect_defense(403, {"server": "AkamaiGHost"}, "Access Denied") == DefenseSystem.AKAMAI


def test_spa_shell_detection():
    assert looks_like_spa(SPA_HTML)
    assert not looks_like_spa(CONTENT_HTML)


# ----------------------------------------------------------------------------- registry
def test_registry_resolves_tiers_names_and_aliases():
    assert get_spec(1).name == "http"
    assert get_spec("FastFetcher").name == "http"
    assert get_spec("playwright").tier == 2
    assert get_spec("3").name == "stealth"
    with pytest.raises(ConfigError):
        get_spec("does-not-exist")


def test_register_custom_fetcher():
    register_fetcher("scripted-test", ScriptedFetcher, aliases=["scr"], override=True)
    fetcher = create_fetcher("scr", script=[(200, CONTENT_HTML, {})])
    assert isinstance(fetcher, ScriptedFetcher)
    with pytest.raises(ConfigError):
        register_fetcher("scripted-test", ScriptedFetcher)


def test_playwright_proxy_splits_credentials():
    assert playwright_proxy("http://user:pw@1.2.3.4:8080") == {"server": "http://1.2.3.4:8080", "username": "user", "password": "pw"}
    assert playwright_proxy(None) is None


# ----------------------------------------------------------------------------- escalation policy
async def test_auto_mode_static_page_uses_exactly_one_request():
    client = OmniClient(retries=0)
    t1 = ScriptedFetcher([(200, CONTENT_HTML, {"cf-ray": "abc"})])
    t2 = ScriptedFetcher([(200, CONTENT_HTML, {})], tier=2)
    install(client, t1=t1, t2=t2)
    res = await client.fetch("https://shop.example/p/1")
    assert res.fetcher_tier == 1
    assert len(t1.calls) == 1 and len(t2.calls) == 0


async def test_spa_shell_escalates_to_browser():
    client = OmniClient(retries=0)
    t1 = ScriptedFetcher([(200, SPA_HTML, {})])
    t2 = ScriptedFetcher([(200, CONTENT_HTML, {})], tier=2)
    install(client, t1=t1, t2=t2)
    res = await client.fetch("https://spa.example/")
    assert res.fetcher_tier == 2 and len(t2.calls) == 1


async def test_block_is_not_escalated_to_stealth_by_default():
    client = OmniClient(retries=0)
    t1 = ScriptedFetcher([(403, "<html>blocked</html>", {"server": "cloudflare"})])
    t3 = ScriptedFetcher([(200, CONTENT_HTML, {})], tier=3)
    install(client, t1=t1, t3=t3)
    res = await client.fetch("https://blocked.example/")
    assert res.status_code == 403 and res.defense_detected == DefenseSystem.CLOUDFLARE
    assert len(t3.calls) == 0


async def test_block_escalates_only_with_allow_stealth():
    client = OmniClient(retries=0, allow_stealth=True)
    t1 = ScriptedFetcher([(403, "<html>blocked</html>", {"server": "cloudflare"})])
    t3 = ScriptedFetcher([(200, CONTENT_HTML, {})], tier=3)
    install(client, t1=t1, t3=t3)
    res = await client.fetch("https://blocked.example/")
    assert res.fetcher_tier == 3 and len(t3.calls) == 1


def test_should_escalate_backward_compatible_names():
    blocked = FetchResult(url="u", status_code=403, html="", fetcher_tier=1)
    assert EscalationStrategy.should_escalate(blocked) is None
    assert EscalationStrategy.should_escalate(blocked, allow_stealth=True) == "StealthFetcher"
    spa = FetchResult(url="u", status_code=200, html=SPA_HTML, fetcher_tier=1)
    assert EscalationStrategy.should_escalate(spa) == "DynamicFetcher"


# ----------------------------------------------------------------------------- retries & resilience
async def test_retries_5xx_then_succeeds():
    client = OmniClient(retries=2, retry_delay=0.001)
    t1 = ScriptedFetcher([(503, "busy", {}), (502, "bad gw", {}), (200, CONTENT_HTML, {})])
    install(client, t1=t1)
    res = await client.fetch("https://flaky.example/", tier=1)
    assert res.status_code == 200 and len(t1.calls) == 3


async def test_exhausted_status_retries_return_last_response():
    client = OmniClient(retries=1, retry_delay=0.001)
    t1 = ScriptedFetcher([(500, "err", {})])
    install(client, t1=t1)
    res = await client.fetch("https://down.example/", tier=1)
    assert res.status_code == 500 and len(t1.calls) == 2


async def test_network_error_goes_to_dead_letter_queue():
    with tempfile.TemporaryDirectory() as tmp:
        dlq = DeadLetterQueue(db_path=f"{tmp}/dlq.db")
        client = OmniClient(retries=1, retry_delay=0.001, dead_letter=dlq)
        t1 = ScriptedFetcher([ConnectionTimeoutError("timed out")])
        install(client, t1=t1)
        with pytest.raises(ConnectionTimeoutError):
            await client.fetch("https://slow.example/", tier=1)
        assert len(t1.calls) == 2
        rows = [(r["url"], r["error_type"]) for r in dlq.list()]
        assert rows == [("https://slow.example/", "ConnectionTimeoutError")]


async def test_circuit_breaker_opens_after_failures():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
    client = OmniClient(retries=0, circuit_breaker=breaker)
    install(client, t1=ScriptedFetcher([ConnectionTimeoutError("timed out")]))
    for _ in range(2):
        with pytest.raises(ConnectionTimeoutError):
            await client.fetch("https://dead.example/a", tier=1)
    with pytest.raises(CircuitBreakerOpenError):
        await client.fetch("https://dead.example/b", tier=1)


async def test_proxy_pool_is_used_and_unhealthy_proxies_skipped():
    pool = ProxyPoolManager(["http://p1:1", "http://p2:2"], min_samples=2)
    for _ in range(3):
        pool.record_result("http://p1:1", False)
    client = OmniClient(retries=0, proxy_pool=pool)
    t1 = ScriptedFetcher([(200, CONTENT_HTML, {})])
    install(client, t1=t1)
    for _ in range(3):
        await client.fetch("https://shop.example/", tier=1)
    assert {c["proxy"] for c in t1.calls} == {"http://p2:2"}
    assert pool.stats()["http://p2:2"]["success"] == 3


async def test_client_reuses_and_closes_fetchers():
    client = OmniClient()
    f1 = await client.get_fetcher(1)
    assert f1 is await client.get_fetcher("http")
    t1 = ScriptedFetcher([(200, CONTENT_HTML, {})])
    install(client, t1=t1)
    await client.close()
    assert t1.closed
