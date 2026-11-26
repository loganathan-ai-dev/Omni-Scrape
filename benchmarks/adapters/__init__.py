"""Tool registry: name -> (module, class, constructor kwargs, environment group)."""

from importlib import import_module
from typing import Any

from benchmarks.adapters.base import ToolAdapter

# env group: tools in one group share a virtualenv (only conflict-free libraries are grouped);
# every tool still runs in its own subprocess.
TOOLS: dict[str, dict[str, Any]] = {
    "omniscrape": {"module": "omniscrape_adapter", "cls": "OmniScrapeAdapter", "env": "omniscrape"},
    "lxml": {"module": "parsers_adapter", "cls": "LxmlAdapter", "env": "parsers"},
    "bs4-lxml": {"module": "parsers_adapter", "cls": "Bs4Adapter", "kwargs": {"parser": "lxml"}, "env": "parsers"},
    "bs4-html.parser": {"module": "parsers_adapter", "cls": "Bs4Adapter", "kwargs": {"parser": "html.parser"}, "env": "parsers"},
    "selectolax": {"module": "parsers_adapter", "cls": "SelectolaxAdapter", "env": "parsers"},
    "parsel": {"module": "parsers_adapter", "cls": "ParselAdapter", "env": "parsers"},
    "trafilatura": {"module": "parsers_adapter", "cls": "TrafilaturaAdapter", "env": "parsers"},
    "markdownify": {"module": "parsers_adapter", "cls": "MarkdownifyAdapter", "env": "parsers"},
    "html2text": {"module": "parsers_adapter", "cls": "Html2TextAdapter", "env": "parsers"},
    "scrapling": {"module": "scrapling_adapter", "cls": "ScraplingAdapter", "env": "scrapling"},
    "crawl4ai": {"module": "crawl4ai_adapter", "cls": "Crawl4AIAdapter", "env": "crawl4ai"},
    "crawl4ai-fit": {"module": "crawl4ai_adapter", "cls": "Crawl4AIAdapter", "kwargs": {"fit": True}, "env": "crawl4ai"},
    "scrapy": {"module": "scrapy_adapter", "cls": "ScrapyAdapter", "env": "scrapy"},
    "crawlee": {"module": "crawlee_adapter", "cls": "CrawleeAdapter", "env": "crawlee"},
}

# Which tools are compared in which suite (like-for-like only).
SUITE_TOOLS: dict[str, list[str]] = {
    "parse": ["omniscrape", "lxml", "bs4-lxml", "bs4-html.parser", "selectolax", "parsel", "scrapling"],
    "extract": ["omniscrape", "trafilatura"],
    "markdown": ["omniscrape", "trafilatura", "crawl4ai", "crawl4ai-fit", "markdownify", "html2text"],
    "adaptive": ["omniscrape", "scrapling"],
    "render": ["omniscrape", "crawl4ai", "scrapling"],
    "crawl": ["omniscrape", "scrapy", "crawlee", "scrapling", "crawl4ai"],
    "live": ["omniscrape", "scrapy", "crawlee", "scrapling"],
}


def load_adapter(tool: str) -> ToolAdapter:
    spec = TOOLS[tool]
    module = import_module(f"benchmarks.adapters.{spec['module']}")
    adapter = getattr(module, spec["cls"])(**spec.get("kwargs", {}))
    adapter.name = tool
    return adapter
