"""Universal Pydantic data models for structured scraping extraction."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PageType(str, Enum):
    STATIC = "STATIC"
    DYNAMIC_SPA = "DYNAMIC_SPA"
    ANTI_BOT = "ANTI_BOT"
    UNKNOWN = "UNKNOWN"


class DefenseSystem(str, Enum):
    CLOUDFLARE = "cloudflare"
    DATADOME = "datadome"
    AKAMAI = "akamai"
    PERIMETERX = "perimeterx"
    KASADA = "kasada"
    AWS_WAF = "aws_waf"
    NONE = "none"


class PageClassification(BaseModel):
    """Classification of target URL capabilities and defenses."""
    url: str
    page_type: PageType = PageType.UNKNOWN
    defense_system: DefenseSystem = DefenseSystem.NONE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    probe_latency_ms: float = 0.0
    recommended_fetcher: str = "FastFetcher"
    notes: list[str] = Field(default_factory=list)


class FetchResult(BaseModel):
    """Unified raw result returned by any fetcher tier."""
    url: str
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    html: str
    cookies: dict[str, str] = Field(default_factory=dict)
    latency_ms: float = 0.0
    fetcher_tier: int = 1
    defense_detected: DefenseSystem = DefenseSystem.NONE
    # Browser-only extras (empty for HTTP fetchers)
    screenshot: Optional[bytes] = None
    pdf: Optional[bytes] = None
    network: list[dict[str, Any]] = Field(default_factory=list)   # captured XHR/fetch JSON responses
    actions_log: list[dict[str, Any]] = Field(default_factory=list)
    action_results: list[Any] = Field(default_factory=list)
    # Crawler only: the ``meta`` dict of the Request that produced this response (like Scrapy's response.meta).
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400


class Product(BaseModel):
    """Standardized e-commerce product model."""
    url: str
    title: str
    price: Optional[float] = None
    currency: Optional[str] = None  # ISO 4217; None when the page does not show one
    brand: Optional[str] = None
    sku: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    availability: str = "unknown"
    in_stock: bool = True
    images: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class Article(BaseModel):
    """Standardized news/blog article model."""
    url: str
    title: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    modified_date: Optional[str] = None
    body_text: str = ""
    summary: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    reading_time_minutes: Optional[int] = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScrapeResult(BaseModel):
    """Comprehensive high-level scrape result."""
    url: str
    status_code: int = 200
    title: str = ""
    html: str = ""
    markdown: str = ""
    fit_markdown: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    product: Optional[Product] = None
    article: Optional[Article] = None
    links: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    fetcher_tier: int = 1
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
