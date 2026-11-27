"""Model Context Protocol (MCP) server exposing OmniScrape to AI agents (requires the ``mcp`` extra).

    omniscrape mcp                                  # stdio, for desktop agents
    omniscrape mcp --transport http --port 8000     # streamable HTTP at http://127.0.0.1:8000/mcp

Tools: scrape_url, scrape_product, scrape_article, get_markdown, map_site, extract_entities, extract_schema,
extract_listings, get_links, crawl_site, screenshot.

Error and anti-bot challenge pages (including ones served with HTTP 200) are never handed to the agent as page
content: page tools return a tool error, ``get_markdown`` returns an ``Error: ...`` message, and ``crawl_site``
marks such pages with an ``error`` field instead of their content.
"""

import json
from typing import Any, Optional

MAX_CRAWL_PAGES = 50
_CRAWL_MARKDOWN_CHARS = 1500


def _dump(model: Any, drop: tuple[str, ...] = ()) -> str:
    if model is None:
        return json.dumps({})
    data = model.model_dump(mode="json", exclude=set(drop)) if hasattr(model, "model_dump") else model
    return json.dumps(data, default=str, ensure_ascii=False)


def _blocked_message(res: Any, url: str, stealth_hint: bool = True) -> Optional[str]:
    """An error message when ``res`` is an HTTP error or an anti-bot page, else ``None``."""
    from omniscrape.classifier.strategies import is_blocked

    if res.ok and not is_blocked(res):
        return None
    defense = getattr(res.defense_detected, "value", res.defense_detected)
    note = f" (anti-bot: {defense})" if defense and defense != "none" else ""
    hint = " Retry with allow_stealth=true if blocked." if stealth_hint else ""
    return f"Error: {url} returned HTTP {res.status_code}{note}.{hint}"


