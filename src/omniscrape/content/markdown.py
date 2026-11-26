"""HTML -> Markdown on lxml (headings, lists, tables, code, quotes, links, images, citations).

* ``html_to_markdown(html, url)``  whole page, scripts/styles/hidden nodes removed
* ``fit_markdown(html, url)``      main content only (see content.extract), optionally filtered by a query
* ``to_markdown(node, ...)``       render any lxml element
"""

import copy
import re
from typing import Any, Optional, Union
from urllib.parse import urljoin

from omniscrape.parsers.structured import as_root

BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "aside", "nav", "h1", "h2", "h3", "h4",
         "h5", "h6", "ul", "ol", "li", "pre", "blockquote", "table", "figure", "figcaption", "hr", "dl", "dt", "dd",
         "form", "fieldset", "details", "summary", "address", "center", "body", "html", "tr", "thead", "tbody",
         "tfoot", "caption", "noscript", "menu", "hgroup", "search"}
SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object", "embed", "head", "title",
        "button", "input", "select", "textarea", "option", "link", "meta", "map"}
_SPACES = re.compile(r"[ \t\r\f\v ]+")
_LANG = re.compile(r"(?:lang(?:uage)?-|highlight-(?:source-)?)([\w+#.-]+)", re.IGNORECASE)


class MarkdownRenderer:
    def __init__(self, base_url: str = "", links: bool = True, images: bool = True, citations: bool = False,
                 tables: bool = True):
        self.base_url = base_url
        self.links = links
        self.images = images
        self.citations = citations
        self.tables = tables
        self.refs: list[str] = []
        self._ref_index: dict[str, int] = {}

    # ------------------------------------------------------------------ public
    def render(self, node: Any) -> str:
        md = self.container(node)
        md = re.sub(r"[ \t]+\n", "\n", md)
        md = re.sub(r"\n{3,}", "\n\n", md).strip()
        if self.citations and self.refs:
            md += "\n\n## References\n\n" + "\n".join(f"[{i}]: {u}" for i, u in enumerate(self.refs, 1))
        return md

    # ------------------------------------------------------------------ blocks
    def container(self, el: Any, tight: bool = False) -> str:
        parts: list[str] = []
        buf: list[str] = [el.text or ""]

        def flush() -> None:
            text = self._clean_inline("".join(buf))
            if text:
                parts.append(text)
            buf.clear()

        for child in el:
            if not isinstance(child.tag, str):
                buf.append(child.tail or "")
                continue
            tag = child.tag.lower()
            if tag in SKIP:
                pass
            elif tag in BLOCK:
                flush()
                block = self.block(child)
                if block.strip():
                    parts.append(block)
            else:
                buf.append(self.inline(child))
            buf.append(child.tail or "")
        flush()
        return ("\n" if tight else "\n\n").join(parts)

    def block(self, el: Any) -> str:
        tag = el.tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = self._clean_inline(self.inline_children(el)).replace("\n", " ")
            return f"{'#' * int(tag[1])} {text}" if text else ""
        if tag == "p":
            return self._clean_inline(self.inline_children(el))
        if tag == "pre":
            return self.code_block(el)
        if tag == "blockquote":
            inner = self.container(el)
            return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
        if tag in ("ul", "ol", "menu"):
            return self.list_block(el, ordered=tag == "ol")
        if tag == "table":
            return self.table(el) if self.tables else self.container(el)
        if tag == "hr":
            return "---"
        if tag == "dt":
            text = self._clean_inline(self.inline_children(el))
            return f"**{text}**" if text else ""
        if tag == "dd":
            return self.container(el)
        if tag == "figcaption":
            text = self._clean_inline(self.inline_children(el))
            return f"*{text}*" if text else ""
        return self.container(el)

    def code_block(self, el: Any) -> str:
        code_el = el.find(".//code")
        hint = f"{el.get('class', '')} {code_el.get('class', '') if code_el is not None else ''}"
        lang_match = _LANG.search(hint)
        lang = lang_match.group(1) if lang_match else ""
        code = el.text_content().strip("\n")
        fence = "````" if "```" in code else "```"
        return f"{fence}{lang}\n{code}\n{fence}"

    def list_block(self, el: Any, ordered: bool) -> str:
        items = []
        start = int(el.get("start", "1")) if (el.get("start") or "").isdigit() else 1
        n = start
        for li in el:
            if not isinstance(li.tag, str) or li.tag.lower() != "li":
                continue
            marker = f"{n}. " if ordered else "- "
            body = self.container(li, tight=True).strip()
            if not body:
                continue
            pad = " " * len(marker)
            lines = body.split("\n")
            items.append(marker + lines[0] + "".join(f"\n{pad}{line}" if line else "\n" for line in lines[1:]))
            n += 1
        return "\n".join(items)

    def table(self, el: Any) -> str:
        rows = []
        for tr in el.iter("tr"):
            # skip rows of nested tables (they belong to an inner cell)
            if next((a for a in tr.iterancestors("table")), None) is not el:
                continue
            cells = [self._clean_inline(self.inline_children(c)).replace("\n", " ").replace("|", "\\|")
                     for c in tr if isinstance(c.tag, str) and c.tag.lower() in ("td", "th")]
            if any(cells):
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        if width == 1:  # layout table: render as paragraphs
            return "\n\n".join(r[0] for r in rows if r[0])
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join([" --- "] * width) + "|"]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join(lines)

    # ------------------------------------------------------------------ inline
    def inline_children(self, el: Any) -> str:
        out = [el.text or ""]
        for child in el:
            if isinstance(child.tag, str) and child.tag.lower() not in SKIP:
                if child.tag.lower() in BLOCK:
                    out.append("\n" + self.block(child) + "\n")
                else:
                    out.append(self.inline(child))
            out.append(child.tail or "")
        return "".join(out)

    def inline(self, el: Any) -> str:
        tag = el.tag.lower()
        if tag in SKIP:
            return ""
        if tag == "br":
            return "\n"
        if tag == "img":
            if not self.images:
                return ""
            src = el.get("src") or el.get("data-src") or ""
            if not src or src.startswith("data:"):
                return ""
            return f"![{_SPACES.sub(' ', el.get('alt', '')).strip()}]({urljoin(self.base_url, src)})"
        text = self.inline_children(el)
        if tag == "a":
            href = (el.get("href") or "").strip()
            label = _SPACES.sub(" ", text).strip()
            if not self.links or not href or href.startswith(("javascript:", "#", "mailto:", "tel:")) or not label:
                return text
            url = urljoin(self.base_url, href)
            if self.citations:
                if url not in self._ref_index:
                    self.refs.append(url)
                    self._ref_index[url] = len(self.refs)
                return f"{label} [{self._ref_index[url]}]"
            return f"[{label}]({url})"
        stripped = text.strip()
        if not stripped:
            return text
        lead = " " if text[:1].isspace() else ""
        trail = " " if text[-1:].isspace() else ""
        if tag in ("strong", "b"):
            return f"{lead}**{stripped}**{trail}"
        if tag in ("em", "i", "cite", "dfn"):
            return f"{lead}*{stripped}*{trail}"
        if tag in ("code", "kbd", "samp", "tt"):
            return f"{lead}`{stripped}`{trail}"
        if tag in ("del", "s", "strike"):
            return f"{lead}~~{stripped}~~{trail}"
        return text

    @staticmethod
    def _clean_inline(text: str) -> str:
        lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
        out, blank = [], False
        for line in lines:
            if line:
                out.append(line)
                blank = False
            elif not blank and out:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def to_markdown(node: Any, base_url: str = "", links: bool = True, images: bool = True, citations: bool = False,
                tables: bool = True) -> str:
    return MarkdownRenderer(base_url, links=links, images=images, citations=citations, tables=tables).render(node)


