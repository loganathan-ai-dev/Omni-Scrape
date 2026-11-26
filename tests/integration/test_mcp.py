"""MCP server tools, called through fastmcp's in-memory client (skipped without the mcp extra)."""

import json

import pytest

fastmcp = pytest.importorskip("fastmcp")

from omniscrape.mcp.server import build_server  # noqa: E402


async def test_mcp_tools_list_and_call(site):
    from fastmcp.client import Client

    async with Client(build_server()) as client:
        names = {t.name for t in await client.list_tools()}
        assert {"scrape_url", "scrape_product", "scrape_article", "get_markdown", "map_site"} <= names

        scraped = json.loads((await client.call_tool("scrape_url", {"url": site.base + "/page/3"})).content[0].text)
        assert scraped["title"] == "Page 3" and "html" not in scraped

        md = (await client.call_tool("get_markdown", {"url": site.base + "/page/3"})).content[0].text
        assert md.startswith("# Page 3")

        urls = json.loads((await client.call_tool("map_site", {"url": site.base + "/", "limit": 500})).content[0].text)
        assert len(urls) > 50 and not any("/private/" in u for u in urls)
