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
    citations=True,               # appends numbered [1]: URL references
    max_tokens=2000,              # uses tiktoken when [markdown] extra is installed
)

# Split into heading-aware retrieval chunks
chunks = chunk_markdown(md, max_tokens=512, overlap_blocks=0)
for c in chunks:
    print(c.headings, c.tokens, c.text[:100])
```

- Use `html_to_markdown(html, url)` when you want the whole page rendered cleanly instead of main-content isolation.
- Use `extract_main(html, url)` to inspect the selected main DOM node and page title directly.

---

## Command-Line Interface

```bash
# Rich summary table
omniscrape get https://books.toscrape.com/

# Clean main-content Markdown
omniscrape get https://books.toscrape.com/ -f markdown

# Full ScrapeResult JSON + force browser tier
omniscrape get https://example.com/app -f json --tier 2
```

---

## MCP Server (`omniscrape mcp`)

Install the optional MCP dependency and start the server over `stdio` or streamable HTTP:

```bash
pip install "omniscrape[mcp]"
omniscrape mcp                              # stdio (Claude Desktop, Antigravity, Cursor)
omniscrape mcp --transport http --port 8000 # HTTP at http://127.0.0.1:8000/mcp
```

Exposed tools:
- `scrape_url(url, allow_stealth=False)` — Returns JSON with title, Markdown, product/article, metadata, and links (raw HTML excluded to save tokens).
- `scrape_product(url)` — Extracts `Product` fields.
- `scrape_article(url)` — Extracts `Article` fields.
- `get_markdown(url, query=None, max_tokens=None)` — Main-content Markdown with optional BM25 filtering and token cap.
- `map_site(url, search=None, limit=200)` — Sitemap + link URL discovery.

---

## Agent & Claude Skills

This repository ships matching project skills so coding agents automatically know OmniScrape's APIs and best practices:

- **Antigravity / universal `.agents` skill**: [`SKILL.md`](../.agents/skills/omniscrape/SKILL.md) and [`api_cheatsheet.md`](../.agents/skills/omniscrape/references/api_cheatsheet.md)
- **Claude Code skill**: [`SKILL.md`](../.claude/skills/omniscrape/SKILL.md) and [`api_cheatsheet.md`](../.claude/skills/omniscrape/references/api_cheatsheet.md)
