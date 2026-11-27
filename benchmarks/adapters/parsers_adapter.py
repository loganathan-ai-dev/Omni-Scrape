"""Adapters for standalone parsing / content-extraction libraries (idiomatic public APIs only)."""

from typing import Any

from benchmarks.adapters.base import ToolAdapter


class LxmlAdapter(ToolAdapter):
    package = "lxml"
    suites = frozenset({"parse"})

    def prepare(self) -> None:
        import cssselect  # noqa: F401
        import lxml.html  # noqa: F401

    def select_texts(self, html, selectors):
        import lxml.html

        root = lxml.html.fromstring(html)
        return [[el.text_content() for el in root.cssselect(sel)] for sel in selectors]


class Bs4Adapter(ToolAdapter):
    package = "beautifulsoup4"
    suites = frozenset({"parse"})

    def __init__(self, parser: str = "lxml"):
        self.parser = parser

    def prepare(self) -> None:
        import bs4  # noqa: F401

    def select_texts(self, html, selectors):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, self.parser)
        return [[el.get_text() for el in soup.select(sel)] for sel in selectors]


class SelectolaxAdapter(ToolAdapter):
    package = "selectolax"
    suites = frozenset({"parse"})

    def prepare(self) -> None:
        from selectolax.lexbor import LexborHTMLParser  # noqa: F401

    def select_texts(self, html, selectors):
        from selectolax.lexbor import LexborHTMLParser

        tree = LexborHTMLParser(html)
        return [[node.text() for node in tree.css(sel)] for sel in selectors]


class ParselAdapter(ToolAdapter):
    package = "parsel"
    suites = frozenset({"parse"})

    def prepare(self) -> None:
        import parsel  # noqa: F401

    def select_texts(self, html, selectors):
        from parsel import Selector

        sel = Selector(text=html)
        return [[x.xpath("string()").get() for x in sel.css(s)] for s in selectors]


class TrafilaturaAdapter(ToolAdapter):
    package = "trafilatura"
    suites = frozenset({"extract", "markdown"})

    def prepare(self) -> None:
        import trafilatura  # noqa: F401

    def extract(self, html: str, url: str, kind: str) -> dict[str, Any]:
        import trafilatura

        doc = trafilatura.bare_extraction(html, url=url, with_metadata=True)
        if doc is None:
            return {}
        data = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
        if kind == "article":
            return {"title": data.get("title"), "author": data.get("author"), "published_date": data.get("date")}
        return {"title": data.get("title")}

    def markdown(self, html: str, url: str) -> str:
        import trafilatura

        return trafilatura.extract(
            html, url=url, output_format="markdown", include_tables=True, include_formatting=True,
            include_comments=False,
        ) or ""


class MarkdownifyAdapter(ToolAdapter):
    """Whole-page converter baseline (no main-content detection)."""

    package = "markdownify"
    suites = frozenset({"markdown"})

    def prepare(self) -> None:
        import markdownify  # noqa: F401

    def markdown(self, html: str, url: str) -> str:
        from markdownify import markdownify

        # Defaults drop <script>/<style> contents; strip= would keep their text as output.
        return markdownify(html, heading_style="ATX")


class Html2TextAdapter(ToolAdapter):
    """Whole-page converter baseline (no main-content detection)."""

    package = "html2text"
    suites = frozenset({"markdown"})

    def prepare(self) -> None:
        import html2text  # noqa: F401

    def markdown(self, html: str, url: str) -> str:
        import html2text

        h = html2text.HTML2Text(baseurl=url)
        h.ignore_images = True
        h.body_width = 0
        return h.handle(html)
