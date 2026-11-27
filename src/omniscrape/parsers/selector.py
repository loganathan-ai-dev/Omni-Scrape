"""Fast lxml selector with a Scrapy/Parsel/Scrapling-compatible API.

* CSS (with ``::text`` and ``::attr(name)``) and XPath, compiled once and cached
* ``SelectorList`` results: ``.get()``, ``.getall()``, ``.re()``, ``.re_first()``, chained ``.css()``
* navigation: parent, children, next/previous, siblings, ancestors
* search: ``find``/``find_all`` (tag + attributes + text), ``find_by_text``, ``find_by_regex``,
  ``find_similar`` (structurally similar elements, e.g. other cards in a grid)
* ``generate_css_selector()`` / ``generate_xpath()`` for any element
"""

from __future__ import annotations  # methods named `re` must not shadow the module in annotations

import json
import re
from functools import lru_cache
from typing import Any, Callable, Iterable, Optional, Union
from urllib.parse import urljoin

import lxml.etree
import lxml.html
from cssselect import HTMLTranslator, SelectorError

_PSEUDO = re.compile(r"::(text|attr\(\s*([^)\s]+)\s*\))\s*$")
_translator = HTMLTranslator()


@lru_cache(maxsize=2048)
def css_to_xpath(query: str) -> str:
    """Translate CSS (supporting trailing ::text / ::attr(x) per comma group) to XPath."""
    parts = []
    for group in _split_groups(query):
        m = _PSEUDO.search(group)
        suffix = ""
        if m:
            group = group[: m.start()].strip() or "*"
            suffix = "/text()" if m.group(1) == "text" else f"/@{m.group(2)}"
        parts.append(_translator.css_to_xpath(group) + suffix)
    return " | ".join(parts)


def _split_groups(query: str) -> list[str]:
    """Split on top-level commas (not inside brackets/parentheses/quotes)."""
    groups, depth, quote, buf = [], 0, "", []
    for ch in query:
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == "," and depth == 0:
            groups.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    groups.append("".join(buf).strip())
    return [g for g in groups if g]


@lru_cache(maxsize=2048)
def _compiled_xpath(query: str) -> lxml.etree.XPath:
    return lxml.etree.XPath(query)


@lru_cache(maxsize=2048)
def _compiled_css(query: str) -> tuple[lxml.etree.XPath, bool]:
    xp = css_to_xpath(query)
    return lxml.etree.XPath(xp), "::" in query


def _wrap(results: Any, url: str = "") -> "SelectorList":
    if isinstance(results, list):
        out = SelectorList()
        append = out.append
        for item in results:
            if isinstance(item, _LXML_ELEMENT):
                if type(item.tag) is str:
                    append(Element(item, url))
            elif isinstance(item, str):
                append(item)
            elif isinstance(item, bytes):
                append(item.decode())
            elif isinstance(item, (int, float, bool)):
                append(str(item))
        return out
    return _wrap([results], url)


_LXML_ELEMENT = lxml.etree._Element


class SelectorList(list):
    """A list of Elements and/or strings with Parsel-style helpers."""

    def css(self, query: str) -> "SelectorList":
        out = SelectorList()
        for item in self:
            if isinstance(item, Element):
                out.extend(item.css(query))
        return out

    def xpath(self, query: str) -> "SelectorList":
        out = SelectorList()
        for item in self:
            if isinstance(item, Element):
                out.extend(item.xpath(query))
        return out

    def get(self, default: Optional[str] = None) -> Optional[str]:
        """First result as a string: text/attribute values as-is, elements as outer HTML."""
        for item in self:
            return item.html if isinstance(item, Element) else item
        return default

    def getall(self) -> list[str]:
        return [item.html if isinstance(item, Element) else item for item in self]

    extract_first = get
    extract = getall

    def texts(self) -> list[str]:
        return [item.text if isinstance(item, Element) else item.strip() for item in self]

    def re(self, pattern: Union[str, re.Pattern]) -> list[str]:
        out: list[str] = []
        for item in self:
            out.extend(_regex_all(pattern, item.text if isinstance(item, Element) else item))
        return out

    def re_first(self, pattern: Union[str, re.Pattern], default: Optional[str] = None) -> Optional[str]:
        found = self.re(pattern)
        return found[0] if found else default

    @property
    def first(self) -> Optional[Union["Element", str]]:
        return self[0] if self else None

    @property
    def attrib(self) -> dict[str, str]:
        for item in self:
            if isinstance(item, Element):
                return item.attrib
        return {}


