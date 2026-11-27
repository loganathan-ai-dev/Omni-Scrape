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
        self.tags = tuple(tags)

    def extract(self, selector, base_url: str) -> list[str]:
        roots = [el._node for css in self.restrict_css for el in selector.css(css)] if self.restrict_css else [selector.root]
        base_netloc = urlsplit(base_url).netloc.lower()
        out: list[str] = []
        seen: set[str] = set()
        tags = self.tags
        same_domain = self.same_domain
        pages_only = self.pages_only
        allow_domains = self.allow_domains
        deny_domains = self.deny_domains
        allow = self.allow
        deny = self.deny
        for root in roots:
            for el in root.iter(*tags):
                href = el.attrib.get("href")
                if not href:
                    continue
                href = href.strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                    continue
                absolute = urljoin(base_url, href)
                # Preserve trailing slashes on fetched URLs (avoids 301 redirects on directory routes)
                # while deduplicating /path vs /path/ via canonicalize().
                url = canonicalize(absolute, strip_trailing_slash=False)
                dedup_key = canonicalize(absolute)
                if dedup_key in seen:
                    continue
                parts = urlsplit(url)
                if parts.scheme not in ("http", "https"):
                    continue
                if same_domain and parts.netloc.lower() != base_netloc:
                    continue
                if pages_only and not looks_like_page(url):
                    continue
                if allow_domains and not domain_allowed(url, allow_domains):
                    continue
                if deny_domains and domain_allowed(url, deny_domains):
                    continue
                if allow and not any(p.search(url) for p in allow):
                    continue
                if deny and any(p.search(url) for p in deny):
                    continue
                seen.add(dedup_key)
                out.append(url)
        return out
