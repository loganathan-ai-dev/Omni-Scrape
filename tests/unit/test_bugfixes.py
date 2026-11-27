"""Regression tests for the bugs fixed before the 0.1.0 release."""

import asyncio
import logging

import pytest

from omniscrape.crawler.robots import WildcardMatcher
from omniscrape.observability.logging import get_logger
from omniscrape.parsers.selector import Selector
from omniscrape.parsers.tables import TableParser
from omniscrape.storage import DuckDBStorage, JSONLStorage

ROBOTS = """
User-agent: *
Disallow: /*?sessionid=
Disallow: /private/
Allow: /private/public.html
Disallow: /*.pdf$

User-agent: omniscrape
Disallow: /only-bot/
""".splitlines()


# ------------------------------------------------------------------ robots.txt wildcards
def test_robots_star_wildcard_blocks_query_pattern():
    m = WildcardMatcher(ROBOTS)
    assert not m.can_fetch("other", "https://a.test/page?sessionid=1")
    assert m.can_fetch("other", "https://a.test/page?q=1")


def test_robots_dollar_anchor_and_longest_match():
    m = WildcardMatcher(ROBOTS)
    assert not m.can_fetch("other", "https://a.test/doc.pdf")
    assert m.can_fetch("other", "https://a.test/doc.pdf?download=1")  # `$` anchors the end
    assert not m.can_fetch("other", "https://a.test/private/x")
    assert m.can_fetch("other", "https://a.test/private/public.html")  # longer Allow wins


def test_robots_specific_agent_group_beats_star_group():
    m = WildcardMatcher(ROBOTS)
    assert not m.can_fetch("omniscrape", "https://a.test/only-bot/x")
    assert m.can_fetch("omniscrape", "https://a.test/private/x")  # `*` rules do not apply to it


def test_robots_empty_disallow_allows_everything():
    assert WildcardMatcher(["User-agent: *", "Disallow:"]).can_fetch("x", "https://a.test/anything")


# ------------------------------------------------------------------ tables
def test_table_parser_does_not_return_header_as_data():
    html = ("<table><thead><tr><th>A</th><th>B</th></tr></thead>"
            "<tbody><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table>")
    table = Selector(html).css("table")[0]
    assert TableParser.parse_table(table) == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]


def test_table_parser_header_row_without_thead():
    html = "<table><tr><th>X</th><th>Y</th></tr><tr><td>1</td><td>2</td></tr></table>"
    assert TableParser.parse_table(Selector(html).css("table")[0]) == [{"X": "1", "Y": "2"}]


def test_table_parser_headerless_table_uses_first_row():
    html = "<table><tr><td>k</td><td>v</td></tr><tr><td>a</td><td>b</td></tr></table>"
    assert TableParser.parse_table(Selector(html).css("table")[0]) == [{"k": "a", "v": "b"}]


# ------------------------------------------------------------------ find_by_text / find_by_regex
def test_find_by_text_returns_innermost_elements_only():
    s = Selector("<html><body><div><p>Hello <b>world</b></p><p>Hello again</p></div></body></html>")
    assert [e.tag for e in s.find_by_text("world")] == ["b"]
    assert [e.tag for e in s.find_by_text("hello")] == ["p", "p"]  # not html/body/div


def test_find_by_regex_returns_innermost_elements_only():
    s = Selector("<html><body><div><span>Price: $10</span></div></body></html>")
    assert [e.tag for e in s.find_by_regex(r"\$\d+")] == ["span"]


# ------------------------------------------------------------------ selectolax root access
def test_selectolax_backend_root_level_element_api():
    pytest.importorskip("selectolax")
    s = Selector("<html><body><p>hi</p></body></html>", backend="selectolax")
    assert "hi" in s.text  # inherited Element API must work before .root was touched
    assert s.css("p").getall()


# ------------------------------------------------------------------ logging
def test_logger_writes_to_stderr_not_stdout(capsys):
    name = "omniscrape.test.stderr"
    logging.getLogger(name).handlers.clear()
    get_logger(name).warning("hello")
    out, err = capsys.readouterr()
    assert out == ""
    assert "hello" in err


