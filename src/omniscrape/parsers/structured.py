"""Structured metadata extraction in one pass over an lxml tree.

Syntaxes: JSON-LD (incl. @graph and lists), Microdata (nested itemscope), RDFa Lite
(vocab/typeof/property), OpenGraph / Twitter / product:* meta, plain <meta> tags, and
Dublin Core (DC.* / DCTERMS.*). ``uniform`` items share the shape {"@type": ..., prop: value}.
"""

import json
import re
from collections import deque
from typing import Any, Iterable, Optional, Union
from urllib.parse import urljoin

import lxml.html

from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.parsers.structured")

_URL_PROPS = {"href", "src", "data", "action"}
_JSON_COMMENTS = re.compile(r"^\s*<!--|-->\s*$")
_TRAILING_COMMAS = re.compile(r",\s*([\]}])")


def as_root(html_or_root: Union[str, bytes, Any]) -> Any:
    if isinstance(html_or_root, (str, bytes)):
        try:
            return lxml.html.fromstring(html_or_root or "<html></html>")
        except (lxml.etree.ParserError, ValueError):
            return lxml.html.fromstring("<html></html>")
    return html_or_root


def _loads_lenient(raw: str) -> Optional[Any]:
    raw = _JSON_COMMENTS.sub("", raw.strip()).strip().rstrip(";")
    if not raw:
        return None
    for candidate in (raw, _TRAILING_COMMAS.sub(r"\1", raw), raw.replace("\n", " ").replace("\t", " ")):
        try:
            return json.loads(candidate, strict=False)
        except ValueError:
            continue
    return None


