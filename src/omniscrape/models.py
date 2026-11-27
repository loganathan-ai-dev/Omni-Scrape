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


class Review(BaseModel):
    """One review of a product, recipe, place or organisation."""
    author: Optional[str] = None
    rating: Optional[float] = None
    best_rating: Optional[float] = None
    title: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None


class Recipe(BaseModel):
    """schema.org Recipe, normalised."""
    url: str
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    prep_time_minutes: Optional[int] = None
    cook_time_minutes: Optional[int] = None
    total_time_minutes: Optional[int] = None
    servings: Optional[str] = None
    calories: Optional[str] = None
    cuisine: Optional[str] = None
    category: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None


class Event(BaseModel):
    """schema.org Event (concerts, conferences, webinars, ...), normalised."""
    url: str
    title: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None            # e.g. "EventScheduled", "EventCancelled"
    attendance_mode: Optional[str] = None   # e.g. "OfflineEventAttendanceMode", "OnlineEventAttendanceMode"
    location_name: Optional[str] = None
    address: Optional[str] = None
    organizer: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    ticket_url: Optional[str] = None
    images: list[str] = Field(default_factory=list)


class JobPosting(BaseModel):
    """schema.org JobPosting, normalised."""
    url: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    remote: bool = False
    employment_type: Optional[str] = None
    date_posted: Optional[str] = None
    valid_through: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    salary_period: Optional[str] = None     # e.g. "HOUR", "YEAR"
    description: Optional[str] = None


class FAQItem(BaseModel):
    question: str
    answer: str


class Breadcrumb(BaseModel):
    name: str
    url: Optional[str] = None


class Organization(BaseModel):
    """The organisation or business behind a page, with contact details."""
    name: Optional[str] = None
    url: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    address: Optional[str] = None
    social_profiles: list[str] = Field(default_factory=list)


class PageEntities(BaseModel):
    """Everything zero-config extraction found on a page, beyond product and article."""
    recipe: Optional[Recipe] = None
    events: list[Event] = Field(default_factory=list)
    jobs: list[JobPosting] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    rating: Optional[float] = None          # aggregate rating of the page's main item
    rating_count: Optional[int] = None
    faq: list[FAQItem] = Field(default_factory=list)
    organization: Optional[Organization] = None
    breadcrumbs: list[Breadcrumb] = Field(default_factory=list)
    next_page: Optional[str] = None         # absolute URL of the next page of results / articles
    tables: list[list[dict[str, str]]] = Field(default_factory=list)


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
    # What kind of page this is: product, article, recipe, event, job, listing, faq, organization or other.
    content_type: str = "other"
    entities: PageEntities = Field(default_factory=PageEntities)
    links: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    fetcher_tier: int = 1
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
