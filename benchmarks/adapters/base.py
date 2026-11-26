"""Uniform adapter interface. Each method is optional; ``suites`` declares what a tool supports."""

import re
from importlib import metadata
from typing import Any, Optional

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def html_title(html: str) -> str:
    m = TITLE_RE.search(html or "")
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


class ToolAdapter:
    name: str = "tool"
    package: str = ""  # distribution name used for the version string
    suites: frozenset[str] = frozenset()

    def version(self) -> str:
        try:
            return metadata.version(self.package) if self.package else ""
        except metadata.PackageNotFoundError:
            return "unknown"

    def prepare(self) -> None:
        """Import heavy modules here so import cost is excluded from timings."""

    # parse suite: one list of element texts per selector
    def select_texts(self, html: str, selectors: list[str]) -> list[list[str]]:
        raise NotImplementedError

    # extract suite: zero-config field extraction; kind is "product" or "article"
    def extract(self, html: str, url: str, kind: str) -> dict[str, Any]:
        raise NotImplementedError

    # markdown suite
    def markdown(self, html: str, url: str) -> str:
        raise NotImplementedError

    # adaptive suite
    def adaptive_save(self, html: str, url: str, selectors: dict[str, str], storage_dir: str) -> None:
        raise NotImplementedError

    def adaptive_find(self, html: str, url: str, selectors: dict[str, str], storage_dir: str) -> dict[str, Optional[str]]:
        raise NotImplementedError

    # render suite: load JS-rendered pages in a browser; return [{"url", "status", "html"}]
    def render(self, urls: list[str], concurrency: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    # crawl + live suites: return [{"url", "status", "title"}]
    def crawl(self, start_url: str, max_pages: int, concurrency: int, obey_robots: bool, workdir: str) -> list[dict[str, Any]]:
        raise NotImplementedError
