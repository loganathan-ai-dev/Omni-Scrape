# OmniScrape

Universal dynamic web scraping framework in Python.

## Key Features
- **3-Tier Fetcher Engine**: Fast HTTP/2 with TLS impersonation (`curl_cffi`), Headless JS rendering (`playwright`), and Stealth Anti-bot evasion (`camoufox`).
- **Dynamic Page Classifier**: Auto-probes target URLs to detect static pages, SPAs, and anti-bot defenses (Cloudflare, Turnstile, DataDome, Akamai).
- **Self-Healing Adaptive Selectors**: 12-factor structural fingerprinting relocates target elements even when websites alter classes and markup.
- **Zero-Config Semantic Extraction**: Automatically extracts JSON-LD, Microdata, OpenGraph, and main body text without manual selectors.
- **Data Normalizers**: Multi-currency, unit, date, and token-optimized Markdown export for LLMs.
- **Async Crawler & Storage**: Concurrency controller with AutoThrottle, crash-resilient checkpoints, and pluggable DuckDB / PostgreSQL / Parquet persistence.
- **Built-in MCP Server**: Native integration for AI agents and developer tooling.
