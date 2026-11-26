"""Build adaptive-selector test cases: (original page, mutated page, selector, expected text).

For each product page, every target element (title, price, sku, stock) gets a "typical scraper"
CSS selector built from the original DOM. Seeded mutations then simulate site redesigns. A case
counts toward the score only if the original selector no longer returns the target on the
mutated page; the rest are reported as ``selector_still_works``.

Mutations:
  class_rename     every class token in the document is replaced (CSS-in-JS rebuild)
  wrapper_insert   targets wrapped in new <div>s; parent > child selectors break
  attr_churn       target + parent classes renamed, ids and data-* values changed
  sibling_insert   target class renamed; similar-looking distractor siblings inserted
  tag_change       target tag changed (span->div, h1->h2 ...) and its class renamed
  content_update   global class rename + target text changes (e.g. new price)
  combined         class_rename + wrapper_insert + attr_churn

Generated into benchmarks/corpus/data/adaptive/ (gitignored).
"""

import json
import random
from typing import Any, Optional

import lxml.html
from lxml.cssselect import CSSSelector

from benchmarks.common import CORPUS_DIR, load_corpus, norm_text, read_text

MUTATIONS = ["class_rename", "wrapper_insert", "attr_churn", "sibling_insert", "tag_change", "content_update", "combined"]
ADAPTIVE_DIR = CORPUS_DIR / "adaptive"
TAG_SWAP = {"span": "div", "div": "section", "h1": "h2", "h2": "h3", "p": "div", "font": "span", "small": "span",
            "b": "strong", "button": "a", "td": "td"}


def _rand_token(rng: random.Random) -> str:
    return "x" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(7))


def _sel_part(el: Any) -> str:
    tag = el.tag.lower()
    if el.get("id"):
        return f"{tag}#{el.get('id')}"
    classes = (el.get("class") or "").split()
    return f"{tag}.{classes[0]}" if classes else tag


def make_selector(root: Any, el: Any) -> Optional[str]:
    """Build a 'typical' scraper selector (parent > target, widened until unique)."""
    parts = [_sel_part(el)]
    node = el.getparent()
    for _ in range(4):
        if node is None:
            break
        parts.insert(0, _sel_part(node))
        sel = " > ".join(parts)
        try:
            found = CSSSelector(sel)(root)
        except Exception:
            return None
        if len(found) == 1 and found[0] is el:
            return sel
        node = node.getparent()
    return None


def find_target(root: Any, truth: dict[str, Any], target: dict[str, Any]) -> Optional[Any]:
    if target.get("selector"):
        found = CSSSelector(target["selector"])(root)
        return found[0] if found else None
    cls = truth["classes"][target["role"]]
    for el in root.iter():
        if isinstance(el.tag, str) and el.get("class") == cls and norm_text(el.text_content()) == norm_text(target["text"]):
            return el
    return None


def rename_all_classes(root: Any, rng: random.Random) -> None:
    mapping: dict[str, str] = {}
    for el in root.iter():
        if isinstance(el.tag, str) and el.get("class"):
            el.set("class", " ".join(mapping.setdefault(c, _rand_token(rng)) for c in el.get("class").split()))


def rename_classes(el: Any, rng: random.Random) -> None:
    if el.get("class"):
        el.set("class", " ".join(_rand_token(rng) for _ in el.get("class").split()))
    else:
        el.set("class", _rand_token(rng))


def churn_attrs(root: Any, rng: random.Random) -> None:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.get("id") and el.tag not in ("html", "body"):
            el.set("id", _rand_token(rng))
        for k in list(el.attrib):
            if k.startswith("data-"):
                el.set(k, _rand_token(rng))


def wrap(el: Any, rng: random.Random) -> None:
    parent = el.getparent()
    if parent is None:
        return
    wrapper = lxml.html.Element("div", {"class": _rand_token(rng)})
    idx = parent.index(el)
    tail, el.tail = el.tail, None
    parent.remove(el)
    wrapper.append(el)
    wrapper.tail = tail
    parent.insert(idx, wrapper)


