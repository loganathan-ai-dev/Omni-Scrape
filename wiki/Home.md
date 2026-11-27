<p align="center">
  <img src="https://raw.githubusercontent.com/loganathan-ai-dev/Omni-Scrape/main/docs/assets/logo-mark.png" width="140">
</p>

# OmniScrape

**Adaptive web scraping for Python.** OmniScrape gives you tiered HTTP / browser / stealth fetching, self-healing selectors, zero-config product and article extraction, LLM-ready Markdown, a polite resumable crawler, a CLI and an MCP server, all behind one small API.

```bash
pip install omni-scraper
```

```python
import omniscrape

page = omniscrape.scrape_sync("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
print(page.title)                        # page title
print(page.product.title, page.product.price, page.product.currency)
print(page.markdown[:200])               # main content only, as Markdown
```

> [!NOTE]
> The PyPI package is named `omni-scraper`, but you `import omniscrape` and run the `omniscrape` command. See [[Installation]].

## Contents

| Page | What it covers |
|---|---|
| [[Installation]] | `pip install`, optional extras, Playwright, installing from source |
| [[Quick-Start]] | Scrape a page, batch scrape, extract fields, crawl a site |
| [[Fetching-and-Stealth]] | Fetcher tiers, retries, proxies, browser actions, custom fetchers |
| [[Selectors-and-Extraction]] | CSS/XPath, schemas, self-healing selectors, product/article/listing extraction |
| [[Crawling-and-Storage]] | `Spider`, `CrawlEngine`, politeness, pause/resume, JSONL and DuckDB |
| [[Markdown-and-Agents]] | `fit_markdown`, chunking, CLI and MCP overview, agent skills |
| [[CLI-Reference]] | Every `omniscrape` command and flag |
| [[MCP-Server]] | The five MCP tools, transports, Claude Code and Claude Desktop setup |
| [[Benchmarks]] | Published benchmark results, methodology and how to reproduce |
| [[Comparison]] | Feature comparison with Scrapling, Crawl4AI, Scrapy, Crawlee and Trafilatura |
| [[FAQ-and-Troubleshooting]] | Common problems and fixes |
| [[Contributing]] | Dev setup and contribution guidelines |
