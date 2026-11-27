"""CLI tests: every command runs against a tiny in-process HTTP site (no internet)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from omniscrape.cli.main import cli

PAGES = {
    "/": "<html><head><title>Home</title></head><body><main><h1>Home</h1><p>Welcome to the demo shop, "
         "a place with enough text to count as content for the extractor.</p>"
         "<a href='/a'>A</a> <a href='/b'>B</a> <a href='/private/x'>secret</a></main></body></html>",
    "/a": "<html><head><title>Page A</title></head><body><main><h1>Page A</h1><p class='price'>$19.99</p>"
          "<p>Some paragraph text about page A that is long enough to be treated as main content.</p>"
          "<a href='/'>home</a></main></body></html>",
    "/b": "<html><head><title>Page B</title></head><body><main><h1>Page B</h1>"
          "<p>Different text on page B, again long enough to be treated as main content.</p></main></body></html>",
    "/private/x": "<html><head><title>Secret</title></head><body><p>should not be crawled</p></body></html>",
}
ROBOTS = "User-agent: *\nDisallow: /private/\n"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            body, ctype = ROBOTS, "text/plain"
        elif path in PAGES:
            body, ctype = PAGES[path], "text/html; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def runner():
    return CliRunner()


def test_version(runner):
    res = runner.invoke(cli, ["--version"])
    assert res.exit_code == 0 and "omniscrape, version" in res.output


def test_help_lists_all_commands(runner):
    out = runner.invoke(cli, ["--help"]).output
    for command in ("get", "crawl", "map", "extract", "shell", "mcp"):
        assert command in out


def test_get_json_is_valid_json_on_stdout(runner, site):
    res = runner.invoke(cli, ["get", f"{site}/a", "-f", "json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)  # stdout carries only the JSON document
    assert data["title"] == "Page A" and data["status_code"] == 200


def test_get_markdown_to_file(runner, site, tmp_path):
    out = tmp_path / "page.md"
    res = runner.invoke(cli, ["get", f"{site}/a", "-f", "markdown", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert "Page A" in out.read_text(encoding="utf-8")


def test_get_css_prints_matching_text(runner, site):
    res = runner.invoke(cli, ["get", f"{site}/a", "--css", "p.price"])
    assert res.exit_code == 0, res.output
    assert res.stdout.strip() == "$19.99"


def test_get_css_no_match_fails(runner, site):
    res = runner.invoke(cli, ["get", f"{site}/a", "--css", ".does-not-exist"])
    assert res.exit_code == 1


def test_get_bad_header_is_a_usage_error(runner, site):
    res = runner.invoke(cli, ["get", f"{site}/a", "-H", "no-colon-here"])
    assert res.exit_code == 2


def test_get_unreachable_host_exits_cleanly(runner):
    res = runner.invoke(cli, ["get", "http://127.0.0.1:9/", "--timeout", "2"])
    assert res.exit_code == 1 and "error" in res.output.lower()


def test_map_lists_links(runner, site):
    res = runner.invoke(cli, ["map", site, "-f", "json"])
    assert res.exit_code == 0, res.output
    urls = json.loads(res.stdout)
    assert f"{site}/a" in urls and f"{site}/b" in urls
    assert not any("/private/" in u for u in urls)  # robots.txt respected


def test_extract_with_schema(runner, site, tmp_path):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"heading": "h1::text", "price": {"selector": "p.price::text", "type": "price"}}))
    res = runner.invoke(cli, ["extract", f"{site}/a", "--schema", str(schema)])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data == {"heading": "Page A", "price": 19.99}


def test_extract_rejects_bad_schema_file(runner, site, tmp_path):
    schema = tmp_path / "bad.json"
    schema.write_text("{not json")
    res = runner.invoke(cli, ["extract", f"{site}/a", "--schema", str(schema)])
    assert res.exit_code == 1


def test_crawl_writes_jsonl_and_obeys_robots(runner, site, tmp_path):
    out = tmp_path / "items.jsonl"
    res = runner.invoke(cli, ["crawl", site, "--max-pages", "10", "-c", "2", "-o", str(out)])
    assert res.exit_code == 0, res.output
    items = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    urls = {i["url"] for i in items}
    assert urls == {f"{site}/", f"{site}/a", f"{site}/b"}  # /private/ is disallowed by robots.txt
    assert all(i["content_type"] in ("product", "article", "listing", "other") for i in items)


def test_crawl_duckdb_output(runner, site, tmp_path):
    duckdb = pytest.importorskip("duckdb")
    out = tmp_path / "items.duckdb"
    res = runner.invoke(cli, ["crawl", site, "--max-pages", "5", "-o", str(out)])
    assert res.exit_code == 0, res.output
    con = duckdb.connect(str(out))
    assert con.execute("SELECT count(*) FROM scraped_data").fetchone()[0] == 3
    con.close()


def test_crawl_rejects_unknown_output_extension(runner, site, tmp_path):
    res = runner.invoke(cli, ["crawl", site, "-o", str(tmp_path / "items.csv")])
    assert res.exit_code == 1


def test_shell_plain_repl_has_names_preloaded(runner, site, monkeypatch):
    import code

    seen = {}

    def fake_interact(banner="", local=None, **kw):
        seen["local"], seen["banner"] = local, banner

    monkeypatch.setattr(code, "interact", fake_interact)
    res = runner.invoke(cli, ["shell", site + "/a", "--plain"])
    assert res.exit_code == 0, res.output
    assert {"Selector", "fetch_sync", "scrape_sync", "page", "response"} <= set(seen["local"])
    assert seen["local"]["page"].css("h1::text").get() == "Page A"


async def test_request_meta_reaches_callback_and_selector_has_url(site):
    """Crawler fixes: ``Request.meta`` is delivered as ``response.meta``; ``Selector`` gets the page URL."""
    from omniscrape.crawler import CrawlEngine, Request, Spider

    seen = []

    class MetaSpider(Spider):
        name = "meta-test"

        async def start_requests(self):
            yield Request(f"{site}/a", meta={"tag": "from-start"})

        async def parse(self, response, selector):
            seen.append((response.meta, selector.url, selector.css("a::attr(href)").get()))
            yield {"ok": True}

    await CrawlEngine(MetaSpider(), max_pages=1, obey_robots=False).run()
    assert seen == [({"tag": "from-start"}, f"{site}/a", "/")]


async def test_httpx_fetcher_fetches_local_page(site):
    pytest.importorskip("httpx")
    from omniscrape.fetchers.httpx_fetcher import HttpxFetcher

    fetcher = HttpxFetcher(http2=False)
    try:
        res = await fetcher.fetch(f"{site}/a")
        missing = await fetcher.fetch(f"{site}/nope")
    finally:
        await fetcher.close()
    assert res.status_code == 200 and "Page A" in res.html
    assert missing.status_code == 404


def test_get_css_text_pseudo_element(runner, site):
    res = runner.invoke(cli, ["get", f"{site}/a", "--css", "h1::text"])
    assert res.exit_code == 0, res.output
    assert res.stdout.strip() == "Page A"
    res = runner.invoke(cli, ["get", f"{site}/", "--css", "main a::attr(href)"])
    assert res.exit_code == 0, res.output
    assert res.stdout.split() == ["/a", "/b", "/private/x"]


def test_crawl_rejects_json_extension_with_hint(runner, site, tmp_path):
    res = runner.invoke(cli, ["crawl", site, "-o", str(tmp_path / "items.json")])
    assert res.exit_code == 1 and ".jsonl" in res.output


def test_crawl_replaces_output_unless_append(runner, site, tmp_path):
    out = tmp_path / "items.jsonl"
    for _ in range(2):
        assert runner.invoke(cli, ["crawl", site, "--max-pages", "10", "-o", str(out)]).exit_code == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3  # replaced, not duplicated
    assert runner.invoke(cli, ["crawl", site, "--max-pages", "10", "-o", str(out), "--append"]).exit_code == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 6
