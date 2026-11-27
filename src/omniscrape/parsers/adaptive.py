"""Self-healing selectors: fingerprint an element once, find it again after the page changes.

A fingerprint records structure (tag, full ancestor tag path, depth, sibling position, child
tags), attributes (stable keys, classes), content (text, shingles, digit/currency shape) and
context (words from neighbouring siblings and the parent, e.g. labels such as "SKU:").
Relocation scores every element in the new page on all factors; it never requires the tag or
classes to match. A match is accepted only above ``min_confidence`` and when it beats the runner-up
by ``margin`` (ambiguous matches are rejected: a missed element is safer than a wrong one).

Use through ``Selector(html, url=..., adaptive=True)``::

    page.css(".price", auto_save=True)      # first run: remember the element
    page.css(".price", adaptive=True)       # later: falls back to relocation if the selector breaks
"""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.parsers.adaptive")

SKIP_TAGS = {"html", "head", "script", "style", "noscript", "template", "meta", "link", "title", "br", "svg", "path"}
VOLATILE_ATTRS = {"class", "style", "id"}
_WORD = re.compile(r"[^\W_]{2,}", re.UNICODE)

# factor weights (sum to 1.0)
WEIGHTS = {
    "tag": 0.10, "path": 0.22, "depth": 0.04, "parent_tag": 0.07, "attr_keys": 0.08, "classes": 0.05,
    "text_exact": 0.08, "text_shingles": 0.06, "text_shape": 0.07, "siblings": 0.05, "children": 0.05,
    "context": 0.13,
}


def _words(text: str, limit: int = 40) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text or "")][:limit]


def _shingles(text: str, n: int = 3) -> set[str]:
    t = " ".join((text or "").casefold().split())
    return {t[i:i + n] for i in range(max(1, len(t) - n + 1))} if t else set()


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def _lcs_ratio(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return 2 * prev[-1] / (len(a) + len(b))


def _own_text(node: Any) -> str:
    return " ".join((node.text_content() or "").split())


class NodeFingerprint:
    """Structural, attribute, content and context profile of a DOM node."""

    FIELDS = ("tag", "path", "hierarchy", "text", "text_len", "has_digits", "has_currency", "stable_attrib_keys",
              "classes", "attrib_count", "child_count", "child_tags", "sibling_count", "sibling_index", "dom_depth",
              "parent_tag", "id_fragment", "context")

    def __init__(self, data: dict[str, Any]):
        self.tag: str = data.get("tag", "")
        self.path: list[str] = data.get("path") or [t for t in data.get("hierarchy", "").split(">") if t]
        self.hierarchy: str = data.get("hierarchy", ">".join(self.path[-4:]))
        self.text: str = data.get("text", "")
        self.text_len: int = data.get("text_len", len(self.text))
        self.has_digits: bool = data.get("has_digits", False)
        self.has_currency: bool = data.get("has_currency", False)
        self.stable_attrib_keys: list[str] = data.get("stable_attrib_keys", [])
        self.classes: list[str] = data.get("classes", [])
        self.attrib_count: int = data.get("attrib_count", 0)
        self.child_count: int = data.get("child_count", 0)
        self.child_tags: list[str] = data.get("child_tags", [])
        self.sibling_count: int = data.get("sibling_count", 0)
        self.sibling_index: int = data.get("sibling_index", 0)
        self.dom_depth: int = data.get("dom_depth", len(self.path))
        self.parent_tag: str = data.get("parent_tag", "")
        self.id_fragment: str = data.get("id_fragment", "")
        self.context: list[str] = data.get("context", [])
        self._shingles: Optional[set[str]] = None

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.FIELDS}

    @property
    def shingles(self) -> set[str]:
        if self._shingles is None:
            self._shingles = _shingles(self.text[:300])
        return self._shingles

    @classmethod
    def from_node(cls, raw: Any) -> "NodeFingerprint":
        text = _own_text(raw)
        ancestors = [a.tag.lower() for a in raw.iterancestors() if isinstance(a.tag, str)]
        path = list(reversed(ancestors))
        parent = raw.getparent()
        siblings = [s for s in parent if isinstance(s.tag, str)] if parent is not None else [raw]
        children = [c for c in raw if isinstance(c.tag, str)]
        context_parts = []
        prev_sib, next_sib = raw.getprevious(), raw.getnext()
        while prev_sib is not None and not isinstance(prev_sib.tag, str):
            prev_sib = prev_sib.getprevious()
        while next_sib is not None and not isinstance(next_sib.tag, str):
            next_sib = next_sib.getnext()
        if prev_sib is not None:
            context_parts.append(_own_text(prev_sib)[-120:])
        if next_sib is not None:
            context_parts.append(_own_text(next_sib)[:120])
        if parent is not None:  # parent's own text outside this node (labels like "SKU:")
            parent_bits = [parent.text or ""] + [c.tail or "" for c in parent]
            context_parts.append(" ".join(parent_bits)[:200])
        stable = sorted(k for k in raw.attrib if k not in VOLATILE_ATTRS)
        return cls({
            "tag": raw.tag.lower(), "path": path, "hierarchy": ">".join(path[-4:]), "text": text[:500],
            "text_len": len(text), "has_digits": bool(re.search(r"\d", text)),
            "has_currency": bool(re.search(r"[₹$€£¥]|\b(?:USD|EUR|GBP|INR)\b", text)),
            "stable_attrib_keys": stable, "classes": sorted((raw.get("class") or "").split()),
            "attrib_count": len(raw.attrib), "child_count": len(children), "child_tags": [c.tag for c in children][:20],
            "sibling_count": len(siblings), "sibling_index": siblings.index(raw) if raw in siblings else 0,
            "dom_depth": len(path), "parent_tag": parent.tag.lower() if parent is not None and isinstance(parent.tag, str) else "",
            "id_fragment": (raw.get("id") or "")[:12], "context": _words(" ".join(context_parts)),
        })

    @classmethod
    def from_element(cls, el: Any) -> "NodeFingerprint":
        return cls.from_node(el._node if hasattr(el, "_node") else el)


