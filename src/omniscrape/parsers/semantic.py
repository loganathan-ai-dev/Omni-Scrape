"""Zero-config semantic extraction (structured data, product, article) over a single parsed tree."""

from typing import Any, Optional

from omniscrape.models import Article, Product
from omniscrape.observability.logging import get_logger
from omniscrape.parsers.structured import as_root, extract_structured, find_items

logger = get_logger("omniscrape.parsers.semantic")

ARTICLE_SIGNAL_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle", "Report",
                        "LiveBlogPosting", "OpinionNewsArticle", "AnalysisNewsArticle"}


_UNSET = object()


class SemanticExtractor:
    """Extracts structured data, products and articles without site-specific selectors.

    Pass ``root`` (an lxml element) to reuse an already-parsed document.
    """

    def __init__(self, html: str = "", url: str = "", root: Optional[Any] = None):
        self.html = html
        self.url = url
        self.root = root if root is not None else as_root(html)
        self._structured: Optional[dict[str, Any]] = None
        self._main: Optional[Any] = None
        self._metadata: Any = _UNSET
        self._product: Any = _UNSET
        self._article: Any = _UNSET

    @property
    def structured(self) -> dict[str, Any]:
        if self._structured is None:
            self._structured = extract_structured(self.root, self.url)
        return self._structured

    @property
    def main(self) -> Any:
        if self._main is None:
            from omniscrape.content.extract import extract_main

            self._main = extract_main(self.root, self.url, self.structured)
        return self._main

    @property
    def metadata(self) -> dict[str, Any]:
        if self._metadata is _UNSET:
            from omniscrape.content.metadata import extract_metadata

            self._metadata = extract_metadata(self.root, self.url, self.structured)
        return self._metadata

    def extract_all(self) -> dict[str, Any]:
        s = self.structured
        return {
            "json_ld": s["json-ld"],
            "microdata": s["microdata"],
            "rdfa": s["rdfa"],
            "opengraph": s["opengraph"],
            "meta_tags": s["meta"],
            "dublincore": s["dublincore"],
            "product": self.extract_product(),
            "article": self.extract_article(),
        }

    def extract_json_ld(self) -> list[dict[str, Any]]:
        return self.structured["json-ld"]

    def extract_microdata(self) -> list[dict[str, Any]]:
        return self.structured["microdata"]

    def extract_opengraph(self) -> dict[str, Any]:
        return {k: v for k, v in self.structured["opengraph"].items() if k.startswith(("og:", "twitter:"))}

    def extract_meta_tags(self) -> dict[str, str]:
        return dict(self.structured["meta"])

    def extract_product(self) -> Optional[Product]:
        if self._product is _UNSET:
            from omniscrape.extract.product import extract_product

            self._product = extract_product(self.root, self.url, self.structured)
        return self._product

    def is_article_like(self) -> bool:
        if find_items(self.structured, ARTICLE_SIGNAL_TYPES):
            return True
        if "article" in str(self.structured["opengraph"].get("og:type", "")).lower():
            return True
        if self.root.find(".//article") is not None:
            return True
        if find_items(self.structured, {"Product", "ProductGroup", "Offer"}):
            return False
        # short news items and docs pages are articles too; product pages are excluded above
        return len(self.main.text) >= 200

    def extract_article(self) -> Optional[Article]:
        if self._article is not _UNSET:
            return self._article
        if not self.is_article_like():
            self._article = None
            return None
        meta = self.metadata
        if not meta.get("title"):
            self._article = None
            return None
        body = self.main.text
        words = len(body.split())
        self._article = Article(
            url=self.url,
            title=meta["title"],
            author=meta.get("author"),
            published_date=meta.get("published_date"),
            modified_date=meta.get("modified_date"),
            body_text=body,
            summary=meta.get("description"),
            images=[meta["image"]] if meta.get("image") else [],
            tags=meta.get("tags") or [],
            reading_time_minutes=max(1, round(words / 230)) if words else None,
        )
        return self._article
