"""Zero-config and schema-driven extraction."""

from omniscrape.extract.listings import extract_listings
from omniscrape.extract.product import extract_product

__all__ = ["extract_product", "extract_listings"]
