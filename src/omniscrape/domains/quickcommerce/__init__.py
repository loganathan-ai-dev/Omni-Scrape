"""QuickCommerce domain accelerator."""

from typing import Optional
from omniscrape.fetchers.http import FastFetcher
from omniscrape.models import Product
from omniscrape.parsers.selector import Selector


class QuickCommerceAdapter:
    """Specialized geolocation and catalog crawler for Q-Commerce apps."""

    def __init__(self, lat: float = 12.9716, lon: float = 77.5946):
        self.lat = lat
        self.lon = lon
        self.fetcher = FastFetcher(default_headers={
            "lat": str(lat),
            "lon": str(lon),
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
        })

    async def get_page(self, url: str):
        return await self.fetcher.fetch(url)
