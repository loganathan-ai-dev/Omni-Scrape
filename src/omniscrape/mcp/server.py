"""Model Context Protocol (MCP) server exposing scraping tools to AI agents."""

import json
from typing import Any
import click


def run_mcp_server(port: int = 8080):
    """Starts the MCP server."""
    click.echo(f"Starting OmniScrape MCP Server on port {port}...")
    try:
        from fastmcp import FastMCP
        mcp = FastMCP("OmniScrape")

        @mcp.tool()
        async def scrape_url(url: str) -> str:
            """Scrapes any URL and returns structured data and clean markdown."""
            import omniscrape
            res = await omniscrape.scrape(url)
            return json.dumps(res.model_dump(), default=str)

        @mcp.tool()
        async def scrape_product(url: str) -> str:
            """Extracts structured product information from an e-commerce page."""
            import omniscrape
            prod = await omniscrape.scrape_product(url)
            return json.dumps(prod.model_dump() if prod else {}, default=str)

        @mcp.tool()
        async def scrape_article(url: str) -> str:
            """Extracts article headline and body text from a news or blog page."""
            import omniscrape
            art = await omniscrape.scrape_article(url)
            return json.dumps(art.model_dump() if art else {}, default=str)

        mcp.run()
    except ImportError:
        click.echo("FastMCP not installed. Install with 'pip install fastmcp'.")
