"""12-factor structural fingerprinting and self-healing selector engine."""

import os
import re
import sqlite3
import json
from contextlib import closing
from pathlib import Path
from typing import Any, Optional
import lxml.html
from omniscrape.parsers.selector import Element, Selector
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.parsers.adaptive")


class NodeFingerprint:
    """12-factor structural profile of an HTML DOM node."""

    def __init__(self, data: dict[str, Any]):
        self.tag: str = data.get("tag", "")
        self.hierarchy: str = data.get("hierarchy", "")
        self.text_len: int = data.get("text_len", 0)
        self.has_digits: bool = data.get("has_digits", False)
        self.has_currency: bool = data.get("has_currency", False)
        self.stable_attrib_keys: list[str] = data.get("stable_attrib_keys", [])
        self.attrib_count: int = data.get("attrib_count", 0)
        self.child_count: int = data.get("child_count", 0)
        self.sibling_count: int = data.get("sibling_count", 0)
        self.dom_depth: int = data.get("dom_depth", 0)
        self.parent_tag: str = data.get("parent_tag", "")
        self.id_fragment: str = data.get("id_fragment", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "hierarchy": self.hierarchy,
            "text_len": self.text_len,
            "has_digits": self.has_digits,
            "has_currency": self.has_currency,
            "stable_attrib_keys": self.stable_attrib_keys,
            "attrib_count": self.attrib_count,
            "child_count": self.child_count,
            "sibling_count": self.sibling_count,
            "dom_depth": self.dom_depth,
            "parent_tag": self.parent_tag,
            "id_fragment": self.id_fragment,
        }

    @classmethod
    def from_element(cls, el: Element) -> "NodeFingerprint":
        raw = el._node
        text = el.text

        # Get ancestor hierarchy
        ancestors = []
        curr = raw.getparent()
        depth = 0
        while curr is not None:
            depth += 1
            ancestors.append(curr.tag.lower())
            curr = curr.getparent()
        hierarchy = ">".join(reversed(ancestors[-4:])) if ancestors else ""

        parent = raw.getparent()
        parent_tag = parent.tag.lower() if parent is not None else ""
        siblings = list(parent.iterchildren()) if parent is not None else []

        attrib_keys = [k for k in raw.attrib.keys() if k.startswith(("data-", "aria-", "itemprop", "role", "name"))]

        return cls({
            "tag": el.tag,
            "hierarchy": hierarchy,
            "text_len": len(text),
            "has_digits": bool(re.search(r"\d", text)),
            "has_currency": bool(re.search(r"[₹$€£¥]", text)),
            "stable_attrib_keys": sorted(attrib_keys),
            "attrib_count": len(raw.attrib),
            "child_count": len(list(raw.iterchildren())),
            "sibling_count": len(siblings),
            "dom_depth": depth,
            "parent_tag": parent_tag,
            "id_fragment": raw.attrib.get("id", "")[:12],
        })


class AdaptiveEngine:
    """Manages persistent selector fingerprints and computes multi-factor similarity relocation."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            cache_dir = Path.home() / ".omniscrape"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "fingerprints.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fingerprints (
                    domain TEXT,
                    name TEXT,
                    fingerprint TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (domain, name)
                )
            """)

    def save_fingerprint(self, domain: str, name: str, fp: NodeFingerprint):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                INSERT INTO fingerprints (domain, name, fingerprint)
                VALUES (?, ?, ?)
                ON CONFLICT(domain, name) DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    updated_at = CURRENT_TIMESTAMP
            """, (domain, name, json.dumps(fp.to_dict())))

    def load_fingerprint(self, domain: str, name: str) -> Optional[NodeFingerprint]:
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT fingerprint FROM fingerprints WHERE domain = ? AND name = ?", (domain, name)
            ).fetchone()
        return NodeFingerprint(json.loads(row[0])) if row else None

    def calculate_similarity(self, fp1: NodeFingerprint, fp2: NodeFingerprint) -> float:
        """Weighted similarity metric across 12 structural factors."""
        score = 0.0

        # Tag match (0.25)
        if fp1.tag == fp2.tag:
            score += 0.25

        # Parent tag match (0.15)
        if fp1.parent_tag == fp2.parent_tag:
            score += 0.15

        # Characteristic content flags (0.20)
        if fp1.has_currency == fp2.has_currency:
            score += 0.10
        if fp1.has_digits == fp2.has_digits:
            score += 0.10

        # Text length proximity (0.10)
        max_len = max(fp1.text_len, fp2.text_len, 1)
        len_diff = abs(fp1.text_len - fp2.text_len)
        score += max(0.0, 0.10 * (1.0 - len_diff / max_len))

        # DOM depth proximity (0.10)
        depth_diff = abs(fp1.dom_depth - fp2.dom_depth)
        score += max(0.0, 0.10 * (1.0 - depth_diff / 5.0))

        # Stable attribute key overlap (0.20)
        s1 = set(fp1.stable_attrib_keys)
        s2 = set(fp2.stable_attrib_keys)
        if s1 and s2:
            jaccard = len(s1 & s2) / len(s1 | s2)
            score += 0.20 * jaccard
        elif not s1 and not s2:
            score += 0.10

        return round(score, 3)

    def relocate(
        self,
        selector: Selector,
        stored_fp: NodeFingerprint,
        min_confidence: float = 0.70,
    ) -> Optional[Element]:
        """Scans DOM candidates and selects best matching node based on fingerprint."""
        candidates = selector.css(stored_fp.tag) or selector.css("*")
        best_candidate: Optional[Element] = None
        highest_score = -1.0

        for cand in candidates:
            cand_fp = NodeFingerprint.from_element(cand)
            sim = self.calculate_similarity(stored_fp, cand_fp)
            if sim > highest_score:
                highest_score = sim
                best_candidate = cand

        if best_candidate and highest_score >= min_confidence:
            logger.info(f"Self-healed element relocation matched with confidence {highest_score}")
            return best_candidate

        return None
