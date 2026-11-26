"""OmniScrape benchmark harness.

Compares OmniScrape against other scraping tools on reproducible suites:

* parse     - CSS selection speed + memory (parsers only)
* extract   - zero-config metadata extraction accuracy (field F1)
* markdown  - main-content Markdown quality (token F1, boilerplate leakage)
* adaptive  - selector recovery after DOM mutations
* crawl     - local test site: throughput, coverage, robots compliance, retries
* live      - polite crawl of public scraping sandboxes (toscrape.com)

Run ``python -m benchmarks --help``. This package must not import omniscrape or any tool at
module level: workers run inside each tool's isolated environment.
"""