def similarity(a: NodeFingerprint, b: NodeFingerprint) -> float:
    s = 0.0
    s += WEIGHTS["tag"] * (a.tag == b.tag)
    path_score = 0.5 * _lcs_ratio(a.path, b.path) + 0.5 * _lcs_ratio(a.path[-4:], b.path[-4:])
    s += WEIGHTS["path"] * path_score
    s += WEIGHTS["depth"] * max(0.0, 1 - abs(a.dom_depth - b.dom_depth) / 4)
    s += WEIGHTS["parent_tag"] * (a.parent_tag == b.parent_tag)
    s += WEIGHTS["attr_keys"] * _jaccard(set(a.stable_attrib_keys), set(b.stable_attrib_keys))
    s += WEIGHTS["classes"] * (_jaccard(set(a.classes), set(b.classes)) if a.classes or b.classes else 1.0)
    s += WEIGHTS["text_exact"] * (bool(a.text) and a.text == b.text)
    s += WEIGHTS["text_shingles"] * _jaccard(a.shingles, b.shingles)
    shape = (a.has_digits == b.has_digits) + (a.has_currency == b.has_currency)
    shape += max(0.0, 1 - abs(a.text_len - b.text_len) / max(a.text_len, b.text_len, 1))
    s += WEIGHTS["text_shape"] * shape / 3
    sib = max(0.0, 1 - abs(a.sibling_count - b.sibling_count) / max(a.sibling_count, b.sibling_count, 1))
    s += WEIGHTS["siblings"] * (0.5 * sib + 0.5 * (a.sibling_index == b.sibling_index))
    s += WEIGHTS["children"] * _lcs_ratio(a.child_tags, b.child_tags)
    s += WEIGHTS["context"] * _jaccard(set(a.context), set(b.context))
    return round(s, 4)


_DIGIT_RX = re.compile(r"\d")
_CURR_RX = re.compile(r"[₹$€£¥]|\b(?:USD|EUR|GBP|INR)\b")


