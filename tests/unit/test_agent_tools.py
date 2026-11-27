"""curl import, CLI output formats and the `curl` command, and the extended MCP toolset."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from omniscrape import parse_curl
from omniscrape.cli.main import cli
from omniscrape.exceptions import ConfigError

RECIPE = {"@context": "https://schema.org", "@type": "Recipe", "name": "Lemon Rice",
          "recipeIngredient": ["1 cup rice", "1 lemon"], "totalTime": "PT25M"}
CARDS = "".join(f'<div class="card"><a href="/item/{i}"><img src="/i{i}.jpg"><h3>Item {i}</h3></a>'
                f'<span class="price">${i + 10}.00</span></div>' for i in range(10))
PAGES = {
    "/": "<html><head><title>Home</title></head><body><main><h1>Home</h1>"
         "<a href='/recipe'>Recipe</a><a href='/shop'>Shop</a><a href='https://other.test/x'>Out</a></main></body></html>",
    "/recipe": "<html><head><title>Lemon Rice</title><script type='application/ld+json'>"
               + json.dumps(RECIPE) + "</script></head><body><h1>Lemon Rice</h1><p>Tangy.</p></body></html>",
    "/shop": f"<html><head><title>Shop</title></head><body><div class='grid'>{CARDS}</div></body></html>",
}


class _Site(BaseHTTPRequestHandler):
    def _reply(self):
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            body, ctype, status = "User-agent: *\nAllow: /\n", "text/plain", 200
        elif path == "/echo":
            length = int(self.headers.get("Content-Length") or 0)
            payload = {"method": self.command, "query": self.path.partition("?")[2],
                       "headers": {k.lower(): v for k, v in self.headers.items()},
                       "body": self.rfile.read(length).decode() if length else ""}
            body, ctype, status = json.dumps(payload), "application/json", 200
        elif path == "/blocked":
            body, ctype, status = "<html><body>Access denied</body></html>", "text/html", 403
        elif path in PAGES:
            body, ctype, status = PAGES[path], "text/html; charset=utf-8", 200
        else:
            body, ctype, status = "not found", "text/plain", 404
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _reply  # noqa: N815
    do_POST = _reply  # noqa: N815

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Site)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


# ------------------------------------------------------------------ curl parsing
def test_parse_curl_browser_copy_bash_style():
    req = parse_curl("""curl 'https://api.test/items?page=2' \\
      -H 'accept: application/json' \\
      -H 'user-agent: Mozilla/5.0 Test' \\
      -b 'sid=abc; theme=dark' \\
      --compressed""")
    assert req["url"] == "https://api.test/items?page=2" and req["method"] == "GET"
    assert req["headers"] == {"accept": "application/json", "user-agent": "Mozilla/5.0 Test"}
    assert req["cookies"] == {"sid": "abc", "theme": "dark"} and req["data"] is None


def test_parse_curl_windows_cmd_style():
    req = parse_curl('curl ^"https://api.test/search^" ^\n  -H ^"Accept: text/html^" ^\n  --data-raw ^"q=lamp^&n=2^"')
    assert req["url"] == "https://api.test/search" and req["method"] == "POST"
    assert req["data"] == "q=lamp&n=2" and req["headers"]["Accept"] == "text/html"
    assert req["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_parse_curl_json_get_auth_and_flags():
    req = parse_curl("curl -sSL -XPUT --json '{\"a\":1}' -u user:pw --http3 -m 7 -x http://p:8080 https://a.test/x")
    assert req["method"] == "PUT" and req["data"] == '{"a":1}'
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["headers"]["Authorization"] == "Basic dXNlcjpwdw=="
    assert (req["http_version"], req["timeout"], req["proxy"]) == ("3", 7.0, "http://p:8080")
    got = parse_curl("curl -G https://a.test/s -d q=1 --data-urlencode 'name=a b'")
    assert got["url"] == "https://a.test/s?q=1&name=a%20b" and got["method"] == "GET" and got["data"] is None
    assert parse_curl("curl -I https://a.test/")["method"] == "HEAD"
    assert parse_curl("curl -k https://a.test/")["insecure"] is True


@pytest.mark.parametrize("bad", ["wget https://a.test/", "curl -H 'X: 1'", "curl -d @body.json https://a.test/",
                                 "curl -F file=@a.png https://a.test/", "curl 'unterminated"])
def test_parse_curl_rejects_unsupported(bad):
    with pytest.raises(ConfigError):
        parse_curl(bad)


async def test_fetch_curl_replays_method_headers_cookies_and_body(site):
    from omniscrape import fetch_curl

    res = await fetch_curl(f"curl '{site}/echo?x=1' -H 'X-Token: t1' -b 'sid=abc' --data-raw 'a=1&b=2'")
    echo = json.loads(res.html)
    assert echo["method"] == "POST" and echo["query"] == "x=1" and echo["body"] == "a=1&b=2"
    assert echo["headers"]["x-token"] == "t1" and "sid=abc" in echo["headers"]["cookie"]


# ------------------------------------------------------------------ CLI
def test_cli_curl_command_outputs_json(site):
    res = CliRunner().invoke(cli, ["curl", f"curl '{site}/recipe'", "-f", "json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["content_type"] == "recipe" and data["entities"]["recipe"]["title"] == "Lemon Rice"


@pytest.mark.parametrize("name,check", [
    ("page.md", lambda text: text.startswith("# Lemon Rice")),
    ("page.html", lambda text: "application/ld+json" in text),
    ("page.txt", lambda text: "Tangy." in text and "<" not in text),
    ("page.json", lambda text: json.loads(text)["content_type"] == "recipe"),
])
def test_cli_get_infers_format_from_output_extension(site, tmp_path, name, check):
    out = tmp_path / name
    res = CliRunner().invoke(cli, ["get", f"{site}/recipe", "-o", str(out)])
    assert res.exit_code == 0, res.output
    assert check(out.read_text(encoding="utf-8"))


def test_cli_get_unknown_extension_needs_format(site, tmp_path):
    res = CliRunner().invoke(cli, ["get", f"{site}/recipe", "-o", str(tmp_path / "page.dat")])
    assert res.exit_code == 1 and "-f" in res.output


def test_cli_get_impersonate_option(site):
    res = CliRunner().invoke(cli, ["get", f"{site}/echo", "-f", "html", "--impersonate", "firefox", "-t", "1"])
    assert res.exit_code == 0, res.output
    assert "Firefox/" in json.loads(res.stdout)["headers"]["user-agent"]


def test_cli_summary_shows_page_type_and_entities(site):
    res = CliRunner().invoke(cli, ["get", f"{site}/recipe"])
    assert res.exit_code == 0, res.output
    assert "recipe" in res.output and "Lemon Rice (2 ingredients)" in res.output


# ------------------------------------------------------------------ MCP
async def test_mcp_lists_all_tools():
    pytest.importorskip("fastmcp")
    from fastmcp.client import Client

    from omniscrape.mcp.server import build_server

    async with Client(build_server()) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"scrape_url", "scrape_product", "scrape_article", "get_markdown", "map_site", "extract_entities",
                     "extract_schema", "extract_listings", "get_links", "crawl_site", "screenshot"}


async def test_mcp_new_tools_against_local_site(site):
    pytest.importorskip("fastmcp")
    from fastmcp.client import Client

    from omniscrape.mcp.server import build_server

    async def call(client, name, args):
        return (await client.call_tool(name, args)).content[0].text

    async with Client(build_server()) as client:
        ents = json.loads(await call(client, "extract_entities", {"url": f"{site}/recipe"}))
        assert ents["content_type"] == "recipe" and ents["entities"]["recipe"]["total_time_minutes"] == 25

        data = json.loads(await call(client, "extract_schema", {
            "url": f"{site}/shop", "schema": {"titles": {"selector": "h3::text", "all": True}}}))
        assert data["titles"][:2] == ["Item 0", "Item 1"]

        items = json.loads(await call(client, "extract_listings", {"url": f"{site}/shop"}))
        assert len(items) == 10 and items[0]["price"] == 10.0

        links = json.loads(await call(client, "get_links", {"url": f"{site}/"}))
        assert f"{site}/recipe" in links and not any("other.test" in u for u in links)

        pages = json.loads(await call(client, "crawl_site", {"url": f"{site}/", "max_pages": 3}))
        assert 1 <= len(pages) <= 3 and pages[0]["url"].startswith(site)

        with pytest.raises(Exception, match="HTTP 403"):
            await client.call_tool("extract_entities", {"url": f"{site}/blocked"})
