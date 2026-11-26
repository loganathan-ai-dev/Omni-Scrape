"""Link extraction with scope rules (domains, allow/deny patterns, CSS restriction)."""

import re
from typing import Iterable, Optional, Pattern, Union
from urllib.parse import urljoin, urlsplit

from omniscrape.crawler.urls import canonicalize, looks_like_page

PatternLike = Union[str, Pattern[str]]


def _compile(patterns: Optional[Iterable[PatternLike]]) -> list[Pattern[str]]:
    return [re.compile(p) if isinstance(p, str) else p for p in (patterns or [])]


def domain_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    allowed = [d.lower().lstrip(".") for d in allowed_domains if d]
    if not allowed:
        return True
    host = (urlsplit(url).hostname or "").lower()
    netloc = urlsplit(url).netloc.lower()
    return any(host == d or host.endswith("." + d) or netloc == d for d in allowed)


class LinkExtractor:
    """Extract absolute, canonical, de-duplicated links from a page.

    ``allow``/``deny`` are regexes matched against the absolute URL; ``restrict_css`` limits the
    search to parts of the page (e.g. "main", "nav.pagination"); ``same_domain`` keeps only links
    on the page's own host (host:port).
    """

    def __init__(self, allow: Optional[Iterable[PatternLike]] = None, deny: Optional[Iterable[PatternLike]] = None,
                 allow_domains: Optional[Iterable[str]] = None, deny_domains: Optional[Iterable[str]] = None,
                 restrict_css: Optional[Union[str, Iterable[str]]] = None, same_domain: bool = False,
                 pages_only: bool = True, tags: Iterable[str] = ("a", "area")):
        self.allow = _compile(allow)
        self.deny = _compile(deny)
        self.allow_domains = list(allow_domains or [])
        self.deny_domains = list(deny_domains or [])
        self.restrict_css = [restrict_css] if isinstance(restrict_css, str) else list(restrict_css or [])
        self.same_domain = same_domain
        self.pages_only = pages_only
        self.tags = set(tags)

    def extract(self, selector, base_url: str) -> list[str]:
        roots = [el._node for css in self.restrict_css for el in selector.css(css)] if self.restrict_css else [selector.root]
        base_netloc = urlsplit(base_url).netloc.lower()
        out: list[str] = []
        seen: set[str] = set()
        for root in roots:
            for el in root.iter(*self.tags):
                href = (el.get("href") or "").strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                    continue
                absolute = urljoin(base_url, href)
                if urlsplit(absolute).scheme not in ("http", "https"):
                    continue
                url = canonicalize(absolute)
                if url in seen:
                    continue
                if self.same_domain and urlsplit(url).netloc.lower() != base_netloc:
                    continue
                if self.pages_only and not looks_like_page(url):
                    continue
                if self.allow_domains and not domain_allowed(url, self.allow_domains):
                    continue
                if self.deny_domains and domain_allowed(url, self.deny_domains):
                    continue
                if self.allow and not any(p.search(url) for p in self.allow):
                    continue
                if any(p.search(url) for p in self.deny):
                    continue
                seen.add(url)
                out.append(url)
        return out
