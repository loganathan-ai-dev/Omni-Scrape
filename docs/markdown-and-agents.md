# LLM Markdown, CLI & AI Agent Skills

OmniScrape includes a noise-free Markdown pipeline, a terminal CLI, a built-in FastMCP server, and ready-to-use agent skills.

---

## LLM-Ready Markdown & Chunking

```python
from omniscrape import chunk_markdown, extract_main, fit_markdown, html_to_markdown

# Main content only (boilerplate, navs, sidebars, cookie banners stripped)
md = fit_markdown(
    html,
    url="https://example.com/docs",
    query="rate limits pricing",  # optional BM25 relevance filter
    links=True,                   # keep hyperlinks (off by default); required for citations
    citations=True,               # appends numbered [1]: URL references
    max_tokens=2000,              # uses tiktoken when [markdown] extra is installed
)

# Split into heading-aware retrieval chunks
chunks = chunk_markdown(md, max_tokens=512, overlap_blocks=0)
for c in chunks:
    print(c.headings, c.tokens, c.text[:100])
```

- `omniscrape.html_to_markdown(html, max_tokens=None, url="", main_content=True, links=True)` converts to Markdown; it isolates the main content by default (`main_content=False` keeps the whole page). The lower-level `omniscrape.content.markdown.html_to_markdown(html, url="", links=True, images=True, citations=False, max_tokens=None)` always converts the whole HTML.
- Use `extract_main(html, url)` to inspect the selected main DOM node and page title directly.

---

## Command-Line Interface

```bash
# Rich summary table
omniscrape get https://books.toscrape.com/

# Clean main-content Markdown
omniscrape get https://books.toscrape.com/ -f markdown

# Full ScrapeResult JSON + force browser tier (data on stdout, logs on stderr)
omniscrape get https://example.com/app -f json --tier 2 > page.json

# Just the text of a CSS selector, with a header and a proxy
omniscrape get https://example.com --css "h1" -H "Accept-Language: en" --proxy http://p:8080

# Crawl a site into JSONL (or .duckdb), resumable, robots.txt obeyed
omniscrape crawl https://books.toscrape.com/ --max-pages 100 -o books.jsonl --resume

# List a site's URLs, ranked by relevance to a search
omniscrape map https://example.com --search pricing

# Extract fields with a JSON schema of CSS selectors
omniscrape extract https://example.com --schema schema.json

# Interactive REPL with `page` (Selector) and `response` (FetchResult) preloaded
omniscrape shell https://example.com
```

`schema.json` is a `Selector.extract` schema, for example
`{"title": "h1::text", "price": {"selector": ".price::text", "type": "price"}}`.

---

## MCP Server (`omniscrape mcp`)

Install the optional MCP dependency and start the server over `stdio` or streamable HTTP:

```bash
pip install "omni-scraper[mcp]"
omniscrape mcp                              # stdio (Claude Desktop, Antigravity, Cursor)
omniscrape mcp --transport http --port 8000 # HTTP at http://127.0.0.1:8000/mcp
```

Exposed tools:
- `scrape_url(url, allow_stealth=False)` — Returns JSON with title, Markdown, product/article, metadata, and links (raw HTML excluded to save tokens).
- `scrape_product(url)` — Extracts `Product` fields.
- `scrape_article(url)` — Extracts `Article` fields.
- `get_markdown(url, query=None, max_tokens=None, allow_stealth=False)` — Main-content Markdown with optional BM25 filtering and token cap; returns an `Error: ... HTTP <status>` message instead of Markdown for failed or blocked pages.
- `map_site(url, search=None, limit=200)` — Sitemap + link URL discovery.

---

## Agent & Claude Skills

This repository ships matching project skills so coding agents automatically know OmniScrape's APIs and best practices:

- **Antigravity / universal `.agents` skill**: [`SKILL.md`](../.agents/skills/omniscrape/SKILL.md) and [`api_cheatsheet.md`](../.agents/skills/omniscrape/references/api_cheatsheet.md)
- **Claude Code skill**: [`SKILL.md`](../.claude/skills/omniscrape/SKILL.md) and [`api_cheatsheet.md`](../.claude/skills/omniscrape/references/api_cheatsheet.md)
- **Claude Code plugin**: `/plugin marketplace add loganathan-ai-dev/Omni-Scrape` then `/plugin install omniscrape@omni-scraper` (bundles the skill and an MCP server entry; install `omni-scraper[mcp]` first).

The two skill folders are kept identical: edit `.agents/skills/omniscrape/` and run `python scripts/sync_skills.py`.
