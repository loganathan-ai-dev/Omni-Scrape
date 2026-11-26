"""OmniScrape Command Line Interface."""

import asyncio
import json
import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def cli():
    """OmniScrape - Universal dynamic web scraping framework."""
    pass


@cli.command()
@click.argument("url")
@click.option("--format", "-f", type=click.Choice(["json", "markdown", "summary"]), default="summary")
@click.option("--tier", "-t", type=int, default=None, help="Force fetcher tier (1, 2, or 3)")
def get(url: str, format: str, tier: int):
    """Scrape and extract data from a single URL."""
    import omniscrape

    async def _run():
        with console.status(f"[bold green]Scraping {url}..."):
            res = await omniscrape.scrape(url, tier=tier)
        return res

    result = asyncio.run(_run())

    if format == "json":
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))
    elif format == "markdown":
        click.echo(result.markdown)
    else:
        table = Table(title=f"Scrape Result: {result.title or url}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Status", str(result.status_code))
        table.add_row("Latency", f"{result.latency_ms:.1f}ms")
        table.add_row("Fetcher Tier", f"Tier {result.fetcher_tier}")
        if result.product:
            table.add_row("Product Title", result.product.title)
            table.add_row("Price", f"{result.product.price} {result.product.currency}")
            table.add_row("Availability", result.product.availability)
        if result.article:
            table.add_row("Article Headline", result.article.title)
            table.add_row("Author", str(result.article.author))

        console.print(table)


@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio", show_default=True,
              help="stdio for desktop agents; http serves streamable HTTP at /mcp")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host for --transport http")
@click.option("--port", "-p", default=8000, show_default=True, help="Port for --transport http")
def mcp(transport: str, host: str, port: int):
    """Start the Model Context Protocol (MCP) server for AI agents."""
    from omniscrape.mcp.server import run_mcp_server
    run_mcp_server(transport=transport, host=host, port=port)


if __name__ == "__main__":
    cli()
