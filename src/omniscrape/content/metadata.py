"""Article metadata: title, author, publish/modify dates, site name, description, language, tags.

Sources in priority order: JSON-LD (Article types) -> Microdata -> meta tags (article:*, og:*,
parsely, dc.*) -> visible markup (<time>, rel=author, byline/author classes, "By ..." lines).
"""

import re
from typing import Any, Optional, Union

from omniscrape.content.extract import detect_title, norm
from omniscrape.normalizers.dates import parse_date
from omniscrape.parsers.structured import as_root, extract_structured, find_items, first_text

ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle", "Report", "WebPage",
                 "ReportageNewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle", "LiveBlogPosting", "Recipe",
                 "HowTo", "SocialMediaPosting", "DiscussionForumPosting", "MedicalWebPage", "Guide"}
_BY = re.compile(r"^\s*(?:by|written by|posted by|author:?)\s+(.+?)(?:\s+(?:on|at|·|\||-|–|—)\s+.*)?$", re.IGNORECASE)
_DATE_HINT = re.compile(r"(date|time|publish|posted|updated|byline|dateline|meta|ts\b|\bby\b|credit)", re.IGNORECASE)
_AUTHOR_HINT = re.compile(r"(author|byline|by-?name|writer|contributor|creator)", re.IGNORECASE)
_MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_HUMAN_DATE = re.compile(
    rf"\b(\d{{4}}[-/]\d{{2}}[-/]\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\.?\s+\d{{4}}|"
    rf"{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{1,2}}-[A-Z][a-z]{{2}}-\d{{4}})\b",
    re.IGNORECASE,
)
_ORDINAL = re.compile(r"(\d{1,2})(?:st|nd|rd|th)\b", re.IGNORECASE)
_URL_DATE = re.compile(r"/(20\d{2}|19\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])(?:/|$)")


def _iso(value: Any) -> Optional[str]:
    text = first_text(value)
    if not text:
        return None
    m = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    cleaned = _ORDINAL.sub(r"\1", text)
    parsed = parse_date(cleaned)
    return parsed[:10] if parsed else None


def _author_name(value: Any) -> Optional[str]:
    name = first_text(value)
    if not name:
        return None
    name = re.sub(r"\s*<[^>]*>", "", name)          # "Name <email>"
    name = re.sub(r"^(?:by|written by)\s+", "", name, flags=re.IGNORECASE)
    if re.match(r"(?i)^(https?:)?//|^/", name):
        return None  # a profile URL (e.g. microdata itemprop=author on a link) is not a name
    return norm(name) or None


def extract_metadata(html_or_root: Union[str, Any], url: str = "", structured: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    root = as_root(html_or_root)
    structured = structured or extract_structured(root, url)
    og, meta, dc = structured["opengraph"], structured["meta"], structured["dublincore"]
    items = find_items(structured, ARTICLE_TYPES)
    item = items[0] if items else {}

    author = _author_name(item.get("author") or item.get("creator"))
    author = author or _author_name(meta.get("author") or meta.get("citation_author")
                                    or og.get("article:author") or meta.get("parsely-author")
                                    or meta.get("sailthru.author") or dc.get("creator"))
    if not author:
        author = _visible_author(root)

    published = _iso(item.get("datePublished") or item.get("dateCreated"))
    published = published or _iso(og.get("article:published_time") or og.get("article:published")
                                  or meta.get("citation_publication_date") or meta.get("citation_date")
                                  or meta.get("parsely-pub-date") or meta.get("publish-date")
                                  or meta.get("pubdate") or meta.get("datepublished") or meta.get("date")
                                  or meta.get("sailthru.date") or dc.get("date.issued")
                                  or dc.get("date") or dc.get("created"))
    if not published:
        published = _visible_date(root)
    if not published and url:
        um = _URL_DATE.search(url)
        if um:
            published = f"{um.group(1)}-{um.group(2)}-{um.group(3)}"
    modified = _iso(item.get("dateModified") or og.get("article:modified_time")
                    or og.get("og:updated_time") or meta.get("last-modified"))

    tags = item.get("keywords") or meta.get("keywords") or og.get("article:tag")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    html_el = root if root.tag == "html" else root.find(".//html")
    language = (html_el.get("lang") if html_el is not None else None) or meta.get("language") or og.get("og:locale")
    return {
        "title": detect_title(root, structured),
        "author": author,
        "published_date": published,
        "modified_date": modified,
        "site_name": og.get("og:site_name") or first_text(item.get("publisher")),
        "description": og.get("og:description") or meta.get("description") or first_text(item.get("description")),
        "language": language,
        "tags": list(tags) if isinstance(tags, list) else [],
        "image": first_text(og.get("og:image") or item.get("image")),
    }


def _visible_author(root: Any) -> Optional[str]:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.get("rel") == "author" or el.get("itemprop") == "author":
            name = _author_name(norm(el.text_content()))
            if name and len(name) < 80:
                return name
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag in ("script", "style"):
            continue
        hint = f"{el.get('class', '')} {el.get('id', '')}"
        if not _AUTHOR_HINT.search(hint) and el.tag != "address":
            continue
        text = norm(el.text_content())
        if not text or len(text) > 120:
            continue
        m = _BY.match(text)
        candidate = m.group(1) if m else text
        candidate = _HUMAN_DATE.sub("", candidate)
        candidate = re.split(r"\s+(?:·|\||-|–|—)\s+|,\s*\d", candidate)[0].strip(" ,·|")
        if 2 < len(candidate) < 80 and not re.search(r"\d{3,}", candidate):
            return candidate
    for el in root.iter("p", "span", "div"):
        text = norm(el.text_content())
        if len(text) < 80:
            m = _BY.match(text)
            if m and not re.search(r"\d{3,}", m.group(1)):
                return m.group(1).strip(" ,·|")
    return None


def _visible_date(root: Any) -> Optional[str]:
    for t in root.iter("time"):
        iso = _iso(t.get("datetime")) or _iso(norm(t.text_content()))
        if iso:
            return iso
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag in ("script", "style", "a"):
            continue
        hint = f"{el.get('class', '')} {el.get('id', '')} {el.get('itemprop', '')}"
        if not _DATE_HINT.search(hint):
            continue
        text = norm(el.text_content())
        if len(text) > 160:
            continue
        m = _HUMAN_DATE.search(text)
        if m:
            iso = _iso(m.group(0))
            if iso:
                return iso
    for el in root.iter("p", "div", "span"):  # bylines such as "By Lena Okoye | 3 Feb 2026"
        text = norm(el.text_content())
        if len(text) <= 120 and _BY.match(text):
            m = _HUMAN_DATE.search(text)
            if m and _iso(m.group(0)):
                return _iso(m.group(0))
    return None
