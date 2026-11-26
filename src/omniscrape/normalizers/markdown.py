"""Token-optimized clean Markdown exporter for LLM agent feeding."""

import re
from typing import Optional
from bs4 import BeautifulSoup


def html_to_markdown(html: str, max_tokens: Optional[int] = None) -> str:
    """Converts HTML to clean, boilerplate-stripped Markdown."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for el in soup.find_all(["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "iframe"]):
        el.decompose()

    # Convert headers
    for i in range(1, 7):
        for h in soup.find_all(f"h{i}"):
            h.replace_with(f"\n{'#' * i} {h.get_text().strip()}\n")

    # Convert links
    for a in soup.find_all("a", href=True):
        text = a.get_text().strip()
        if text:
            a.replace_with(f"[{text}]({a['href']})")

    # Convert paragraphs
    for p in soup.find_all("p"):
        p.replace_with(f"\n{p.get_text().strip()}\n")

    # Convert list items
    for li in soup.find_all("li"):
        li.replace_with(f"\n- {li.get_text().strip()}")

    raw_text = soup.get_text()
    # Normalize multiple newlines
    cleaned = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    if max_tokens:
        # Approximate 4 characters per token
        char_limit = max_tokens * 4
        if len(cleaned) > char_limit:
            cleaned = cleaned[:char_limit] + "\n\n... [truncated]"

    return cleaned