# ------------------------------------------------------------------ storage
async def test_jsonl_is_durable_and_reusable_after_close(tmp_path):
    path = tmp_path / "out.jsonl"
    storage = JSONLStorage(str(path))
    await storage.write({"a": 1})
    assert path.read_text(encoding="utf-8").strip() == '{"a": 1}'  # visible before close/flush
    await storage.close()
    await storage.write({"b": 2})  # reusable after close
    await storage.close()
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


async def test_duckdb_accepts_records_with_new_keys(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    storage = DuckDBStorage(str(tmp_path / "x.duckdb"))
    await storage.write({"a": 1})
    await storage.write({"a": 2, "b": [1, 2]})
    await storage.write({"c": 5.5})
    rows = storage._get_con().execute("SELECT a, b, c FROM scraped_data ORDER BY a NULLS LAST").fetchall()
    assert rows == [("1", None, None), ("2", "[1, 2]", None), (None, None, "5.5")]
    await storage.close()
    assert duckdb is not None


# ------------------------------------------------------------------ fetch_many
async def test_fetch_many_cancels_siblings_when_one_fails():
    from omniscrape import OmniClient
    from omniscrape.models import FetchResult

    cancelled = []

    class FakeClient(OmniClient):
        async def fetch(self, url, tier=None, **kwargs):
            if url.endswith("/bad"):
                raise RuntimeError("boom")
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.append(url)
                raise
            return FetchResult(url=url, status_code=200, html="")

    client = FakeClient()
    with pytest.raises(RuntimeError):
        await client.fetch_many(["https://x.test/slow1", "https://x.test/bad", "https://x.test/slow2"])
    assert sorted(cancelled) == ["https://x.test/slow1", "https://x.test/slow2"]


async def test_fetch_many_return_exceptions_collects_errors():
    from omniscrape import OmniClient
    from omniscrape.models import FetchResult

    class FakeClient(OmniClient):
        async def fetch(self, url, tier=None, **kwargs):
            if url.endswith("/bad"):
                raise RuntimeError("boom")
            return FetchResult(url=url, status_code=200, html="ok")

    res = await FakeClient().fetch_many(["https://x.test/a", "https://x.test/bad"], return_exceptions=True)
    assert isinstance(res[1], RuntimeError) and res[0].html == "ok"


# ------------------------------------------------------------------ proxy pool strategies
def test_proxy_pool_sticky_keeps_one_proxy_per_domain():
    from omniscrape import ProxyPoolManager

    pool = ProxyPoolManager(["http://p1:1", "http://p2:2", "http://p3:3"], strategy="sticky")
    first = pool.get_proxy("a.test")
    assert all(pool.get_proxy("a.test") == first for _ in range(20))


def test_proxy_pool_sticky_moves_domain_off_an_unhealthy_proxy():
    from omniscrape import ProxyPoolManager

    pool = ProxyPoolManager(["http://p1:1", "http://p2:2"], strategy="sticky", min_samples=2)
    first = pool.get_proxy("a.test")
    for _ in range(4):
        pool.record_result(first, success=False)
    assert pool.get_proxy("a.test") != first


def test_proxy_pool_random_only_returns_known_healthy_proxies():
    from omniscrape import ProxyPoolManager

    proxies = ["http://p1:1", "http://p2:2", "http://p3:3"]
    pool = ProxyPoolManager(proxies, strategy="random", min_samples=1)
    for _ in range(3):
        pool.record_result(proxies[0], success=False)
    assert {pool.get_proxy() for _ in range(50)} <= set(proxies[1:])


def test_proxy_pool_empty_returns_none():
    from omniscrape import ProxyPoolManager

    assert ProxyPoolManager().get_proxy("a.test") is None


# ------------------------------------------------------------------ review round 2
def test_robots_percent_encoded_rules_match_decoded_and_encoded_urls():
    m = WildcardMatcher(["User-agent: *", "Disallow: /caf%C3%A9/", "Disallow: /search%3Fq"])
    assert not m.can_fetch("x", "https://a.test/caf%C3%A9/menu")
    assert not m.can_fetch("x", "https://a.test/café/menu")
    assert not m.can_fetch("x", "https://a.test/search%3Fq=1")
    assert m.can_fetch("x", "https://a.test/cafe/menu")


def test_robots_groups_for_the_same_agent_are_merged():
    m = WildcardMatcher(["User-agent: *", "Disallow: /a", "", "User-agent: *", "Disallow: /private"])
    assert not m.can_fetch("x", "https://a.test/a/1")
    assert not m.can_fetch("x", "https://a.test/private/x")


def test_robots_crawl_delay_comes_from_the_same_group_as_the_rules():
    m = WildcardMatcher([
        "User-agent: omni", "Crawl-delay: 1", "",
        "User-agent: omniscrape", "Crawl-delay: 10", "Disallow: /x", "",
        "User-agent: *", "Request-rate: 1/5",
    ])
    assert m.crawl_delay("omniscrape") == 10.0
    assert m.crawl_delay("someone-else") == 5.0


async def test_duckdb_keys_differing_only_in_case_share_a_column(tmp_path):
    pytest.importorskip("duckdb")
    storage = DuckDBStorage(str(tmp_path / "c.duckdb"))
    await storage.write({"Title": "a"})
    await storage.write({"title": "b", "x": 1})
    await storage.write_batch([{"X": 2, "TITLE": "c"}])
    rows = storage._get_con().execute('SELECT "Title", x FROM scraped_data').fetchall()
    assert rows == [("a", None), ("b", "1"), ("c", "2")]
    await storage.close()


async def test_iter_scrape_cancels_remaining_downloads_when_caller_stops_early():
    from omniscrape import OmniClient
    from omniscrape.models import FetchResult

    cancelled = []

    class FakeClient(OmniClient):
        async def fetch(self, url, tier=None, **kwargs):
            if not url.endswith("/fast"):
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    cancelled.append(url)
                    raise
            return FetchResult(url=url, status_code=200, html="<title>t</title>")

    gen = FakeClient().iter_scrape(["https://x.test/fast", "https://x.test/slow1", "https://x.test/slow2"])
    async for url, _ in gen:
        assert url.endswith("/fast")
        break
    await gen.aclose()
    assert sorted(cancelled) == ["https://x.test/slow1", "https://x.test/slow2"]


def test_request_queue_persists_tier_across_resume(tmp_path):
    from omniscrape.crawler.queue import RequestQueue
    from omniscrape.crawler.spider import Request

    path = str(tmp_path / "q.db")
    q = RequestQueue(path)
    q.add(Request("https://a.test/js", tier=2))
    q.add(Request("https://a.test/api", tier="httpx"))
    q.add(Request("https://a.test/plain"))
    q.close()
    resumed = RequestQueue(path)
    tiers = {}
    while (item := resumed.pop()) is not None:
        tiers[item[1].url] = item[1].tier
    resumed.close()
    assert tiers == {"https://a.test/js": 2, "https://a.test/api": "httpx", "https://a.test/plain": None}


async def test_mcp_get_markdown_rejects_200_challenge_pages(monkeypatch):
    pytest.importorskip("fastmcp")
    from fastmcp.client import Client

    import omniscrape
    from omniscrape.mcp.server import build_server
    from omniscrape.models import DefenseSystem, FetchResult

    async def fake_fetch(url, **kwargs):
        return FetchResult(url=url, status_code=200, html="<html><body>Just a moment...</body></html>",
                           defense_detected=DefenseSystem.CLOUDFLARE)

    monkeypatch.setattr(omniscrape, "fetch", fake_fetch)
    async with Client(build_server()) as client:
        text = (await client.call_tool("get_markdown", {"url": "https://a.test/"})).content[0].text
    assert text.startswith("Error:") and "cloudflare" in text
