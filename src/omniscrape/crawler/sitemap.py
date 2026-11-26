"""Sitemap parsing (urlset + sitemap index) and fast site mapping (like Firecrawl's /map)."""

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

import lxml.etree

from omniscrape.crawler.links import LinkExtractor
from omniscrape.crawler.robots import RobotsCache
from omniscrape.crawler.urls import canonicalize, origin
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.crawler.sitemap")


def parse_sitemap_xml(text: str) -> tuple[list[str], list[str]]:
    """Return (page_urls, child_sitemap_urls). Tolerates missing namespaces and minor XML errors."""
    if not text or "<" not in text[:500]:
        return [], []
    try:
        root = lxml.etree.fromstring(text.encode("utf-8"), parser=lxml.etree.XMLParser(recover=True, huge_tree=True))
    except (lxml.etree.XMLSyntaxError, ValueError):
        return [], []
    if root is None:
        return [], []
    pages, children = [], []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""
        if tag != "loc" or not (el.text or "").strip():
            continue
        parent = el.getparent()
        parent_tag = parent.tag.rsplit("}", 1)[-1] if parent is not None and isinstance(parent.tag, str) else ""
        (children if parent_tag == "sitemap" else pages).append(el.text.strip())
    return pages, children


async def sitemap_urls(client: Any, sitemap_url: str, limit: int = 50_000, _depth: int = 0) -> list[str]:
    if _depth > 3:
        return []
    try:
        res = await client.fetch(sitemap_url, tier=1)
    except Exception as exc:
        logger.debug(f"sitemap fetch failed {sitemap_url}: {exc}")
        return []
    if not 200 <= res.status_code < 300:
        return []
    pages, children = parse_sitemap_xml(res.html)
    for child in children:
        if len(pages) >= limit:
            break
        pages.extend(await sitemap_urls(client, urljoin(sitemap_url, child), limit - len(pages), _depth + 1))
    return pages[:limit]


def _relevance(url: str, terms: list[str]) -> float:
    text = re.sub(r"[^a-z0-9]+", " ", url.lower())
    return sum(text.count(t) for t in terms) / (1 + len(urlsplit(url).path.split("/")) * 0.05)


async def map_site(url: str, client: Optional[Any] = None, limit: int = 5000, search: Optional[str] = None,
                   include_subdomains: bool = False, obey_robots: bool = True, use_sitemaps: bool = True) -> list[str]:
    """Discover a site's URLs quickly: robots.txt sitemaps, /sitemap.xml and links on the start page.

    With ``search``, results are ordered by how well the URL matches the search terms.
    """
    from omniscrape.client import OmniClient
    from omniscrape.parsers.selector import Selector

    owns = client is None
    client = client or OmniClient(retries=1, retry_delay=0.5)
    base = origin(url)
    host = (urlsplit(url).hostname or "").lower()
    found: dict[str, None] = {}
    try:
        robots = RobotsCache(client)
        rules = await robots.rules_for(url) if obey_robots else None
        if use_sitemaps:
            candidates = (rules.sitemaps() if rules else []) or [f"{base}/sitemap.xml", f"{base}/sitemap_index.xml"]
            for sm in candidates:
                for u in await sitemap_urls(client, urljoin(base + "/", sm), limit):
                    found.setdefault(canonicalize(u))
                if found:
                    break
        try:
            res = await client.fetch(url, tier=1)
            if 200 <= res.status_code < 300:
                for u in LinkExtractor().extract(Selector(res.html), res.url):
                    found.setdefault(u)
        except Exception as exc:
            logger.debug(f"start page fetch failed {url}: {exc}")
    finally:
        if owns:
            await client.close()

    def in_scope(u: str) -> bool:
        h = (urlsplit(u).hostname or "").lower()
        return h == host or (include_subdomains and h.endswith("." + host.removeprefix("www.")))

    urls = [u for u in found if in_scope(u)]
    if obey_robots and rules is not None:
        urls = [u for u in urls if rules.allowed(robots.user_agent, u)]
    if search:
        terms = [t for t in re.split(r"\W+", search.lower()) if t]
        urls.sort(key=lambda u: -_relevance(u, terms))
    return urls[:limit]
