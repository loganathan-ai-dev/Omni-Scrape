"""High-speed lxml/cssselect based selector and element wrapper."""

import re
from typing import Optional, Union
import lxml.html
from lxml.cssselect import CSSSelector


class Element:
    """Wrapper around an lxml HTML element with ergonomic querying methods."""

    def __init__(self, raw_node: lxml.html.HtmlElement):
        self._node = raw_node

    @property
    def tag(self) -> str:
        return self._node.tag.lower()

    @property
    def text(self) -> str:
        return (self._node.text_content() or "").strip()

    @property
    def html(self) -> str:
        return lxml.html.tostring(self._node, encoding="unicode")

    @property
    def attrib(self) -> dict[str, str]:
        return dict(self._node.attrib)

    def get(self, attr_name: str, default: Optional[str] = None) -> Optional[str]:
        return self._node.attrib.get(attr_name, default)

    def css(self, query: str) -> list["Element"]:
        try:
            sel = CSSSelector(query)
            return [Element(el) for el in sel(self._node)]
        except Exception:
            return []

    def xpath(self, query: str) -> list["Element"]:
        try:
            results = self._node.xpath(query)
            elements = []
            for item in results:
                if isinstance(item, lxml.html.HtmlElement):
                    elements.append(Element(item))
            return elements
        except Exception:
            return []

    def parent(self) -> Optional["Element"]:
        p = self._node.getparent()
        return Element(p) if p is not None else None

    def children(self) -> list["Element"]:
        return [Element(c) for c in self._node.iterchildren() if isinstance(c, lxml.html.HtmlElement)]


class Selector:
    """Root selector engine for an HTML document."""

    def __init__(self, html: str = "", root: Optional[lxml.html.HtmlElement] = None):
        self.raw_html = html
        if root is not None:  # reuse an already-parsed document
            self.root = root
            return
        try:
            parser = lxml.html.HTMLParser(encoding="utf-8")
            if isinstance(html, str):
                self.root = lxml.html.fromstring(html.encode("utf-8"), parser=parser)
            else:
                self.root = lxml.html.fromstring(html, parser=parser)
        except Exception:
            self.root = lxml.html.fromstring("<html><body></body></html>")

    def css(self, query: str) -> list[Element]:
        try:
            sel = CSSSelector(query)
            return [Element(el) for el in sel(self.root)]
        except Exception:
            return []

    def xpath(self, query: str) -> list[Element]:
        try:
            results = self.root.xpath(query)
            return [Element(item) for item in results if isinstance(item, lxml.html.HtmlElement)]
        except Exception:
            return []

    def find_by_text(self, text: str, exact: bool = False) -> list[Element]:
        pattern = text.strip()
        matches = []
        for el in self.root.iter():
            if not isinstance(el, lxml.html.HtmlElement):
                continue
            content = (el.text_content() or "").strip()
            if exact and content == pattern:
                matches.append(Element(el))
            elif not exact and pattern.lower() in content.lower():
                matches.append(Element(el))
        return matches

    def find_by_regex(self, pattern: Union[str, re.Pattern]) -> list[Element]:
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        matches = []
        for el in self.root.iter():
            if not isinstance(el, lxml.html.HtmlElement):
                continue
            content = el.text_content() or ""
            if compiled.search(content):
                matches.append(Element(el))
        return matches
