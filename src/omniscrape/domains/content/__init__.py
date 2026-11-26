"""Content & News domain accelerator."""

from typing import Optional
from omniscrape.models import Article
from omniscrape.parsers.density import DensityAnalyzer
from omniscrape.parsers.semantic import SemanticExtractor


class ContentAdapter:
    """Optimized extractor for news, substacks, blogs, and articles."""

    @staticmethod
    def extract_article(html: str, url: str = "") -> Optional[Article]:
        extractor = SemanticExtractor(html, url)
        art = extractor.extract_article()
        if art and art.body_text:
            return art

        # Density analyzer fallback
        density = DensityAnalyzer(html)
        body = density.extract_main_content()
        if body:
            return Article(url=url, title=extractor.extract_opengraph().get("og:title", ""), body_text=body)
        return None
