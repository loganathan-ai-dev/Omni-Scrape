## OmniScrape 0.1.0

First public release. Install with `pip install omni-scraper` (the PyPI name is `omni-scraper`; you still
`import omniscrape` and run `omniscrape`).

### Highlights
- **Zero-config extraction for every common page type**: products, articles, listings, recipes, events, job postings,
  reviews and ratings, FAQs, organisation contacts, breadcrumbs, next-page links and data tables, plus
  page-type detection on every `scrape()` result.
- **Three-tier fetching**: `curl_cffi` HTTP that impersonates Chrome, Edge, Safari, Firefox, Android or iOS end to end
  (TLS fingerprint and matching headers, with rotation and HTTP/3), Playwright rendering, and an opt-in stealth tier.
- **Self-healing selectors** that relocate elements after class renames, tag swaps, wrappers and attribute churn.
- **Polite, resumable crawler** with `robots.txt` (including `*`/`$` wildcards), throttling, SQLite pause/resume and
  multi-session spiders that mix HTTP and browser pages in one crawl.
- **CLI** (`get`, `crawl`, `map`, `extract`, `curl`, `shell`, `mcp`), an **MCP server with 11 tools**, an **agent skill**
  and a Claude Code plugin. Replay any browser "Copy as cURL" request with `omniscrape curl` or `fetch_curl`.

### Benchmarks
Measured on 2026-11-27 against Scrapling 0.5.1 and Trafilatura 2.4.0 (raw data in
`benchmarks/published/2026-11-27-release/`): 100% selector recovery on 1,377 self-generated broken cases
(Scrapling 85.3%) at 31.0 vs 82.1 ms per page, 474.6 vs 338.1 pages/s parsing, 178.5 vs 167.6 pages/s on a local
crawl, 10.2 vs 5.5 pages/s JavaScript rendering, Markdown F1 0.9903 vs 0.9807 (Trafilatura). Scrapling was slightly
faster on one of the two live crawls and the other was a tie. See the README for methodology and caveats.

### Known limitations
- Light browser stealth patches (no browser fingerprint randomisation); no Cloudflare challenge solving, by design.
- No LLM-based extraction.
- `mypy` reports some typing issues (advisory in CI).

Full list of changes: [CHANGELOG.md](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/CHANGELOG.md).
