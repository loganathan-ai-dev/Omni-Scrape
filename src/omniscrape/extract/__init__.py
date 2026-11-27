"""Zero-config and schema-driven extraction."""

from omniscrape.extract.entities import (
    detect_content_type,
    extract_breadcrumbs,
    extract_entities,
    extract_events,
    extract_faq,
    extract_jobs,
    extract_organization,
    extract_recipe,
    extract_reviews,
    extract_tables,
    find_next_page,
)
from omniscrape.extract.listings import extract_listings
from omniscrape.extract.product import extract_product

__all__ = [
    "extract_product",
    "extract_listings",
    "extract_entities",
    "detect_content_type",
    "extract_recipe",
    "extract_events",
    "extract_jobs",
    "extract_reviews",
    "extract_faq",
    "extract_organization",
    "extract_breadcrumbs",
    "find_next_page",
    "extract_tables",
]
