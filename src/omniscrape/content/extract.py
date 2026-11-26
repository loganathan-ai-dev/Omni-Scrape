"""Main-content extraction: find the article/product body and drop page boilerplate.

Approach (clean-room, no external extractor):
  1. Remove structural junk (scripts, hidden nodes, nav/aside/footer landmarks, form controls).
  2. Score text blocks by length, punctuation and link density; propagate scores to ancestors,
     weighted by class/id hints and semantic tags (article, main, itemprop=articleBody).
  3. Pick the best container, merge qualifying siblings, then prune boilerplate inside it
     (share bars, promos, comment sections, link-dense lists).
"""

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union

import lxml.html

from omniscrape.parsers.structured import as_root

JUNK_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed",
             "button", "input", "select", "textarea", "option", "link", "meta", "map", "dialog"}
LANDMARK_TAGS = {"nav", "aside", "footer", "header"}
JUNK_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog", "alert", "menu", "menubar"}
BLOCK_TAGS = {"p", "pre", "td", "blockquote", "li", "dd", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6"}
PRUNABLE = {"div", "section", "ul", "ol", "dl", "table", "aside", "p", "li", "figure", "form", "header", "footer",
            "nav", "article", "details", "menu"}

NEGATIVE = re.compile(
    r"comment|sidebar|side-bar|footer|\bfoot\b|\bnav\b|navbar|menu|share|sharing|social|related|promo|advert|"
    r"\bads?\b|\bad-|-ad\b|banner|cookie|consent|newsletter|subscribe|signup|sign-up|breadcrumb|widget|popup|"
    r"modal|masthead|pager|pagination|tag-?list|author-?bio|recommend|trending|popular|sponsor|outbrain|taboola|"
    r"disqus|toolbar|skip-link|jump-?link|print-?link|login|search-?form|newsletter|most-?read|more-?stories|"
    r"announcement|ticker|carousel|similar|you-may|upsell|cross-sell|rating-widget|byline|dateline|meta-?data|"
    r"post-?meta|entry-?meta|article-?meta|share-?bar|inline-?promo|kicker|subnav|offcanvas",
    re.IGNORECASE,
)
POSITIVE = re.compile(
    r"article|content|entry|\bpost\b|post-?body|story|\bbody\b|\btext\b|\bmain\b|prose|blog|govspeak|\brte\b|"
    r"markdown|page-?content|post-?content|description|detail",
    re.IGNORECASE,
)
_WS = re.compile(r"\s+")


@dataclass
class MainContent:
    node: Any                      # lxml element holding only the main content (a detached copy)
    title: str = ""
    text: str = ""
    score: float = 0.0
    method: str = "scored"
    removed: dict[str, int] = field(default_factory=dict)


def norm(s: str) -> str:
    return _WS.sub(" ", s or "").strip()


def text_len(el: Any) -> int:
    return len(norm(el.text_content()))


def link_density(el: Any) -> float:
    total = text_len(el)
    if not total:
        return 0.0
    linked = sum(text_len(a) for a in el.iter("a"))
    return min(1.0, linked / total)


def class_weight(el: Any) -> float:
    hint = f"{el.get('class', '')} {el.get('id', '')} {el.get('itemprop', '')} {el.get('role', '')}"
    if not hint.strip():
        return 0.0
    weight = 0.0
    if NEGATIVE.search(hint):
        weight -= 25
    if POSITIVE.search(hint):
        weight += 25
    if el.get("itemprop") == "articleBody":
        weight += 40
    return weight


def _is_hidden(el: Any) -> bool:
    if el.get("hidden") is not None or el.get("aria-hidden") == "true":
        return True
    style = (el.get("style") or "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def strip_junk(root: Any, removed: dict[str, int]) -> None:
    body_len = max(1, text_len(root))
    doomed = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            doomed.append(el)  # comments, processing instructions
            continue
        tag = el.tag.lower()
        if tag in JUNK_TAGS or _is_hidden(el) or (el.get("role") or "").lower() in JUNK_ROLES:
            doomed.append(el)
        elif tag in LANDMARK_TAGS and text_len(el) < 0.5 * body_len:
            # <header>/<footer> inside an <article> are bylines/share bars: still boilerplate for body text
            doomed.append(el)
    for el in doomed:
        if el.getparent() is None:
            continue  # already gone with an ancestor
        key = el.tag if isinstance(el.tag, str) else "comment"
        removed[key] = removed.get(key, 0) + 1
        el.drop_tree()  # keeps the element's tail text


def _tag_bonus(tag: str) -> float:
    if tag in ("article", "main"):
        return 10
    if tag in ("div", "section"):
        return 5
    if tag in ("pre", "td", "blockquote"):
        return 3
    if tag in ("ol", "ul", "dl", "dd", "dt", "li", "form", "address"):
        return -3
    if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "th"):
        return -5
    return 0


def score_candidates(root: Any) -> dict[Any, float]:
    scores: dict[Any, float] = {}

    def init(el: Any) -> None:
        if el not in scores:
            scores[el] = _tag_bonus(el.tag) + class_weight(el)

    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag
        if tag in BLOCK_TAGS or (tag in ("div", "section", "span", "font") and _direct_text(el) > 40):
            t = norm(el.text_content())
            if len(t) < 25:
                continue
            content = 1 + t.count(",") + t.count("，") + min(len(t) / 100, 3)
            ancestors = [a for a in el.iterancestors() if isinstance(a.tag, str)][:3]
            for depth, anc in enumerate(ancestors):
                if anc.tag in ("html", "body") and depth > 0:
                    break
                init(anc)
                scores[anc] += content / (1, 2, 3)[depth]
    for el in list(scores):
        scores[el] *= 1 - link_density(el)
    return scores


def _direct_text(el: Any) -> int:
    n = len(norm(el.text or ""))
    for child in el:
        n += len(norm(child.tail or ""))
    return n


def prune(node: Any, removed: dict[str, int]) -> None:
    """Remove boilerplate inside the chosen container."""
    for el in list(node.iter()):
        if el is node or not isinstance(el.tag, str) or el.getparent() is None:
            continue
        if el.tag not in PRUNABLE:
            continue  # never remove inline elements: a lone <a> inside a sentence is 100% link text
        if el.tag in ("pre", "code", "table", "h1", "h2", "h3", "h4", "h5", "h6"):
            if el.tag != "table" or link_density(el) < 0.6:
                continue
        hint = f"{el.get('class', '')} {el.get('id', '')}"
        tl = text_len(el)
        negative = NEGATIVE.search(hint) and not (POSITIVE.search(hint) and tl > 400)
        linky = tl and link_density(el) > 0.5 and tl < 400 and el.tag not in ("p",)
        if el.tag in ("p", "li") and tl and link_density(el) > 0.8 and tl < 160:
            linky = True
        if negative or linky:
            removed["pruned"] = removed.get("pruned", 0) + 1
            el.drop_tree()


def detect_title(root: Any, structured: Optional[dict[str, Any]] = None) -> str:
    title_tag = norm(root.findtext(".//title") or "")
    og = ""
    for m in root.iter("meta"):
        if (m.get("property") or m.get("name") or "").lower() in ("og:title", "twitter:title") and m.get("content"):
            og = norm(m.get("content"))
            break
    headline = ""
    if structured:
        for item in structured.get("json-ld", []):
            if item.get("headline") or (item.get("name") and "Product" in str(item.get("@type"))):
                headline = norm(str(item.get("headline") or item.get("name")))
                break
    h1s = [norm(h.text_content()) for h in root.iter("h1")]
    h1s = [h for h in h1s if 3 <= len(h) <= 300]
    references = [x for x in (headline, og, title_tag) if x]
    for h in h1s:
        if any(h.casefold() in ref.casefold() or ref.casefold() in h.casefold() for ref in references):
            return h
    for ref in (headline, og):
        if ref:
            return strip_site_suffix(ref)
    if h1s:
        return h1s[0]
    return strip_site_suffix(title_tag)


def strip_site_suffix(title: str) -> str:
    parts = re.split(r"\s+[|\-–—:·»]\s+", title)
    if len(parts) > 1:
        return max(parts, key=len) if len(parts[0]) < 15 else parts[0]
    return title


def extract_main(html_or_root: Union[str, Any], url: str = "", structured: Optional[dict[str, Any]] = None) -> MainContent:
    """Return the main content as a detached element plus title and plain text."""
    original = as_root(html_or_root)
    title = detect_title(original, structured)
    root = copy.deepcopy(original)
    body = root.find(".//body")
    if body is None:
        body = root
    removed: dict[str, int] = {}
    strip_junk(body, removed)

    scores = score_candidates(body)
    if not scores:
        node, method, best_score = body, "body", 0.0
    else:
        # strong semantic containers win ties
        for el in list(scores):
            if el.tag in ("article", "main") or el.get("itemprop") == "articleBody" or el.get("role") == "main":
                scores[el] *= 1.25
        best = max(scores, key=scores.get)
        best_score = scores[best]
        node, method = _merge_siblings(best, scores, best_score), "scored"
        chosen_len = sum(text_len(n) for n in node) if isinstance(node, list) else text_len(node)
        if chosen_len < 140 and text_len(body) > 4 * max(1, chosen_len):
            node, method = body, "body-fallback"

    container = lxml.html.Element("div", {"class": "omniscrape-main"})
    if node is body:
        for child in list(body):
            container.append(copy.deepcopy(child))
        if body.text:
            container.text = body.text
    else:
        for part in node if isinstance(node, list) else [node]:
            container.append(copy.deepcopy(part))
    prune(container, removed)
    return MainContent(node=container, title=title, text=norm(container.text_content()), score=best_score,
                       method=method, removed=removed)


def _merge_siblings(best: Any, scores: dict[Any, float], best_score: float) -> Any:
    parent = best.getparent()
    if parent is None:
        return best
    threshold = max(10.0, best_score * 0.2)
    chosen = []
    for sib in parent:
        if not isinstance(sib.tag, str):
            continue
        if sib is best:
            chosen.append(sib)
            continue
        hint = f"{sib.get('class', '')} {sib.get('id', '')}"
        if NEGATIVE.search(hint):
            continue
        s = scores.get(sib, 0.0)
        if s >= threshold:
            chosen.append(sib)
        elif sib.tag == "p":
            tl, ld = text_len(sib), link_density(sib)
            if (tl > 80 and ld < 0.25) or (0 < tl <= 80 and ld == 0 and re.search(r"\.\s*$", norm(sib.text_content()))):
                chosen.append(sib)
    return chosen if len(chosen) > 1 else best