def _fast_similarity(
    stored: NodeFingerprint,
    stored_ctx: set[str],
    stored_attrs: set[str],
    stored_classes: set[str],
    stored_shingles: set[str],
    node: Any,
    path: list[str],
    parent_tag: str,
    sibling_count: int,
    sibling_index: int,
    parent_ctx: str,
    sib_texts: list[str],
) -> float:
    """Compute similarity directly during top-down DFS without full NodeFingerprint construction."""
    tag = node.tag.lower()
    raw_text = node.text_content() or "" if len(node) else (node.text or "")
    text = " ".join(raw_text.split())[:500]
    text_len = len(text)

    s = WEIGHTS["tag"] * (stored.tag == tag)
    s += WEIGHTS["path"] * (0.5 * _lcs_ratio(stored.path, path) + 0.5 * _lcs_ratio(stored.path[-4:], path[-4:]))
    s += WEIGHTS["depth"] * max(0.0, 1.0 - abs(stored.dom_depth - len(path)) / 4.0)
    s += WEIGHTS["parent_tag"] * (stored.parent_tag == parent_tag)

    attrib = node.attrib
    if attrib:
        stable = {k for k in attrib if k not in VOLATILE_ATTRS}
        cls_raw = attrib.get("class")
        classes = set(cls_raw.split()) if cls_raw else set()
    else:
        stable = set()
        classes = set()
    s += WEIGHTS["attr_keys"] * _jaccard(stored_attrs, stable)
    s += WEIGHTS["classes"] * (_jaccard(stored_classes, classes) if stored_classes or classes else 1.0)

    if text:
        s += WEIGHTS["text_exact"] * (bool(stored.text) and stored.text == text)
        s += WEIGHTS["text_shingles"] * _jaccard(stored_shingles, _shingles(text[:300]))
        has_digits = bool(_DIGIT_RX.search(text))
        has_currency = bool(_CURR_RX.search(text))
    else:
        has_digits = False
        has_currency = False

    shape = (stored.has_digits == has_digits) + (stored.has_currency == has_currency)
    shape += max(0.0, 1.0 - abs(stored.text_len - text_len) / max(stored.text_len, text_len, 1))
    s += WEIGHTS["text_shape"] * shape / 3.0

    sib = max(0.0, 1.0 - abs(stored.sibling_count - sibling_count) / max(stored.sibling_count, sibling_count, 1))
    s += WEIGHTS["siblings"] * (0.5 * sib + 0.5 * (stored.sibling_index == sibling_index))

    child_tags = [c.tag for c in node if type(c.tag) is str][:20]
    s += WEIGHTS["children"] * _lcs_ratio(stored.child_tags, child_tags)

    if stored_ctx:
        parts = []
        if sibling_index > 0:
            parts.append(sib_texts[sibling_index - 1][-120:])
        if sibling_index + 1 < sibling_count:
            parts.append(sib_texts[sibling_index + 1][:120])
        if parent_ctx:
            parts.append(parent_ctx)
        cand_ctx = set(_words(" ".join(parts))) if parts else set()
        s += WEIGHTS["context"] * _jaccard(stored_ctx, cand_ctx)
    else:
        # Both empty -> jaccard({}, {}) == 1.0; non-empty cand_ctx -> 0.0
        has_ctx = bool(parent_ctx) or (sibling_index > 0 and bool(sib_texts[sibling_index - 1])) or (
            sibling_index + 1 < sibling_count and bool(sib_texts[sibling_index + 1])
        )
        if not has_ctx:
            s += WEIGHTS["context"]

    return round(s, 4)


