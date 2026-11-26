"""Domains module exports."""

from omniscrape.domains.content import ContentAdapter
from omniscrape.domains.ecommerce import EcommerceAdapter
from omniscrape.domains.quickcommerce import QuickCommerceAdapter

__all__ = [
    "QuickCommerceAdapter",
    "EcommerceAdapter",
    "ContentAdapter",
]
