"""OmniScrape command line interface.

    omniscrape get URL [-f summary|json|markdown] [--css SELECTOR] [--tier N] [--stealth] ...
    omniscrape crawl URL --max-pages 100 -o items.jsonl [--resume]
    omniscrape map URL [--search TERMS]
    omniscrape extract URL --schema schema.json
    omniscrape shell [URL]
    omniscrape mcp [--transport stdio|http]
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

from omniscrape._version import __version__

# Human-facing output (tables, spinners) goes to stderr so stdout carries only data and
# `omniscrape get -f json | jq` / `... > page.md` stay clean.
console = Console(stderr=True)

_HEADER_HELP = "Extra request header 'Name: value' (repeatable)"


def _parse_headers(values: tuple[str, ...]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in values:
        name, sep, value = item.partition(":")
        if not sep or not name.strip():
            raise click.BadParameter(f"expected 'Name: value', got {item!r}", param_hint="--header")
        headers[name.strip()] = value.strip()
    return headers


def _fetch_options(tier: Optional[int], stealth: bool, proxy: Optional[str], header: tuple[str, ...],
                   timeout: float, wait_for: Optional[str]) -> dict[str, Any]:
    opts: dict[str, Any] = {"tier": tier, "allow_stealth": stealth, "proxy": proxy,
                            "headers": _parse_headers(header) or None, "timeout": timeout}
    if wait_for:
        opts["wait_for"] = wait_for
    return opts


def _fail(message: str) -> "click.exceptions.Exit":
    console.print(f"[bold red]error:[/bold red] {message}")
    return click.exceptions.Exit(1)


def _emit(text: str, output: Optional[str]) -> None:
    if output:
        Path(output).write_text(text, encoding="utf-8")
        console.print(f"[green]wrote[/green] {output}")
    else:
        click.echo(text)


def _run(coro):
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        raise click.exceptions.Exit(130)
    except click.exceptions.Exit:
        raise
    except Exception as exc:  # network errors, bad URLs, missing extras: show a message, not a traceback
        raise _fail(f"{type(exc).__name__}: {exc}")


_common_fetch_options = [
    click.option("--tier", "-t", type=int, default=None, help="Force fetcher tier (1 HTTP, 2 browser, 3 stealth)"),
    click.option("--stealth", is_flag=True, help="Allow escalation to the stealth browser tier"),
    click.option("--proxy", default=None, help="Proxy URL, e.g. http://user:pass@host:8080"),
    click.option("--header", "-H", multiple=True, help=_HEADER_HELP),
    click.option("--timeout", type=float, default=30.0, show_default=True, help="Request timeout in seconds"),
    click.option("--wait-for", default=None, help="CSS selector to wait for (browser tiers)"),
]


def _with_fetch_options(fn):
    for opt in reversed(_common_fetch_options):
        fn = opt(fn)
    return fn


@click.group()
@click.version_option(__version__, prog_name="omniscrape")
def cli():
    """OmniScrape: adaptive web scraping for Python."""


# ------------------------------------------------------------------------------------------ get
@cli.command()
@click.argument("url")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown", "summary"]), default="summary",
              show_default=True)
@click.option("--css", "-s", default=None, help="CSS selector; print the matching elements' text instead")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False), help="Write output to a file")
@_with_fetch_options
def get(url: str, fmt: str, css: Optional[str], output: Optional[str], tier, stealth, proxy, header, timeout,
        wait_for):
    """Scrape and extract data from a single URL."""
    import omniscrape

    opts = _fetch_options(tier, stealth, proxy, header, timeout, wait_for)

    async def _go():
        with console.status(f"[bold green]Scraping {url}..."):
            return await omniscrape.scrape(url, **opts)

    result = _run(_go())

    if css:
        from omniscrape.parsers.selector import Selector

        found = Selector(result.html, url=result.url).css(css)
        # `::text` / `::attr()` selectors yield strings; element selectors yield Elements.
        _emit("\n".join(el if isinstance(el, str) else el.text for el in found), output)
        if not found:
            raise _fail(f"selector {css!r} matched nothing")
        return

    if fmt == "json":
        _emit(json.dumps(result.model_dump(), indent=2, default=str), output)
    elif fmt == "markdown":
        _emit(result.markdown, output)
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
            table.add_row("Availability", str(result.product.availability))
        if result.article:
            table.add_row("Article Headline", result.article.title)
            table.add_row("Author", str(result.article.author))
        table.add_row("Links", str(len(result.links)))
        console.print(table)


# ---------------------------------------------------------------------------------------- crawl
@cli.command()
@click.argument("url")
@click.option("--max-pages", type=int, default=50, show_default=True, help="Stop after this many pages")
@click.option("--depth", "max_depth", type=int, default=None, help="Maximum link depth from the start URL")
@click.option("--concurrency", "-c", type=int, default=5, show_default=True)
@click.option("--delay", type=float, default=0.0, show_default=True, help="Seconds between requests per domain")
@click.option("--output", "-o", default="omniscrape-items.jsonl", show_default=True,
              type=click.Path(dir_okay=False), help="Output file: .jsonl or .duckdb")
@click.option("--allow", default=None, help="Only follow URLs matching this regex")
@click.option("--deny", default=None, help="Never follow URLs matching this regex")
@click.option("--resume/--no-resume", default=False,
              help="Persist the queue and resume an interrupted crawl (appends to --output)")
@click.option("--append", is_flag=True, help="Append to an existing --output instead of replacing it")
@click.option("--no-robots", is_flag=True, help="Do not obey robots.txt (only for sites you own or may crawl)")
@click.option("--sitemap", is_flag=True, help="Also seed the queue from the site's sitemaps")
@click.option("--tier", "-t", type=int, default=1, show_default=True, help="Fetcher tier for every page")
def crawl(url: str, max_pages: int, max_depth: Optional[int], concurrency: int, delay: float, output: str,
          allow: Optional[str], deny: Optional[str], resume: bool, append: bool, no_robots: bool, sitemap: bool,
          tier: int):
    """Crawl a site from URL, extracting each page, and save items to a file."""
    from urllib.parse import urlsplit

    from omniscrape.client import build_scrape_result
    from omniscrape.crawler import CrawlEngine, LinkExtractor, Request, Spider
    from omniscrape.storage import BaseStorage, DuckDBStorage, JSONLStorage

    parsed_host = urlsplit(url).hostname
    if not parsed_host:
        raise _fail(f"not a valid URL: {url}")
    host: str = parsed_host
    out_path = Path(output)
    suffix = out_path.suffix.lower()
    if suffix not in (".jsonl", ".ndjson", ".duckdb"):
        hint = " (items are written one JSON object per line; use .jsonl)" if suffix == ".json" else ""
        raise _fail(f"output must end in .jsonl, .ndjson or .duckdb{hint}")
    # A fresh crawl replaces the previous output; --resume continues it and --append adds to it.
    if out_path.exists() and not (resume or append):
        out_path.unlink()
        console.print(f"[dim]replacing existing {output} (use --append to keep it)[/dim]")
    storage: BaseStorage = DuckDBStorage(output) if suffix == ".duckdb" else JSONLStorage(output)

    links = LinkExtractor(allow=[allow] if allow else None, deny=[deny] if deny else None, same_domain=True)

    class CliSpider(Spider):
        name = f"cli-{host}"
        start_urls = [url]
        allowed_domains = [host]

        async def parse(self, response, selector):
            page = build_scrape_result(response)
            item: dict[str, Any] = {"url": response.url, "status": response.status_code, "title": page.title,
                                    "markdown": page.fit_markdown}
            if page.product:
                item["product"] = page.product.model_dump(mode="json", exclude={"scraped_at"})
            if page.article:
                item["article"] = page.article.model_dump(mode="json")
            yield item
            for link in links.extract(selector, response.url):
                yield Request(link)

    engine = CrawlEngine(CliSpider(), storage=storage, use_checkpoint=resume, max_pages=max_pages,
                         max_depth=max_depth, concurrency=concurrency, download_delay=delay,
                         obey_robots=not no_robots, start_from_sitemap=sitemap, resume=resume, tier=tier)

    async def _go():
        with console.status(f"[bold green]Crawling {url} (max {max_pages} pages)..."):
            return await engine.run()

    stats = _run(_go())
    summary = stats.to_dict()
    table = Table(title=f"Crawl finished -> {output}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    for key, value in summary.items():
        table.add_row(str(key), str(value))
    console.print(table)


# ------------------------------------------------------------------------------------------ map
@cli.command("map")
@click.argument("url")
@click.option("--search", "-q", default=None, help="Rank URLs by relevance to these terms")
@click.option("--limit", type=int, default=200, show_default=True)
@click.option("--format", "-f", "fmt", type=click.Choice(["text", "json"]), default="text", show_default=True)
def map_(url: str, search: Optional[str], limit: int, fmt: str):
    """List a site's URLs from its sitemaps and start page (robots.txt respected)."""
    import omniscrape

    async def _go():
        with console.status(f"[bold green]Mapping {url}..."):
            return await omniscrape.map_site(url, search=search, limit=limit)

    urls = _run(_go())
    click.echo(json.dumps(urls, indent=2) if fmt == "json" else "\n".join(urls))
    console.print(f"[dim]{len(urls)} URLs[/dim]")


