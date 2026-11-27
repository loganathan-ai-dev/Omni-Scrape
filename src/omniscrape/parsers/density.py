"""Text-to-Tag ratio and DOM subtree frequency analyzer."""

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
