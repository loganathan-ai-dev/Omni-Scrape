"""Zero-config semantic data extractor (JSON-LD, Microdata, OpenGraph)."""

import json
import re
from typing import Any, Optional
from bs4 import BeautifulSoup
from omniscrape.models import Article, Product
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.parsers.semantic")


class SemanticExtractor:
    """Extracts structured schema without needing manual CSS/XPath locators."""

    def __init__(self, html: str, url: str = ""):
        self.html = html
        self.url = url
        self.soup = BeautifulSoup(html, "html.parser")

    def extract_all(self) -> dict[str, Any]:
        return {
            "json_ld": self.extract_json_ld(),
            "opengraph": self.extract_opengraph(),
            "meta_tags": self.extract_meta_tags(),
            "product": self.extract_product(),
            "article": self.extract_article(),
        }

    def extract_json_ld(self) -> list[dict[str, Any]]:
        scripts = self.soup.find_all("script", type="application/ld+json")
        items = []
        for s in scripts:
            try:
                raw_text = s.string or s.get_text()
                if not raw_text or not raw_text.strip():
                    continue
                data = json.loads(raw_text.strip())
                if isinstance(data, list):
                    items.extend(data)
                elif isinstance(data, dict):
                    # Handle @graph patterns
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items.extend(data["@graph"])
                    else:
                        items.append(data)
            except Exception as e:
                logger.debug(f"JSON-LD parse failure: {e}")
        return items

    def extract_opengraph(self) -> dict[str, str]:
        og = {}
        for tag in self.soup.find_all("meta"):
            prop = tag.get("property", "") or tag.get("name", "")
            if prop.startswith("og:") or prop.startswith("twitter:"):
                content = tag.get("content", "")
                if content:
                    og[prop] = content
        return og

    def extract_meta_tags(self) -> dict[str, str]:
        meta = {}
        for tag in self.soup.find_all("meta"):
            name = tag.get("name")
            content = tag.get("content")
            if name and content:
                meta[name.lower()] = content
        return meta

    def extract_product(self) -> Optional[Product]:
        """Tries to find schema.org/Product from JSON-LD or Microdata."""
        for item in self.extract_json_ld():
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else ""

            if item_type.lower() == "product":
                title = item.get("name") or self.extract_opengraph().get("og:title") or ""
                offers = item.get("offers", {})
                if isinstance(offers, list) and offers:
                    offers = offers[0]

                price_val = None
                currency_val = "USD"
                availability_val = "in_stock"

                if isinstance(offers, dict):
                    raw_price = offers.get("price")
                    if raw_price is not None:
                        try:
                            price_val = float(str(raw_price).replace(",", ""))
                        except ValueError:
                            pass
                    currency_val = offers.get("priceCurrency", "USD")
                    avail = str(offers.get("availability", "")).lower()
                    if "outofstock" in avail or "discontinued" in avail:
                        availability_val = "out_of_stock"

                images = item.get("image", [])
                if isinstance(images, str):
                    images = [images]
                elif isinstance(images, list):
                    images = [img if isinstance(img, str) else img.get("url", "") for img in images if img]

                brand_val = None
                brand = item.get("brand")
                if isinstance(brand, dict):
                    brand_val = brand.get("name")
                elif isinstance(brand, str):
                    brand_val = brand

                rating_val = None
                review_count_val = None
                agg = item.get("aggregateRating", {})
                if isinstance(agg, dict):
                    try:
                        rating_val = float(agg.get("ratingValue", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        review_count_val = int(agg.get("reviewCount", 0))
                    except (ValueError, TypeError):
                        pass

                return Product(
                    url=self.url or item.get("url", ""),
                    title=title,
                    price=price_val,
                    currency=currency_val,
                    brand=brand_val,
                    sku=item.get("sku"),
                    rating=rating_val,
                    review_count=review_count_val,
                    availability=availability_val,
                    in_stock=(availability_val == "in_stock"),
                    images=images,
                    description=item.get("description"),
                )
        return None

    def extract_article(self) -> Optional[Article]:
        """Tries to find schema.org/Article from JSON-LD or OpenGraph."""
        for item in self.extract_json_ld():
            item_type = str(item.get("@type", "")).lower()
            if item_type in ("article", "newsarticle", "blogposting"):
                title = item.get("headline") or item.get("name") or ""
                author_val = None
                author = item.get("author")
                if isinstance(author, dict):
                    author_val = author.get("name")
                elif isinstance(author, list) and author:
                    author_val = author[0].get("name") if isinstance(author[0], dict) else str(author[0])
                elif isinstance(author, str):
                    author_val = author

                return Article(
                    url=self.url or item.get("url", ""),
                    title=title,
                    author=author_val,
                    published_date=item.get("datePublished"),
                    modified_date=item.get("dateModified"),
                    body_text=item.get("articleBody", ""),
                    summary=item.get("description"),
                )
        return None