# --------------------------------------------------------------------------------------- extract
@cli.command()
@click.argument("url")
@click.option("--schema", "-s", "schema_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="JSON file with a declarative schema (see Selector.extract)")
@click.option("--output", "-o", default=None, type=click.Path(dir_okay=False), help="Write JSON to a file")
@_with_fetch_options
def extract(url: str, schema_path: str, output: Optional[str], tier, stealth, proxy, header, timeout, wait_for):
    """Extract fields from URL using a JSON schema of CSS/XPath selectors."""
    import omniscrape
    from omniscrape.exceptions import SchemaValidationError
    from omniscrape.parsers.selector import Selector

    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _fail(f"{schema_path} is not valid JSON: {exc}")
    if not isinstance(schema, dict):
        raise _fail("the schema file must contain a JSON object")
    opts = _fetch_options(tier, stealth, proxy, header, timeout, wait_for)
    opts.pop("allow_stealth")

    async def _go():
        with console.status(f"[bold green]Fetching {url}..."):
            return await omniscrape.fetch(url, allow_stealth=stealth, **opts)

    res = _run(_go())
    try:
        data = Selector(res.html, url=res.url).extract(schema)
    except SchemaValidationError as exc:
        raise _fail(str(exc))
    _emit(json.dumps(data, indent=2, ensure_ascii=False, default=str), output)


# ------------------------------------------------------------------------------------------ shell
@cli.command()
@click.argument("url", required=False)
@click.option("--plain", is_flag=True, help="Use the standard Python REPL even if IPython is installed")
def shell(url: Optional[str], plain: bool):
    """Interactive shell with omniscrape preloaded; pass URL to start with `page` fetched."""
    import omniscrape
    from omniscrape.parsers.selector import Selector

    namespace: dict[str, Any] = {
        "omniscrape": omniscrape, "Selector": Selector, "scrape_sync": omniscrape.scrape_sync,
        "fetch_sync": lambda u, **kw: asyncio.run(omniscrape.fetch(u, **kw)),
    }
    banner = ["OmniScrape shell", "  fetch_sync(url)   -> FetchResult", "  scrape_sync(url)  -> ScrapeResult",
              "  Selector(html)    -> parse and query with .css() / .xpath() / .find_all()"]
    if url:
        try:
            namespace["response"] = namespace["fetch_sync"](url)
        except Exception as exc:
            raise _fail(f"{type(exc).__name__}: {exc}")
        namespace["page"] = Selector(namespace["response"].html, url=namespace["response"].url)
        banner.append(f"  response, page    -> {url} (HTTP {namespace['response'].status_code})")
    text = "\n".join(banner)

    if not plain:
        try:
            from IPython import start_ipython
        except ImportError:
            console.print("[dim]IPython not installed (pip install 'omni-scrape[shell]'); using the standard REPL[/dim]")
        else:
            click.echo(text)
            start_ipython(argv=["--no-banner"], user_ns=namespace)
            return
    import code

    code.interact(banner=text, local=namespace)


# -------------------------------------------------------------------------------------------- mcp
@cli.command()
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio", show_default=True,
              help="stdio for desktop agents; http serves streamable HTTP at /mcp")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host for --transport http")
@click.option("--port", "-p", default=8000, show_default=True, help="Port for --transport http")
def mcp(transport: str, host: str, port: int):
    """Start the Model Context Protocol (MCP) server for AI agents."""
    from omniscrape.mcp.server import run_mcp_server

    run_mcp_server(transport=transport, host=host, port=port)


def main() -> None:  # pragma: no cover - console-script helper
    cli(prog_name="omniscrape")


if __name__ == "__main__":
    sys.exit(cli())
