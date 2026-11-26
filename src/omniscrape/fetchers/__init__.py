"""Fetcher exports."""

from omniscrape.fetchers.base import BaseFetcher
from omniscrape.fetchers.browser import DynamicFetcher
from omniscrape.fetchers.http import FastFetcher
from omniscrape.fetchers.pool import ProxyPoolManager
from omniscrape.fetchers.session import FetcherSession
from omniscrape.fetchers.stealth import StealthFetcher

__all__ = [
    "BaseFetcher",
    "FastFetcher",
    "DynamicFetcher",
    "StealthFetcher",
    "ProxyPoolManager",
    "FetcherSession",
]
