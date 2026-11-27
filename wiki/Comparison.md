# How OmniScrape Compares

Cells come from each project's own README or documentation, read on 2026-11-27. `—` means the page does not state it, which is not the same as "no". Corrections welcome via an issue.

| | **OmniScrape** | [Scrapling](https://github.com/D4Vinci/Scrapling) | [Crawl4AI](https://github.com/unclecode/crawl4ai) | [Scrapy](https://github.com/scrapy/scrapy) | [Crawlee (Python)](https://github.com/apify/crawlee-python) | [Trafilatura](https://github.com/adbar/trafilatura) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Async API | ✅ | ✅ | ✅ | engine only | ✅ | — |
| HTTP with TLS/browser impersonation | ✅ 6 browser families, rotation, HTTP/3 | ✅ incl. HTTP/3 | — | — | — | — |
| Real-browser rendering | ✅ | ✅ | ✅ | — | ✅ | — |
| Stealth / anti-bot fetcher | ◐ no challenge solving | ✅ claims Turnstile bypass | ✅ stealth mode | — | — | — |
| Adaptive / self-healing selectors | ✅ | ✅ | — | — | — | — |
| CSS and XPath | ✅ | ✅ | ✅ | ✅ | — | — |
| Spider with concurrency | ✅ | ✅ | ✅ deep crawl | ✅ | ✅ | ◐ |
| Pause / resume | ✅ | ✅ | ◐ crash recovery | — | ◐ persisted queue | — |
| `robots.txt` | ✅ on by default | ✅ opt-in | — | ✅ | — | — |
| Proxy rotation | ✅ | ✅ | ✅ | — | ✅ | — |
| CLI | ✅ | ✅ | ✅ | ✅ | scaffolding only | ✅ |
| Interactive shell | ✅ with curl import | ✅ | — | ✅ | — | — |
| MCP server | ✅ 11 tools | ✅ | ✅ | — | — | — |
| LLM-ready Markdown | ✅ | ✅ | ✅ | — | — | ✅ |
| Zero-config extraction: products, articles | ✅ | — | — | — | — | ✅ articles only |
| Zero-config extraction: recipes, events, jobs, reviews, FAQ, contacts, breadcrumbs, pagination | ✅ | — | — | — | — | — |
| Page-type detection | ✅ | — | — | — | — | — |
| Several fetcher types in one spider | ✅ named sessions | ✅ | — | — | — | — |
| Agent skill | ✅ | ✅ | — | — | — | — |
| License | MIT | BSD-3 | Apache-2.0 | BSD-3 | Apache-2.0 | Apache-2.0 |

**Where OmniScrape is behind today:** light browser stealth patches (no browser fingerprint randomisation) and no Cloudflare challenge solving, which this project deliberately does not build; no LLM-based extraction. Scrapling ships a more mature anti-bot story; if Turnstile bypass is your main need, use it.

See also: [[Benchmarks]], [[Fetching-and-Stealth]], [[Selectors-and-Extraction]].
