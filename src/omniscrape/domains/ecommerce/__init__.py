"""E-Commerce domain accelerator."""

from typing import Optional
from omniscrape.models import Product
from omniscrape.parsers.semantic import SemanticExtractor
from omniscrape.parsers.selector import Selector


class EcommerceAdapter:
    """Universal product page parser across Shopify, Amazon, WooCommerce."""

    @staticmethod
    def extract_product(html: str, url: str = "") -> Optional[Product]:
        extractor = SemanticExtractor(html, url)
        prod = extractor.extract_product()
        if prod:
            return prod

        # Fallback to general meta / density heuristics
        sel = Selector(html)
        title_el = sel.css("h1") or sel.css(".product-title")
        title = title_el[0].text if title_el else ""
        if title:
            return Product(url=url, title=title)
        return None