def _flatten_jsonld(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            yield from _flatten_jsonld(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _flatten_jsonld(item)
            rest = {k: v for k, v in data.items() if k not in ("@graph", "@context")}
            if rest.get("@type"):
                yield rest
        else:
            yield data


def _resolve_jsonld_refs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve JSON-LD ``{"@id": "..."}`` object references against items in the same document."""
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        ident = item.get("@id")
        if isinstance(ident, str) and ident and len(item) > 1:
            by_id.setdefault(ident, item)
    if not by_id:
        return items

    def resolve(val: Any, seen: set[str]) -> Any:
        if isinstance(val, list):
            return [resolve(v, seen) for v in val]
        if isinstance(val, dict):
            ident = val.get("@id")
            if isinstance(ident, str) and ident in by_id and ident not in seen:
                target = by_id[ident]
                if len(val) == 1 or ("@type" not in val and len(val) <= 2):
                    return resolve(target, seen | {ident})
            return {k: resolve(v, seen) for k, v in val.items()}
        return val

    return [resolve(item, {item["@id"]} if isinstance(item.get("@id"), str) else set()) for item in items]


def extract_json_ld(root: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for script in root.iter("script"):
        if (script.get("type") or "").strip().lower() != "application/ld+json":
            continue
        data = _loads_lenient(script.text or "")
        if data is None:
            logger.debug("Unparseable JSON-LD block skipped")
            continue
        items.extend(_flatten_jsonld(data))
    return _resolve_jsonld_refs(items)


# ----------------------------------------------------------------------------- microdata
def _microdata_value(el: Any, base_url: str) -> Any:
    if el.get("itemscope") is not None:
        return _microdata_item(el, base_url)
    tag = el.tag
    if el.get("content") is not None:
        return el.get("content").strip()
    if tag in ("a", "link", "area"):
        return urljoin(base_url, el.get("href", ""))
    if tag in ("img", "audio", "video", "source", "embed", "iframe", "track"):
        return urljoin(base_url, el.get("src", ""))
    if tag == "object":
        return urljoin(base_url, el.get("data", ""))
    if tag in ("data", "meter") and el.get("value") is not None:
        return el.get("value")
    if tag == "time" and el.get("datetime"):
        return el.get("datetime")
    return " ".join(el.text_content().split())


def _microdata_item(scope: Any, base_url: str) -> dict[str, Any]:
    types = (scope.get("itemtype") or "").split()
    item: dict[str, Any] = {"@type": [t.rsplit("/", 1)[-1] for t in types] if len(types) > 1 else
                            (types[0].rsplit("/", 1)[-1] if types else None)}
    if scope.get("itemid"):
        item["@id"] = scope.get("itemid")
    stack = deque(scope)
    while stack:
        el = stack.popleft()
        if not isinstance(el.tag, str):
            continue
        prop = el.get("itemprop")
        if prop:
            value = _microdata_value(el, base_url)
            for name in prop.split():
                if name in item:
                    existing = item[name]
                    item[name] = (existing if isinstance(existing, list) else [existing]) + [value]
                else:
                    item[name] = value
        if el.get("itemscope") is None:  # nested scopes own their properties
            stack.extendleft(reversed(list(el)))
    return item


def extract_microdata(root: Any, base_url: str = "") -> list[dict[str, Any]]:
    out = []
    for el in root.iter():
        if isinstance(el.tag, str) and el.get("itemscope") is not None and el.get("itemprop") is None:
            out.append(_microdata_item(el, base_url))
    return out


# ----------------------------------------------------------------------------- RDFa Lite
def extract_rdfa(root: Any, base_url: str = "") -> list[dict[str, Any]]:
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.get("typeof") is None:
            continue
        item: dict[str, Any] = {"@type": (el.get("typeof") or "").split(":")[-1]}
        for child in el.iterdescendants():
            if not isinstance(child.tag, str) or child.get("property") is None:
                continue
            # stop at nested typeof scopes
            owner = next((a for a in child.iterancestors() if a.get("typeof") is not None), None)
            if owner is not el:
                continue
            name = child.get("property").split(":")[-1]
            if child.get("content") is not None:
                value: Any = child.get("content")
            elif child.get("href") or child.get("src"):
                value = urljoin(base_url, child.get("href") or child.get("src"))
            else:
                value = " ".join(child.text_content().split())
            item.setdefault(name, value)
        out.append(item)
    return out


# ----------------------------------------------------------------------------- meta tags
def extract_meta(root: Any) -> dict[str, dict[str, Any]]:
    og: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    dc: dict[str, Any] = {}
    for el in root.iter("meta"):
        key = (el.get("property") or el.get("name") or el.get("itemprop") or "").strip()
        content = el.get("content")
        if not key or content is None:
            continue
        content = content.strip()
        low = key.lower()
        if low.startswith(("og:", "twitter:", "product:", "article:", "book:", "profile:", "music:", "video:")):
            if low in og:  # repeated tags (og:image) become lists
                og[low] = (og[low] if isinstance(og[low], list) else [og[low]]) + [content]
            else:
                og[low] = content
        elif low.startswith(("dc.", "dcterms.")):
            dc[low.split(".", 1)[1]] = content
        else:
            meta.setdefault(low, content)
    return {"opengraph": og, "meta": meta, "dublincore": dc}


def extract_structured(html_or_root: Union[str, Any], url: str = "") -> dict[str, Any]:
    """All structured metadata on the page."""
    root = as_root(html_or_root)
    tags = extract_meta(root)
    return {
        "json-ld": extract_json_ld(root),
        "microdata": extract_microdata(root, url),
        "rdfa": extract_rdfa(root, url),
        "opengraph": tags["opengraph"],
        "meta": tags["meta"],
        "dublincore": tags["dublincore"],
    }


# ----------------------------------------------------------------------------- helpers
def type_names(item: dict[str, Any]) -> set[str]:
    t = item.get("@type")
    values = t if isinstance(t, list) else [t]
    return {str(v).rsplit("/", 1)[-1].rsplit(":", 1)[-1] for v in values if v}


def find_items(structured: dict[str, Any], types: set[str]) -> list[dict[str, Any]]:
    """Items of the given types from JSON-LD, Microdata and RDFa, in that priority order."""
    out = []
    for source in ("json-ld", "microdata", "rdfa"):
        for item in structured.get(source, []):
            if type_names(item) & types:
                out.append(item)
            # products are often nested (e.g. WebPage.mainEntity, ItemPage.about)
            for key in ("mainEntity", "about", "itemReviewed", "subjectOf"):
                nested = item.get(key)
                for n in nested if isinstance(nested, list) else [nested]:
                    if isinstance(n, dict) and type_names(n) & types:
                        out.append(n)
    return out


def first_text(value: Any) -> Optional[str]:
    """Best plain-text value from a JSON-LD/microdata value (str, dict with name/@value, or list)."""
    if value is None:
        return None
    if isinstance(value, list):
        for v in value:
            t = first_text(v)
            if t:
                return t
        return None
    if isinstance(value, dict):
        for key in ("name", "@value", "value", "text", "url", "@id"):
            if value.get(key):
                return first_text(value[key])
        return None
    text = " ".join(str(value).split())
    return text or None
