"""Markdown export (thin wrapper kept for backward compatibility; see omniscrape.content.markdown)."""

from typing import Any, Optional, Union

from omniscrape.content.markdown import fit_markdown, to_markdown
from omniscrape.content.markdown import html_to_markdown as _html_to_markdown

__all__ = ["html_to_markdown", "fit_markdown", "to_markdown"]


def html_to_markdown(html: Union[str, Any], max_tokens: Optional[int] = None, url: str = "",
                     main_content: bool = True, links: bool = True) -> str:
    """Clean Markdown for LLMs. By default only the main content (boilerplate removed)."""
    if main_content:
        return fit_markdown(html, url=url, links=links, images=False, max_tokens=max_tokens)
    return _html_to_markdown(html, url=url, links=links, max_tokens=max_tokens)