def mutate_text(text: str, name: str, rng: random.Random) -> str:
    if name == "price":
        digits = [c for c in text if c.isdigit()]
        if digits:
            pos = max(i for i, c in enumerate(text) if c.isdigit() and i < len(text) - 1) if len(digits) > 1 else text.index(digits[0])
            return text[:pos] + str((int(text[pos]) + 3) % 10) + text[pos + 1:]
        return text + " (sale)"
    if name == "title":
        return text + " (2026 Edition)"
    if name == "stock":
        return "Only 3 left in stock"
    if name == "sku":
        return text[:-2] + "77" if len(text) > 2 else text + "7"
    return text + " updated"


def apply_mutation(html: str, truth: dict[str, Any], mutation: str, seed: int) -> tuple[str, dict[str, str]]:
    """Return mutated HTML and the expected text per target name."""
    rng = random.Random(seed)
    root = lxml.html.fromstring(html)
    targets = {name: find_target(root, truth, t) for name, t in truth["targets"].items()}
    targets = {k: v for k, v in targets.items() if v is not None}
    expected = {name: norm_text(el.text_content()) for name, el in targets.items()}

    if mutation in ("class_rename", "content_update", "combined"):
        rename_all_classes(root, rng)
    if mutation in ("wrapper_insert", "combined"):
        for el in targets.values():
            wrap(el, rng)
    if mutation in ("attr_churn", "combined"):
        churn_attrs(root, rng)
        for el in targets.values():
            rename_classes(el, rng)
            if el.getparent() is not None:
                rename_classes(el.getparent(), rng)
    if mutation == "sibling_insert":
        for name, el in targets.items():
            rename_classes(el, rng)
            parent = el.getparent()
            if parent is None:
                continue
            for _ in range(2):
                clone = lxml.html.fromstring(lxml.html.tostring(el))
                clone.text, clone.tail = mutate_text(el.text_content(), name, rng) + " (was)", None
                for child in list(clone):
                    clone.remove(child)
                rename_classes(clone, rng)
                parent.insert(rng.randint(0, len(parent)), clone)
    if mutation == "tag_change":
        for el in targets.values():
            el.tag = TAG_SWAP.get(el.tag, "div")
            rename_classes(el, rng)
    if mutation == "content_update":
        for name, el in targets.items():
            new_text = mutate_text(el.text_content().strip(), name, rng)
            for child in list(el):
                el.remove(child)
            el.text = new_text
            expected[name] = norm_text(new_text)
    return lxml.html.tostring(root, encoding="unicode", doctype="<!DOCTYPE html>"), expected


def build() -> dict[str, int]:
    ADAPTIVE_DIR.mkdir(parents=True, exist_ok=True)
    for p in ADAPTIVE_DIR.iterdir():
        p.unlink()
    pages = []
    stats = {"pages": 0, "cases": 0, "scored": 0}
    for i, doc in enumerate(d for d in load_corpus(kind="product") if d["truth"].get("targets")):
        html = read_text(doc["html_path"])
        root = lxml.html.fromstring(html)
        selectors = {}
        for name, target in doc["truth"]["targets"].items():
            el = find_target(root, doc["truth"], target)
            sel = target.get("selector") or (make_selector(root, el) if el is not None else None)
            if el is not None and sel:
                selectors[name] = sel
        if not selectors:
            continue
        variants = []
        for j, mutation in enumerate(MUTATIONS):
            mutated, expected = apply_mutation(html, doc["truth"], mutation, seed=i * 100 + j)
            mut_path = ADAPTIVE_DIR / f"{doc['id']}__{mutation}.html"
            mut_path.write_text(mutated, encoding="utf-8")
            mroot = lxml.html.fromstring(mutated)
            checks = {}
            for name, sel in selectors.items():
                found = CSSSelector(sel)(mroot)
                still_works = bool(found) and norm_text(found[0].text_content()) == expected.get(name)
                checks[name] = {"expected": expected.get(name, ""), "selector_still_works": still_works}
                stats["cases"] += 1
                stats["scored"] += 0 if still_works else 1
            variants.append({"mutation": mutation, "html_path": str(mut_path), "targets": checks})
        pages.append({"id": doc["id"], "split": doc["split"], "url": doc["truth"]["url"],
                      "html_path": doc["html_path"], "selectors": selectors,
                      "original_text": {n: norm_text(find_target(root, doc["truth"], doc["truth"]["targets"][n]).text_content()) for n in selectors},
                      "variants": variants})
        stats["pages"] += 1
    (ADAPTIVE_DIR / "cases.json").write_text(json.dumps(pages, indent=1), encoding="utf-8")
    return stats


if __name__ == "__main__":
    print(build())