def build_server() -> Any:
    """Create the FastMCP server with OmniScrape's tools."""
    from fastmcp import FastMCP
    from fastmcp.exceptions import ToolError
    from fastmcp.utilities.types import Image

    import omniscrape
    from omniscrape.parsers.semantic import SemanticExtractor

    mcp = FastMCP("OmniScrape")

    async def fetch_page(url: str, allow_stealth: bool = False, stealth_hint: bool = True, **kwargs: Any) -> Any:
        res = await omniscrape.fetch(url, allow_stealth=allow_stealth, **kwargs)
        message = _blocked_message(res, url, stealth_hint)
        if message:
            raise ToolError(message)
        return res

    @mcp.tool()
    async def scrape_url(url: str, allow_stealth: bool = False) -> str:
        """Scrape a URL: title, page type, main-content Markdown, product/article, recipes, events, jobs,
        reviews, FAQ, contacts, breadcrumbs, next page, metadata and links (no raw HTML)."""
        res = await fetch_page(url, allow_stealth)
        return _dump(omniscrape.build_scrape_result(res, url), drop=("html", "structured_data"))

    @mcp.tool()
    async def scrape_product(url: str, allow_stealth: bool = False) -> str:
        """Extract product data (title, price, currency, brand, SKU, availability, rating) from a product page."""
        res = await fetch_page(url, allow_stealth)
        return _dump(SemanticExtractor(res.html, url=res.url).extract_product())

    @mcp.tool()
    async def scrape_article(url: str, allow_stealth: bool = False) -> str:
        """Extract an article's title, author, dates and body text from a news or blog page."""
        res = await fetch_page(url, allow_stealth)
        return _dump(SemanticExtractor(res.html, url=res.url).extract_article())

    @mcp.tool()
    async def get_markdown(url: str, query: Optional[str] = None, max_tokens: Optional[int] = None,
                           allow_stealth: bool = False) -> str:
        """Main-content Markdown of a page; with `query`, only the blocks relevant to it.
        Returns a message starting with "Error:" for failed or blocked pages."""
        res = await omniscrape.fetch(url, allow_stealth=allow_stealth)
        message = _blocked_message(res, url)
        if message:
            return message
        return omniscrape.fit_markdown(res.html, url=res.url, query=query, max_tokens=max_tokens)

    @mcp.tool()
    async def map_site(url: str, search: Optional[str] = None, limit: int = 200) -> str:
        """List a site's URLs from its sitemaps and start page (robots.txt respected); `search` ranks them."""
        return json.dumps(await omniscrape.map_site(url, search=search, limit=limit))

    @mcp.tool()
    async def extract_entities(url: str, allow_stealth: bool = False) -> str:
        """Page type (product, article, recipe, event, job, listing, faq, organization, other) and every
        structured entity on the page: recipe, events, job postings, reviews and rating, FAQ, organisation
        contacts (emails, phones, address, social profiles), breadcrumbs, next-page URL and data tables."""
        res = await fetch_page(url, allow_stealth)
        page = omniscrape.build_scrape_result(res)
        return json.dumps({"url": page.url, "content_type": page.content_type,
                           "entities": page.entities.model_dump(mode="json")}, ensure_ascii=False)

    @mcp.tool()
    async def extract_schema(url: str, schema: dict[str, Any], allow_stealth: bool = False) -> str:
        """Extract fields with a declarative schema of CSS selectors, e.g.
        {"title": "h1::text", "price": {"selector": ".price::text", "type": "price"},
         "tags": {"selector": ".tag::text", "all": true}}. Types: str, int, float, bool, price, date, unit."""
        res = await fetch_page(url, allow_stealth)
        return json.dumps(omniscrape.Selector(res.html, url=res.url).extract(schema), default=str, ensure_ascii=False)

    @mcp.tool()
    async def extract_listings(url: str, allow_stealth: bool = False) -> str:
        """Items from a category, search or catalogue page: title, URL, price, currency and image per card."""
        res = await fetch_page(url, allow_stealth)
        return json.dumps(omniscrape.extract_listings(res.html, res.url), ensure_ascii=False)

    @mcp.tool()
    async def get_links(url: str, same_domain: bool = True, pattern: Optional[str] = None, limit: int = 200,
                        allow_stealth: bool = False) -> str:
        """Absolute, de-duplicated page links; `pattern` is a regex the URL must match."""
        res = await fetch_page(url, allow_stealth)
        extractor = omniscrape.LinkExtractor(allow=[pattern] if pattern else None, same_domain=same_domain)
        links = extractor.extract(omniscrape.Selector(res.html, url=res.url), res.url)
        return json.dumps(links[: max(1, limit)])

    @mcp.tool()
    async def crawl_site(url: str, max_pages: int = 20, pattern: Optional[str] = None) -> str:
        """Crawl a site from `url` (same domain, robots.txt obeyed, at most 50 pages) and return each page's
        URL, title, page type and the start of its main-content Markdown. `pattern` limits followed links.
        Blocked or challenge pages are listed with an `error` field instead of content."""
        from omniscrape.classifier.strategies import is_blocked
        from omniscrape.crawler import CrawlEngine, LinkExtractor, Request, Spider

        links = LinkExtractor(allow=[pattern] if pattern else None, same_domain=True)
        budget = max(1, min(max_pages, MAX_CRAWL_PAGES))

        class AgentSpider(Spider):
            name = "mcp-crawl"
            start_urls = [url]

            async def parse(self, response, selector):
                if is_blocked(response):
                    defense = getattr(response.defense_detected, "value", response.defense_detected)
                    yield {"url": response.url, "error": f"blocked (anti-bot: {defense})"}
                    return
                page = omniscrape.build_scrape_result(response)
                yield {"url": page.url, "title": page.title, "content_type": page.content_type,
                       "markdown": page.fit_markdown[:_CRAWL_MARKDOWN_CHARS]}
                for link in links.extract(selector, response.url):
                    yield Request(link)

        pages = [item async for item in CrawlEngine(AgentSpider(), max_pages=budget, concurrency=4).stream()]
        return json.dumps(pages, ensure_ascii=False)

    @mcp.tool()
    async def screenshot(url: str, full_page: bool = False, wait_for: Optional[str] = None) -> Image:
        """PNG screenshot of a page rendered in a real browser (needs the `browser` extra and Chromium)."""
        try:
            res = await fetch_page(url, stealth_hint=False, tier=2, screenshot=True, full_page=full_page,
                                   wait_for=wait_for)
        except ImportError as exc:
            raise ToolError("Screenshots need: pip install 'omni-scraper[browser]' && playwright install chromium") \
                from exc
        if not res.screenshot:
            raise ToolError(f"No screenshot was captured for {url}")
        return Image(data=res.screenshot, format="png")

    return mcp


def run_mcp_server(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the MCP server over stdio (default) or streamable HTTP."""
    try:
        server = build_server()
    except ImportError:
        raise SystemExit("The MCP server needs fastmcp: pip install 'omni-scraper[mcp]'")
    if transport == "stdio":
        server.run()
    else:
        server.run(transport="http", host=host, port=port)
