# How OmniScrape Compares

Cells come from each project's own README or documentation, read on 2026-11-27. `—` means the page does not state it, which is not the same as "no". Corrections welcome via an issue.

| | **OmniScrape** | [Scrapling](https://github.com/D4Vinci/Scrapling) | [Crawl4AI](https://github.com/unclecode/crawl4ai) | [Scrapy](https://github.com/scrapy/scrapy) | [Crawlee (Python)](https://github.com/apify/crawlee-python) | [Trafilatura](https://github.com/adbar/trafilatura) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Async API | ✅ | ✅ | ✅ | engine only | ✅ | — |
| HTTP with TLS/browser impersonation | ✅ one profile | ✅ incl. HTTP/3 | — | — | — | — |
| Real-browser rendering | ✅ | ✅ | ✅ | — | ✅ | — |
| Stealth / anti-bot fetcher | ◐ no challenge solving | ✅ claims Turnstile bypass | ✅ stealth mode | — | — | — |
| Adaptive / self-healing selectors | ✅ | ✅ | — | — | — | — |
| CSS and XPath | ✅ | ✅ | ✅ | ✅ | — | — |
| Spider with concurrency | ✅ | ✅ | ✅ deep crawl | ✅ | ✅ | ◐ |
| Pause / resume | ✅ | ✅ | ◐ crash recovery | — | ◐ persisted queue | — |
| `robots.txt` | ✅ on by default | ✅ opt-in | — | ✅ | — | — |
| Proxy rotation | ✅ | ✅ | ✅ | — | ✅ | — |
| CLI | ✅ | ✅ | ✅ | ✅ | scaffolding only | ✅ |
| Interactive shell | ✅ | ✅ | — | ✅ | — | — |
| MCP server | ✅ | ✅ | ✅ | — | — | — |
| LLM-ready Markdown | ✅ | ✅ | ✅ | — | — | ✅ |
| Zero-config product / article extraction | ✅ | — | — | — | — | ✅ articles only |
| Several fetcher types in one spider | ◐ per-request `tier` | ✅ | — | — | — | — |
| Agent skill | ✅ | ✅ | — | — | — | — |
| License | MIT | BSD-3 | Apache-2.0 | BSD-3 | Apache-2.0 | Apache-2.0 |

**Where OmniScrape is behind today:** a single TLS impersonation profile (no rotation, no HTTP/3), light browser stealth patches (no fingerprint randomisation, no Cloudflare challenge solving), no multi-session spider object, and no LLM-based extraction. Scrapling ships a more mature anti-bot story; if Turnstile bypass is your main need, use it.

For measured numbers rather than feature checkboxes, see [[Benchmarks]].