class AdaptiveEngine:
    """Persistent fingerprints (SQLite) plus relocation."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            cache_dir = Path.home() / ".omniscrape"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "fingerprints.db")
        self.db_path = db_path
        self._cache: dict[tuple[str, str], Optional[NodeFingerprint]] = {}
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS fingerprints (
                domain TEXT, name TEXT, fingerprint TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (domain, name))""")

    def save_fingerprint(self, domain: str, name: str, fp: NodeFingerprint) -> None:
        self._cache[(domain, name)] = fp
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""INSERT INTO fingerprints (domain, name, fingerprint) VALUES (?, ?, ?)
                ON CONFLICT(domain, name) DO UPDATE SET fingerprint = excluded.fingerprint, updated_at = CURRENT_TIMESTAMP""",
                         (domain, name, json.dumps(fp.to_dict())))

    def load_fingerprint(self, domain: str, name: str) -> Optional[NodeFingerprint]:
        key = (domain, name)
        if key in self._cache:
            return self._cache[key]
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute("SELECT fingerprint FROM fingerprints WHERE domain = ? AND name = ?",
                               key).fetchone()
        fp = NodeFingerprint(json.loads(row[0])) if row else None
        self._cache[key] = fp
        return fp

    def calculate_similarity(self, fp1: NodeFingerprint, fp2: NodeFingerprint) -> float:
        return similarity(fp1, fp2)

    def rank(self, root: Any, stored: NodeFingerprint, top: int = 3) -> list[tuple[float, Any]]:
        stored_ctx = set(stored.context)
        stored_attrs = set(stored.stable_attrib_keys)
        stored_classes = set(stored.classes)
        stored_shingles = stored.shingles
        scored: list[tuple[float, Any]] = []

        # Single top-down DFS: computes path, parent_tag and sibling list once per parent.
        def walk(parent: Any, path: list[str], parent_tag: str) -> None:
            children = [c for c in parent if type(c.tag) is str]
            sib_count = len(children)
            if not sib_count:
                return
            parent_bits = [parent.text or ""] + [c.tail or "" for c in parent]
            parent_ctx = " ".join(parent_bits)[:200]
            sib_texts = [" ".join((c.text_content() or "").split()) if len(c) else " ".join((c.text or "").split()) for c in children]
            for idx, child in enumerate(children):
                tag_low = child.tag.lower()
                if tag_low not in SKIP_TAGS:
                    score = _fast_similarity(
                        stored, stored_ctx, stored_attrs, stored_classes, stored_shingles,
                        child, path, parent_tag, sib_count, idx, parent_ctx, sib_texts,
                    )
                    scored.append((score, child))
                if len(child):
                    path.append(tag_low)
                    walk(child, path, tag_low)
                    path.pop()

        root_tag = root.tag.lower() if type(root.tag) is str else ""
        if root_tag and root_tag not in SKIP_TAGS:
            scored.append((similarity(stored, NodeFingerprint.from_node(root)), root))
        if root_tag:
            walk(root, [root_tag], root_tag)

        scored.sort(key=lambda x: -x[0])
        return scored[:top]

    def relocate(self, selector: Any, stored_fp: NodeFingerprint, min_confidence: float = 0.62,
                 margin: float = 0.015) -> Optional[Any]:
        """Best-matching element in ``selector``'s document, or None if no confident, unambiguous match."""
        from omniscrape.parsers.selector import Element

        root = selector.root if hasattr(selector, "root") else selector
        ranked = self.rank(root, stored_fp)
        if not ranked:
            return None
        best_score, best = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        # A nested wrapper and its only child can tie; prefer the deeper node when their texts match.
        if len(ranked) > 1 and best_score - runner_up < margin:
            other = ranked[1][1]
            if other in best.iterdescendants() and _own_text(other) == _own_text(best):
                best, best_score = other, ranked[1][0]
                runner_up = ranked[2][0] if len(ranked) > 2 else 0.0
            elif best in other.iterdescendants() and _own_text(other) == _own_text(best):
                runner_up = ranked[2][0] if len(ranked) > 2 else 0.0
        if best_score < min_confidence or best_score - runner_up < margin:
            logger.debug(f"Adaptive relocation rejected (best={best_score}, runner-up={runner_up})")
            return None
        logger.debug(f"Adaptive relocation matched with confidence {best_score}")
        return Element(best, getattr(selector, "url", ""))
