## OmniScrape 0.1.0

First public release. Install with `pip install omni-scraper` (the PyPI name is `omni-scraper`; you still
`import omniscrape` and run `omniscrape`).

### Highlights
- **Three-tier fetching**: `curl_cffi` HTTP with a browser TLS fingerprint, Playwright rendering, and an opt-in stealth tier.
- **Self-healing selectors** that relocate elements after class renames, tag swaps, wrappers and attribute churn.
- **Zero-config extraction** of products, articles and listing cards, plus LLM-ready Markdown.
- **Polite, resumable crawler** with `robots.txt` (including `*`/`$` wildcards), throttling and SQLite pause/resume.
- **CLI** (`get`, `crawl`, `map`, `extract`, `shell`, `mcp`), an **MCP server**, an **agent skill** and a Claude Code plugin.

### Benchmarks
Measured on 2026-11-27 against Scrapling 0.5.1 and Trafilatura 2.4.0 (raw data in `benchmarks/published/`):
100% selector recovery on 1,377 self-generated broken cases (Scrapling 85.3%), 387.7 vs 294.9 pages/s parsing,
175.3 vs 158.2 pages/s on a local crawl, Markdown F1 0.9903 vs 0.9807. Scrapling was faster on one of the two
live crawls. See the README for methodology and caveats.

### Known limitations
- One TLS impersonation profile (no rotation); light browser stealth patches; no Cloudflare challenge solving.
- No multi-session spider object; no LLM-based extraction.
- `mypy` reports some typing issues (advisory in CI).

Full list of changes: [CHANGELOG.md](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/CHANGELOG.md).
