"""Text-to-Tag ratio and DOM subtree frequency analyzer."""

import re
from typing import Any
import lxml.html
from omniscrape.parsers.selector import Element


class DensityAnalyzer:
    """Identifies primary article body or repeated product card grids via layout heuristics."""

    def __init__(self, html: str):
        try:
            parser = lxml.html.HTMLParser(encoding="utf-8")
            if isinstance(html, str):
                self.root = lxml.html.fromstring(html.encode("utf-8"), parser=parser)
            else:
                self.root = lxml.html.fromstring(html, parser=parser)
        except Exception:
            self.root = lxml.html.fromstring("<html><body></body></html>")

    def extract_main_content(self) -> str:
        """Finds the densest readable content node using Text-to-Tag Ratio (TTR)."""
        best_node = None
        best_score = -1.0

        for node in self.root.iter():
            if not isinstance(node, lxml.html.HtmlElement):
                continue
            tag = node.tag.lower()
            if tag in ("script", "style", "nav", "footer", "header", "noscript"):
                continue

            text = (node.text_content() or "").strip()
            text_len = len(text)
            if text_len < 100:
                continue

            children = list(node.iterchildren())
            child_count = max(1, len(children))
            link_text_len = sum(len((a.text_content() or "").strip()) for a in node.xpath(".//a"))
            link_density = link_text_len / max(1, text_len)

            # Heavily penalize navigation/footer blocks with high link ratio
            if link_density > 0.4:
                continue

            score = (text_len / child_count) * (1.0 - link_density)
            if tag in ("article", "main"):
                score *= 1.5

            if score > best_score:
                best_score = score
                best_node = node

        if best_node is not None:
            return (best_node.text_content() or "").strip()
        return ""

    def detect_repeated_cards(self, min_repetition: int = 3) -> list[Element]:
        """Detects repeated grid containers (e.g. product cards or search results)."""
        fingerprints: dict[str, list[lxml.html.HtmlElement]] = {}

        for node in self.root.xpath("//div | //li | //article | //section"):
            if not isinstance(node, lxml.html.HtmlElement):
                continue

            children = [c for c in node.iterchildren() if isinstance(c, lxml.html.HtmlElement)]
            if len(children) < 2:
                continue

            # Subtree tag sequence signature
            sig = "-".join([c.tag.lower() for c in children[:5]])
            if sig not in fingerprints:
                fingerprints[sig] = []
            fingerprints[sig].append(node)

        # Find largest cluster with >= min_repetition
        best_cluster: list[lxml.html.HtmlElement] = []
        for cluster in fingerprints.values():
            if len(cluster) >= min_repetition and len(cluster) > len(best_cluster):
                best_cluster = cluster

        return [Element(el) for el in best_cluster]
