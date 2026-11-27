"""Browser-profile impersonation and rotation, HTTP/3 option, and multi-session spiders."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import omniscrape
from omniscrape.crawler import CrawlEngine, Request, Spider
from omniscrape.exceptions import ConfigError
from omniscrape.fetchers.http import FastFetcher, normalize_http_version

SEEN: list[dict] = []


class _Echo(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        SEEN.append({"path": self.path, **{k.lower(): v for k, v in self.headers.items()}})
        if self.path == "/robots.txt":
            body, ctype = b"User-agent: *\nAllow: /\n", "text/plain"
        elif self.path.startswith("/start"):
            body = b"<html><body><a href='/detail/1'>d1</a><a href='/detail/2'>d2</a></body></html>"
            ctype = "text/html"
        else:
            body = json.dumps({k.lower(): v for k, v in self.headers.items()}).encode()
            ctype = "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def echo():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def _ua(fetcher: FastFetcher, url: str, **kwargs) -> str:
    res = await fetcher.fetch(url, **kwargs)
    return json.loads(res.html)["user-agent"]


async def test_each_profile_sends_its_own_matching_user_agent(echo):
    for profile, marker, absent in (("safari", "Version/", "Chrome/"), ("firefox", "Firefox/", "Chrome/"),
                                    ("chrome", "Chrome/", "Firefox/")):
        fetcher = FastFetcher(impersonate=profile)
        try:
            ua = await _ua(fetcher, f"{echo}/ua")
        finally:
            await fetcher.close()
        assert marker in ua and absent not in ua, (profile, ua)


async def test_per_request_impersonate_override_and_extra_headers(echo):
    fetcher = FastFetcher()
    try:
        res = await fetcher.fetch(f"{echo}/h", impersonate="firefox", headers={"X-Test": "1"})
    finally:
        await fetcher.close()
    seen = json.loads(res.html)
    assert "Firefox/" in seen["user-agent"] and seen["x-test"] == "1"
    assert seen["accept-language"].startswith("en-US")


async def test_top_level_fetch_passes_impersonate_and_http_version(echo):
    res = await omniscrape.fetch(f"{echo}/top", tier=1, impersonate="safari", http_version="1.1")
    assert "Version/" in json.loads(res.html)["user-agent"]


def test_domain_rotation_is_sticky_per_host_and_uses_every_profile():
    fetcher = FastFetcher(impersonate=["chrome", "safari", "firefox"])
    for host in ("a.test", "b.test", "shop.example"):
        first = fetcher.profile_for(f"https://{host}/1")
        assert all(fetcher.profile_for(f"https://{host}/{i}") == first for i in range(10))
    used = {fetcher.profile_for(f"https://site{i}.test/") for i in range(60)}
    assert used == {"chrome", "safari", "firefox"}


def test_request_rotation_cycles():
    fetcher = FastFetcher(impersonate=["chrome", "firefox"], rotate="request")
    assert [fetcher.profile_for("https://a.test/") for _ in range(4)] == ["chrome", "firefox", "chrome", "firefox"]


def test_fetcher_rejects_bad_options():
    with pytest.raises(ValueError):
        FastFetcher(impersonate=[])
    with pytest.raises(ValueError):
        FastFetcher(rotate="random")
    with pytest.raises(ValueError):
        normalize_http_version("4")


def test_http_version_spellings():
    assert [normalize_http_version(v) for v in (None, 3, "h3", "http3", "2", "1.1", "3only")] == \
        [None, "v3", "v3", "v3", "v2", "v1", "v3only"]


class _TwoSessionSpider(Spider):
    name = "two-sessions"
    sessions = {
        "listing": {"tier": 1, "impersonate": "firefox"},
        "detail": {"tier": 1, "impersonate": "safari", "headers": {"X-Session": "detail"}},
    }
    default_session = "listing"

    def __init__(self, base: str):
        self.start_urls = [f"{base}/start"]

    async def parse(self, response, selector):
        for href in selector.css("a::attr(href)").getall():
            yield Request(href, session="detail", callback=self.parse_detail)

    async def parse_detail(self, response, selector):
        yield {"url": response.url, **json.loads(response.html)}


async def test_multi_session_spider_mixes_fetch_configurations(echo):
    SEEN.clear()
    items = [item async for item in CrawlEngine(_TwoSessionSpider(echo), obey_robots=False).stream()]
    start = next(s for s in SEEN if s["path"] == "/start")
    assert "Firefox/" in start["user-agent"]
    assert len(items) == 2
    for item in items:
        assert "Version/" in item["user-agent"] and "Chrome/" not in item["user-agent"]
        assert item["x-session"] == "detail"


async def test_unknown_session_fails_fast():
    class Broken(Spider):
        name = "broken"
        start_urls = ["https://a.test/"]
        default_session = "nope"

    with pytest.raises(ConfigError, match="nope"):
        await CrawlEngine(Broken(), obey_robots=False).run()


def test_request_queue_persists_session(tmp_path):
    from omniscrape.crawler.queue import RequestQueue

    q = RequestQueue(str(tmp_path / "q.db"))
    q.add(Request("https://a.test/x", session="detail"))
    q.close()
    resumed = RequestQueue(str(tmp_path / "q.db"))
    _, req = resumed.pop()
    resumed.close()
    assert req.session == "detail"
