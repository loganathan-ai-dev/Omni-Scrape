"""Model Context Protocol (MCP) server exposing OmniScrape to AI agents (requires the ``mcp`` extra).

    omniscrape mcp                                  # stdio, for desktop agents
    omniscrape mcp --transport http --port 8000     # streamable HTTP at http://127.0.0.1:8000/mcp
"""

import json
from typing import Any, Optional


def _dump(model: Any, drop: tuple[str, ...] = ()) -> str:
    if model is None:
        return json.dumps({})
    data = model.model_dump(exclude=set(drop)) if hasattr(model, "model_dump") else model
    return json.dumps(data, default=str)


def build_server() -> Any:
    """Create the FastMCP server with OmniScrape's tools."""
    from fastmcp import FastMCP

    import omniscrape

    mcp = FastMCP("OmniScrape")

    @mcp.tool()
    async def scrape_url(url: str, allow_stealth: bool = False) -> str:
        """Scrape a URL: title, main-content Markdown, product/article data, metadata and links (no raw HTML)."""
        res = await omniscrape.scrape(url, allow_stealth=allow_stealth)
        return _dump(res, drop=("html", "structured_data"))

    @mcp.tool()
    async def scrape_product(url: str) -> str:
        """Extract product data (title, price, currency, brand, SKU, availability, rating) from a product page."""
        return _dump(await omniscrape.scrape_product(url))

    @mcp.tool()
    async def scrape_article(url: str) -> str:
        """Extract an article's title, author, dates and body text from a news or blog page."""
        return _dump(await omniscrape.scrape_article(url))

    @mcp.tool()
    async def get_markdown(url: str, query: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """Main-content Markdown of a page; with `query`, only the blocks relevant to it."""
        res = await omniscrape.fetch(url)
        return omniscrape.fit_markdown(res.html, url=res.url, query=query, max_tokens=max_tokens)

    @mcp.tool()
    async def map_site(url: str, search: Optional[str] = None, limit: int = 200) -> str:
        """List a site's URLs from its sitemaps and start page (robots.txt respected); `search` ranks them."""
        return json.dumps(await omniscrape.map_site(url, search=search, limit=limit))

    return mcp


def run_mcp_server(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server over stdio (default) or streamable HTTP."""
    try:
        server = build_server()
    except ImportError:
        raise SystemExit("The MCP server needs fastmcp: pip install 'omniscrape[mcp]'")
    if transport == "stdio":
        server.run()
    else:
        server.run(transport="http", host=host, port=port)