def html_to_markdown(html: Union[str, Any], url: str = "", links: bool = True, images: bool = True,
                     citations: bool = False, max_tokens: Optional[int] = None) -> str:
    """Whole-page Markdown (scripts, styles and hidden elements removed)."""
    root = copy.deepcopy(as_root(html)) if not isinstance(html, (str, bytes)) else as_root(html)
    for el in list(root.iter()):
        if el.getparent() is None:
            continue
        if not isinstance(el.tag, str) or el.tag.lower() in SKIP or el.get("hidden") is not None \
                or el.get("aria-hidden") == "true":
            el.drop_tree()
    body = root.find(".//body")
    md = to_markdown(body if body is not None else root, url, links=links, images=images, citations=citations)
    return truncate_tokens(md, max_tokens) if max_tokens else md


def fit_markdown(html: Union[str, Any], url: str = "", query: Optional[str] = None, links: bool = False,
                 images: bool = False, citations: bool = False, title: bool = True,
                 max_tokens: Optional[int] = None, main: Optional[Any] = None) -> str:
    """Main-content Markdown: boilerplate removed, minimal tokens. Optional BM25 filtering by ``query``."""
    from omniscrape.content.extract import extract_main

    main = main if main is not None else extract_main(html, url)
    md = to_markdown(main.node, url, links=links, images=images, citations=citations)
    if title and main.title and main.title.casefold() not in md[:500].casefold():
        md = f"# {main.title}\n\n{md}"
    if query:
        from omniscrape.content.filters import bm25_filter_markdown

        md = bm25_filter_markdown(md, query)
    return truncate_tokens(md, max_tokens) if max_tokens else md


def truncate_tokens(md: str, max_tokens: int) -> str:
    from omniscrape.content.tokens import count_tokens, truncate_to_tokens

    if count_tokens(md) <= max_tokens:
        return md
    return truncate_to_tokens(md, max_tokens) + "\n\n... [truncated]"