def _regex_all(pattern: Union[str, re.Pattern], text: str) -> list[str]:
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern
    out = []
    for m in rx.finditer(text):
        groups = m.groupdict() or None
        if groups:
            out.extend(v for v in groups.values() if v is not None)
        elif m.groups():
            out.extend(g for g in m.groups() if g is not None)
        else:
            out.append(m.group(0))
    return out


class Element:
    """Wrapper around an lxml HTML element."""

    __slots__ = ("_node", "_url")

    def __init__(self, raw_node: lxml.html.HtmlElement, url: str = ""):
        self._node = raw_node
        self._url = url

    def __repr__(self) -> str:
        text = self.text[:40]
        return f"<Element {self.tag} {text!r}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Element) and other._node is self._node

    def __hash__(self) -> int:
        return id(self._node)

    # ------------------------------------------------------------------ content
    @property
    def tag(self) -> str:
        return self._node.tag.lower() if isinstance(self._node.tag, str) else ""

    @property
    def text(self) -> str:
        """All text inside the element (stripped)."""
        node = self._node
        if not len(node):
            t = node.text
            return t.strip() if t else ""
        return node.text_content().strip()

    @property
    def own_text(self) -> str:
        """Only the element's direct text (not its children's)."""
        parts = [self._node.text or ""] + [c.tail or "" for c in self._node]
        return " ".join(" ".join(parts).split())

    @property
    def html(self) -> str:
        return lxml.html.tostring(self._node, encoding="unicode", with_tail=False)

    @property
    def attrib(self) -> dict[str, str]:
        return dict(self._node.attrib)

    def get(self, attr_name: str, default: Optional[str] = None) -> Optional[str]:
        """Attribute value (kept for backward compatibility; see SelectorList.get for Parsel semantics)."""
        return self._node.attrib.get(attr_name, default)

    def has_class(self, name: str) -> bool:
        return name in (self._node.get("class") or "").split()

    def re(self, pattern: Union[str, re.Pattern]) -> list[str]:
        return _regex_all(pattern, self.text)

    def re_first(self, pattern: Union[str, re.Pattern], default: Optional[str] = None) -> Optional[str]:
        found = self.re(pattern)
        return found[0] if found else default

    def json(self) -> Any:
        """Parse the element's text as JSON (e.g. a <script type="application/json">)."""
        return json.loads(self._node.text_content() or "null")

    def urljoin(self, href: str) -> str:
        return urljoin(self._url, href)

    # ------------------------------------------------------------------ querying
    def css(self, query: str) -> SelectorList:
        try:
            compiled, has_pseudo = _compiled_css(query)
            res = compiled(self._node)
            if not has_pseudo:
                url = self._url
                return SelectorList(Element(el, url) for el in res if type(el.tag) is str)
            return _wrap(res, self._url)
        except (SelectorError, lxml.etree.XPathError):
            return SelectorList()

    def xpath(self, query: str, **variables: Any) -> SelectorList:
        try:
            if variables:
                return _wrap(self._node.xpath(query, **variables), self._url)
            return _wrap(_compiled_xpath(query)(self._node), self._url)
        except lxml.etree.XPathError:
            return SelectorList()

    def css_first(self, query: str) -> Optional["Element"]:
        found = self.css(query)
        return found[0] if found and isinstance(found[0], Element) else None

    # ------------------------------------------------------------------ navigation
    def parent(self) -> Optional["Element"]:
        p = self._node.getparent()
        return Element(p, self._url) if p is not None else None

    def children(self) -> list["Element"]:
        return [Element(c, self._url) for c in self._node.iterchildren() if isinstance(c.tag, str)]

    @property
    def next(self) -> Optional["Element"]:
        n = self._node.getnext()
        while n is not None and not isinstance(n.tag, str):
            n = n.getnext()
        return Element(n, self._url) if n is not None else None

    @property
    def previous(self) -> Optional["Element"]:
        p = self._node.getprevious()
        while p is not None and not isinstance(p.tag, str):
            p = p.getprevious()
        return Element(p, self._url) if p is not None else None

    @property
    def siblings(self) -> list["Element"]:
        parent = self._node.getparent()
        if parent is None:
            return []
        return [Element(s, self._url) for s in parent if s is not self._node and isinstance(s.tag, str)]

    def ancestors(self) -> list["Element"]:
        return [Element(a, self._url) for a in self._node.iterancestors()]

    def find_ancestor(self, predicate: Callable[["Element"], bool]) -> Optional["Element"]:
        for anc in self.ancestors():
            if predicate(anc):
                return anc
        return None

    def iter(self) -> Iterable["Element"]:
        for el in self._node.iter():
            if isinstance(el.tag, str):
                yield Element(el, self._url)

    # ------------------------------------------------------------------ search
    def find_all(self, tag: Optional[str] = None, text: Optional[Union[str, re.Pattern]] = None,
                 limit: Optional[int] = None, **attrs: Any) -> list["Element"]:
        """BeautifulSoup-style search. ``class_`` matches one class name; attr values may be regexes."""
        out = []
        for el in self._node.iter(tag) if tag else self._node.iter():
            if not isinstance(el.tag, str) or el is self._node:
                continue
            if attrs and not _attrs_match(el, attrs):
                continue
            if text is not None:
                content = (el.text_content() or "").strip()
                if isinstance(text, str) and text.lower() not in content.lower():
                    continue
                if isinstance(text, re.Pattern) and not text.search(content):
                    continue
            out.append(Element(el, self._url))
            if limit and len(out) >= limit:
                break
        return out

    def find(self, tag: Optional[str] = None, text: Optional[Union[str, re.Pattern]] = None, **attrs: Any) -> Optional["Element"]:
        found = self.find_all(tag, text, limit=1, **attrs)
        return found[0] if found else None

    def find_similar(self, threshold: float = 0.6, ignore_attributes: Iterable[str] = ("href", "src", "id")) -> list["Element"]:
        """Elements with the same tag path and depth and similar attributes (e.g. sibling product cards)."""
        me = self._node
        path = _tag_path(me)
        ignore = set(ignore_attributes)
        mine = {k: v for k, v in me.attrib.items() if k not in ignore}
        root = me.getroottree().getroot()
        out = []
        for el in root.iter(me.tag):
            if el is me or _tag_path(el) != path:
                continue
            theirs = {k: v for k, v in el.attrib.items() if k not in ignore}
            if _attr_similarity(mine, theirs) >= threshold:
                out.append(Element(el, self._url))
        return out

    # ------------------------------------------------------------------ selector generation
    def generate_css_selector(self) -> str:
        parts = []
        node = self._node
        root = node.getroottree().getroot()
        while node is not None and isinstance(node.tag, str):
            ident = node.get("id")
            if ident and re.fullmatch(r"[A-Za-z][\w-]*", ident) and len(root.xpath("//*[@id=$i]", i=ident)) == 1:
                parts.insert(0, f"#{ident}")
                break
            parent = node.getparent()
            if parent is None:
                parts.insert(0, node.tag)
                break
            same = [s for s in parent if s.tag == node.tag]
            parts.insert(0, node.tag if len(same) == 1 else f"{node.tag}:nth-of-type({same.index(node) + 1})")
            node = parent
        return " > ".join(parts)

    def generate_xpath(self) -> str:
        return self._node.getroottree().getpath(self._node)

    def extract(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Declarative field extraction from this element using CSS/XPath/normalizer specs.

        Each schema value may be:
          * a CSS selector string (e.g. ``"h1::text"``, ``"a::attr(href)"``)
          * a dict spec: ``{"selector": ..., "xpath": ..., "all": bool, "attr": str,
            "type": "str|int|float|price|date|unit|bool", "regex": str, "default": Any,
            "required": bool, "schema": {...}}``
        """
        return _extract_with_schema(self, schema)


def _coerce_extracted(val: Any, kind: Optional[str]) -> Any:
    if val is None or not kind:
        return val
    k = kind.lower()
    if k == "str":
        return str(val).strip()
    if k == "int":
        m = re.search(r"-?\d+", str(val).replace(",", ""))
        return int(m.group(0)) if m else None
    if k == "float":
        m = re.search(r"-?\d+(?:\.\d+)?", str(val).replace(",", ""))
        return float(m.group(0)) if m else None
    if k == "bool":
        return str(val).strip().lower() in ("1", "true", "yes", "in stock", "instock", "available")
    if k == "price":
        from omniscrape.normalizers.currency import parse_money

        amount, _ = parse_money(str(val))
        return amount
    if k == "date":
        from omniscrape.normalizers.dates import parse_date

        return parse_date(str(val))
    if k == "unit":
        from omniscrape.normalizers.units import parse_unit

        amount, _ = parse_unit(str(val))
        return amount
    return val


def _extract_with_schema(node: Any, schema: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for field_name, spec in schema.items():
        if isinstance(spec, str):
            spec = {"selector": spec}
        elif not isinstance(spec, dict):
            out[field_name] = spec
            continue

        sel = spec.get("selector") or spec.get("css")
        xp = spec.get("xpath")
        want_all = bool(spec.get("all", False))
        nested = spec.get("schema")
        attr = spec.get("attr")
        rx = spec.get("regex")
        kind = spec.get("type")
        default = spec.get("default")

        matches = node.xpath(xp) if xp else (node.css(sel) if sel else SelectorList())
        if nested is not None:
            if want_all:
                out[field_name] = [_extract_with_schema(m, nested) for m in matches if not isinstance(m, str)]
            else:
                first_el = next((m for m in matches if not isinstance(m, str)), None)
                out[field_name] = _extract_with_schema(first_el, nested) if first_el is not None else default
            continue

        def _val(item: Any) -> Any:
            if isinstance(item, str):
                raw = item.strip()
            elif attr:
                raw = item.get(attr)
            else:
                raw = item.text
            if raw is not None and rx:
                found = _regex_all(rx, str(raw))
                raw = found[0] if found else None
            return _coerce_extracted(raw, kind)

        if want_all:
            vals = [v for v in (_val(m) for m in matches) if v is not None]
            out[field_name] = vals if vals else (default if default is not None else [])
        else:
            val = _val(matches[0]) if matches else None
            if val is None and spec.get("required"):
                from omniscrape.exceptions import SchemaValidationError

                raise SchemaValidationError(f"Required schema field '{field_name}' missing")
            out[field_name] = default if val is None else val
    return out


def _tag_path(el: Any) -> tuple:
    return tuple(a.tag for a in el.iterancestors())


def _attr_similarity(a: dict[str, str], b: dict[str, str]) -> float:
    if not a and not b:
        return 1.0
    # Same attribute *names* and overlapping classes; values such as data-sku are item-specific.
    keys = set(a) | set(b)
    score = 0.0
    for k in keys:
        if k in a and k in b:
            if k == "class":
                ca, cb = set(a[k].split()), set(b[k].split())
                score += len(ca & cb) / max(1, len(ca | cb))
            else:
                score += 1.0
    return score / len(keys)


def _attrs_match(el: Any, attrs: dict[str, Any]) -> bool:
    for key, want in attrs.items():
        name = "class" if key in ("class_", "cls") else key.replace("_", "-") if key.startswith("data_") else key
        value = el.get(name)
        if value is None:
            return False
        if want is True:
            continue
        if name == "class" and isinstance(want, str):
            if want not in value.split():
                return False
        elif isinstance(want, re.Pattern):
            if not want.search(value):
                return False
        elif value != want:
            return False
    return True


_UTF8_PARSER = lxml.html.HTMLParser(encoding="utf-8")


def _parse(html: Union[str, bytes]) -> lxml.html.HtmlElement:
    """Parse str directly (no encode/decode round trip); bytes or str with an encoding declaration via UTF-8."""
    try:
        if isinstance(html, str):
            if html and not html.isspace():
                try:
                    return lxml.html.document_fromstring(html)
                except ValueError:  # "Unicode strings with encoding declaration are not supported"
                    return lxml.html.document_fromstring(html.encode("utf-8"), parser=_UTF8_PARSER)
        elif isinstance(html, (bytes, bytearray)) and html and not html.isspace():
            return lxml.html.document_fromstring(html, parser=_UTF8_PARSER)
    except (lxml.etree.ParserError, ValueError):
        pass
    return lxml.html.fromstring("<html><body></body></html>")


class FastElement:
    """Thin wrapper around a selectolax LexborNode for opt-in ``backend='selectolax'``."""

    __slots__ = ("_node", "_url")

    def __init__(self, raw_node: Any, url: str = ""):
        self._node = raw_node
        self._url = url

    @property
    def tag(self) -> str:
        return (self._node.tag or "").lower()

    @property
    def text(self) -> str:
        return (self._node.text(strip=True) or "").strip()

    @property
    def own_text(self) -> str:
        return (self._node.text(deep=False, strip=True) or "").strip()

    @property
    def html(self) -> str:
        return self._node.html or ""

    @property
    def attrib(self) -> dict[str, str]:
        return dict(self._node.attributes or {})

    def get(self, attr_name: str, default: Optional[str] = None) -> Optional[str]:
        return (self._node.attributes or {}).get(attr_name, default)

    def has_class(self, name: str) -> bool:
        return name in (self.get("class") or "").split()

    def urljoin(self, href: str) -> str:
        return urljoin(self._url, href)

    def re(self, pattern: Union[str, re.Pattern]) -> list[str]:
        return _regex_all(pattern, self.text)

    def re_first(self, pattern: Union[str, re.Pattern], default: Optional[str] = None) -> Optional[str]:
        found = self.re(pattern)
        return found[0] if found else default

    def css(self, query: str) -> SelectorList:
        out = SelectorList()
        for group in _split_groups(query):
            m = _PSEUDO.search(group)
            base = group[: m.start()].strip() if m else group
            try:
                nodes = self._node.css(base or "*")
            except Exception:
                continue
            if not m:
                out.extend(FastElement(n, self._url) for n in nodes)
            elif m.group(1) == "text":
                for n in nodes:
                    t = n.text(deep=False, strip=True)
                    if t:
                        out.append(t)
            else:
                attr = m.group(2)
                for n in nodes:
                    v = (n.attributes or {}).get(attr)
                    if v is not None:
                        out.append(v)
        return out

    def css_first(self, query: str) -> Optional["FastElement"]:
        found = self.css(query)
        return found[0] if found and isinstance(found[0], FastElement) else None

    def parent(self) -> Optional["FastElement"]:
        p = self._node.parent
        return FastElement(p, self._url) if p is not None else None

    def children(self) -> list["FastElement"]:
        out = []
        c = self._node.child
        while c is not None:
            if c.tag and not c.tag.startswith("-"):
                out.append(FastElement(c, self._url))
            c = c.next
        return out

    @property
    def next(self) -> Optional["FastElement"]:
        n = self._node.next
        while n is not None and (not n.tag or n.tag.startswith("-")):
            n = n.next
        return FastElement(n, self._url) if n is not None else None

    @property
    def previous(self) -> Optional["FastElement"]:
        p = self._node.prev
        while p is not None and (not p.tag or p.tag.startswith("-")):
            p = p.prev
        return FastElement(p, self._url) if p is not None else None

    def extract(self, schema: dict[str, Any]) -> dict[str, Any]:
        return _extract_with_schema(self, schema)


class Selector(Element):
    """Root selector for an HTML document. Use ``Selector(html, url=...)`` or ``Selector(root=tree)``.

    Self-healing selectors: ``Selector(html, url=..., adaptive=True)`` then ``css(q, auto_save=True)``
    remembers the matched element and ``css(q, adaptive=True)`` relocates it when ``q`` stops matching.
    ``storage`` is an ``AdaptiveEngine`` or a SQLite path (default ~/.omniscrape/fingerprints.db).
    Pass ``backend="selectolax"`` for opt-in Lexbor CSS speed (XPath/adaptive fall back to lxml lazily).
    """

    __slots__ = ("raw_html", "_lxml_root", "url", "adaptive", "_storage", "_engine", "backend", "_fast_root")

    def __init__(self, html: Union[str, bytes] = "", root: Optional[lxml.html.HtmlElement] = None, url: str = "",
                 adaptive: bool = False, storage: Any = None, backend: str = "lxml"):
        self.raw_html = html
        self.url = url
        self.adaptive = adaptive
        self._storage = storage
        self._engine = None
        self.backend = backend.lower()
        self._fast_root = None
        if self.backend == "selectolax" and root is None:
            try:
                from selectolax.lexbor import LexborHTMLParser
            except ImportError as exc:
                from omniscrape.exceptions import ConfigError

                raise ConfigError("selectolax is not installed. Install with 'pip install omniscrape[fast]'.") from exc
            text = html.decode("utf-8", errors="replace") if isinstance(html, (bytes, bytearray)) else (html or "")
            parser = LexborHTMLParser(text or "<html><body></body></html>")
            self._fast_root = FastElement(parser.root, url)
            self._lxml_root = None
            self._node = None
            self._url = url
        else:
            if root is None:
                root = _parse(html)
            self._lxml_root = root
            super().__init__(root, url)

    @property
    def root(self) -> lxml.html.HtmlElement:
        if self._lxml_root is None:
            self._lxml_root = _parse(self.raw_html)
            self._node = self._lxml_root
        return self._lxml_root

    @root.setter
    def root(self, value: lxml.html.HtmlElement) -> None:
        self._lxml_root = value
        self._node = value

    def _adaptive_engine(self) -> Any:
        if self._engine is None:
            from omniscrape.parsers.adaptive import AdaptiveEngine

            self._engine = self._storage if isinstance(self._storage, AdaptiveEngine) else AdaptiveEngine(self._storage)
        return self._engine

    def css(self, query: str, identifier: str = "", auto_save: bool = False, adaptive: bool = False) -> SelectorList:
        if self._fast_root is not None and not (self.adaptive and (auto_save or adaptive)):
            return self._fast_root.css(query)
        try:
            compiled, has_pseudo = _compiled_css(query)
            res = compiled(self.root)
            found = SelectorList(Element(el, self._url) for el in res if type(el.tag) is str) if not has_pseudo else _wrap(res, self._url)
        except (SelectorError, lxml.etree.XPathError):
            found = SelectorList()
        if not self.adaptive or not (auto_save or adaptive):
            return found
        from urllib.parse import urlsplit

        from omniscrape.parsers.adaptive import NodeFingerprint

        m = _PSEUDO.search(query) if "," not in query else None
        base = query[: m.start()].strip() if m else query
        elements = [e for e in (super().css(base) if m else found) if isinstance(e, Element)]
        engine, domain, key = self._adaptive_engine(), urlsplit(self.url).hostname or "default", identifier or query
        if elements and auto_save:
            engine.save_fingerprint(domain, key, NodeFingerprint.from_element(elements[0]))
        if not elements and adaptive:
            stored = engine.load_fingerprint(domain, key)
            el = engine.relocate(self, stored) if stored else None
            if el is not None:
                if not m:
                    return SelectorList([el])
                return el.xpath("text()") if m.group(1) == "text" else SelectorList(
                    [v for v in [el.get(m.group(2))] if v is not None])
        return found

    def xpath(self, query: str, **variables: Any) -> SelectorList:
        if self._node is None:
            _ = self.root
        return super().xpath(query, **variables)

    def find_all(self, tag: Optional[str] = None, text: Optional[Union[str, re.Pattern]] = None,
                 limit: Optional[int] = None, **attrs: Any) -> list["Element"]:
        if self._node is None:
            _ = self.root
        return super().find_all(tag, text, limit=limit, **attrs)

    def find_by_text(self, text: str, exact: bool = False) -> list[Element]:
        pattern = text.strip()
        matches = []
        for el in self.root.iter():
            if not isinstance(el.tag, str):
                continue
            content = (el.text_content() or "").strip()
            if (exact and content == pattern) or (not exact and pattern.lower() in content.lower()):
                matches.append(Element(el, self.url))
        return matches

    def find_by_regex(self, pattern: Union[str, re.Pattern]) -> list[Element]:
        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        return [Element(el, self.url) for el in self.root.iter()
                if isinstance(el.tag, str) and compiled.search(el.text_content() or "")]
