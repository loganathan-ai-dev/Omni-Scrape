"""Crawler module exports."""

from omniscrape.crawler.autothrottle import AutoThrottle
from omniscrape.crawler.checkpoint import CheckpointManager
from omniscrape.crawler.dedup import URLFilter
from omniscrape.crawler.engine import CrawlEngine
from omniscrape.crawler.spider import Request, Spider

__all__ = [
    "Spider",
    "Request",
    "CrawlEngine",
    "AutoThrottle",
    "CheckpointManager",
    "URLFilter",
]
