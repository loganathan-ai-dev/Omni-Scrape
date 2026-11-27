"""robots.txt cache: one fetch per origin, shared by all workers.

Status handling follows common crawler practice: 2xx -> rules apply; 4xx (incl. 404) -> no
restrictions; 5xx or network failure -> treat the whole site as disallowed for this run.
"""

import asyncio
import re
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote, unquote, urlsplit

from omniscrape.crawler.urls import origin
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.crawler.robots")


# Characters left as-is when normalising paths: RFC 3986 reserved/unreserved characters plus the
# robots wildcards ``*`` and ``$``. Everything else (including a literal ``%``) is percent-encoded, so
# ``/caf%C3%A9/`` in robots.txt and ``/café/`` in a URL compare equal.
_SAFE = "/?=&*$:@!,;+~-._'()"


def _normalize(path: str) -> str:
    return quote(unquote(path), safe=_SAFE)


def _compile_rule(path: str) -> re.Pattern:
    """Turn a robots path (with ``*`` wildcards and an optional ``$`` end anchor) into a regex."""
    path = _normalize(path)
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    pattern = ".*".join(re.escape(part) for part in path.split("*"))
    return re.compile(pattern + ("$" if anchored else ""))


def _parse_float(value: str) -> Optional[float]:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number >= 0 else None


def _parse_rate(value: str) -> Optional[float]:
    """``Request-rate: 1/5`` (1 request per 5 seconds) -> 5.0 seconds between requests."""
    requests, _, seconds = value.partition("/")
    try:
        n, secs = int(requests), float(seconds.rstrip("smh") or 0)
    except ValueError:
        return None
    return secs / n if n > 0 and secs > 0 else None


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str, re.Pattern]] = field(default_factory=list)  # (allow, path, regex)
    crawl_delay: Optional[float] = None
    request_rate: Optional[float] = None


class WildcardMatcher:
    """robots.txt matching with ``*`` / ``$`` wildcards (stdlib ``robotparser`` supports neither).

    Follows RFC 9309: the groups for the most specific matching user-agent token apply (falling back to
    ``*``), and all groups naming that token are merged; within them the longest matching path wins and
    ``Allow`` beats ``Disallow`` on ties. Paths are compared after percent-encoding normalisation.
    ``Crawl-delay`` / ``Request-rate`` are read from the same groups as the path rules.
    """

    def __init__(self, lines: list[str]):
        self.groups: list[_Group] = []
        current: Optional[_Group] = None
        collecting_agents = False
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key, value = key.strip().lower(), value.strip()
            if key == "user-agent":
                if current is None or not collecting_agents:
                    current = _Group()
                    self.groups.append(current)
                current.agents.append(value.lower())
                collecting_agents = True
                continue
            collecting_agents = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if value:  # an empty Disallow means "allow everything"
                    current.rules.append((key == "allow", _normalize(value), _compile_rule(value)))
            elif key == "crawl-delay" and current.crawl_delay is None:
                current.crawl_delay = _parse_float(value)
            elif key == "request-rate" and current.request_rate is None:
                current.request_rate = _parse_rate(value)

    def _groups_for(self, user_agent: str) -> list[_Group]:
        ua = user_agent.lower()
        best_token, best_len = None, -1
        for group in self.groups:
            for agent in group.agents:
                if agent != "*" and agent in ua and len(agent) > best_len:
                    best_token, best_len = agent, len(agent)
        token = best_token if best_token is not None else "*"
        return [g for g in self.groups if token in g.agents]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        groups = self._groups_for(user_agent)
        if not groups:
            return True
        parts = urlsplit(url)
        target = _normalize(parts.path or "/") + (f"?{_normalize(parts.query)}" if parts.query else "")
        best_len, allowed = -1, True
        for group in groups:
            for allow, path, regex in group.rules:
                if regex.match(target) and (len(path) > best_len or (len(path) == best_len and allow)):
                    best_len, allowed = len(path), allow
        return allowed

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        """Seconds between requests from ``Crawl-delay`` (or ``Request-rate``) of the applicable groups."""
        groups = self._groups_for(user_agent)
        for group in groups:
            if group.crawl_delay is not None:
                return group.crawl_delay
        for group in groups:
            if group.request_rate is not None:
                return group.request_rate
        return None


@dataclass
class RobotsRules:
    parser: Optional[urllib.robotparser.RobotFileParser]
    allow_all: bool = False
    disallow_all: bool = False
    matcher: Optional[WildcardMatcher] = None
    _allowed_cache: Optional[dict[str, bool]] = None
    _delay_cache: Optional[dict[str, Optional[float]]] = None

    def allowed(self, user_agent: str, url: str) -> bool:
        if self.allow_all:
            return True
        if self.disallow_all or self.parser is None:
            return False
        cache = self._allowed_cache
        if cache is None:
            cache = self._allowed_cache = {}
        key = f"{user_agent}\0{url}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        matcher = self.matcher
        res = matcher.can_fetch(user_agent, url) if matcher is not None else self.parser.can_fetch(user_agent, url)
        if len(cache) < 8192:
            cache[key] = res
        return res

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        if self.parser is None:
            return None
        cache = self._delay_cache
        if cache is None:
            cache = self._delay_cache = {}
        if user_agent in cache:
            return cache[user_agent]
        if self.matcher is not None:
            cache[user_agent] = self.matcher.crawl_delay(user_agent)
            return cache[user_agent]
        delay = self.parser.crawl_delay(user_agent)
        if delay is None:
            rate = self.parser.request_rate(user_agent)
            if rate and rate.requests:
                val: Optional[float] = rate.seconds / rate.requests
            else:
                val = None
        else:
            val = float(delay)
        cache[user_agent] = val
        return val

    def sitemaps(self) -> list[str]:
        return list(self.parser.site_maps() or []) if self.parser is not None else []


class RobotsCache:
    def __init__(self, client: Any, user_agent: str = "omniscrape"):
        self.client = client
        self.user_agent = user_agent
        self._rules: dict[str, RobotsRules] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def rules_for(self, url: str) -> RobotsRules:
        key = origin(url)
        if key in self._rules:
            return self._rules[key]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key not in self._rules:
                self._rules[key] = await self._fetch(key)
        return self._rules[key]

    async def _fetch(self, base: str) -> RobotsRules:
        robots_url = f"{base}/robots.txt"
        try:
            res = await self.client.fetch(robots_url, tier=1)
        except Exception as exc:
            logger.warning(f"robots.txt unreachable for {base} ({exc}); not crawling this site")
            return RobotsRules(None, disallow_all=True)
        if 200 <= res.status_code < 300:
            parser = urllib.robotparser.RobotFileParser(robots_url)
            lines = res.html.splitlines()
            parser.parse(lines)  # still used for Crawl-delay / Request-rate / Sitemap
            return RobotsRules(parser, matcher=WildcardMatcher(lines))
        if 400 <= res.status_code < 500:
            return RobotsRules(None, allow_all=True)
        logger.warning(f"robots.txt for {base} returned HTTP {res.status_code}; not crawling this site")
        return RobotsRules(None, disallow_all=True)

    async def allowed(self, url: str) -> bool:
        return (await self.rules_for(url)).allowed(self.user_agent, url)

    async def crawl_delay(self, url: str) -> Optional[float]:
        return (await self.rules_for(url)).crawl_delay(self.user_agent)
