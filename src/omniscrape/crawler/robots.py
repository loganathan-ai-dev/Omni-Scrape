"""robots.txt cache: one fetch per origin, shared by all workers.

Status handling follows common crawler practice: 2xx -> rules apply; 4xx (incl. 404) -> no
restrictions; 5xx or network failure -> treat the whole site as disallowed for this run.
"""

import asyncio
import urllib.robotparser
from dataclasses import dataclass
from typing import Any, Optional

from omniscrape.crawler.urls import origin
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.crawler.robots")


@dataclass
class RobotsRules:
    parser: Optional[urllib.robotparser.RobotFileParser]
    allow_all: bool = False
    disallow_all: bool = False

    def allowed(self, user_agent: str, url: str) -> bool:
        if self.allow_all:
            return True
        if self.disallow_all or self.parser is None:
            return False
        return self.parser.can_fetch(user_agent, url)

    def crawl_delay(self, user_agent: str) -> Optional[float]:
        if self.parser is None:
            return None
        delay = self.parser.crawl_delay(user_agent)
        if delay is None:
            rate = self.parser.request_rate(user_agent)
            if rate and rate.requests:
                return rate.seconds / rate.requests
        return float(delay) if delay is not None else None

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
            parser.parse(res.html.splitlines())
            return RobotsRules(parser)
        if 400 <= res.status_code < 500:
            return RobotsRules(None, allow_all=True)
        logger.warning(f"robots.txt for {base} returned HTTP {res.status_code}; not crawling this site")
        return RobotsRules(None, disallow_all=True)

    async def allowed(self, url: str) -> bool:
        return (await self.rules_for(url)).allowed(self.user_agent, url)

    async def crawl_delay(self, url: str) -> Optional[float]:
        return (await self.rules_for(url)).crawl_delay(self.user_agent)
