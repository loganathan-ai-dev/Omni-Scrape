# Installation

OmniScrape requires **Python 3.11 or newer**.

```bash
pip install omni-scraper
```

> [!NOTE]
> The PyPI package is named **`omni-scraper`** (with a hyphen). The name `omniscrape` on PyPI belongs to an unrelated project, so `pip install omniscrape` installs the wrong thing. The import name and the command are still `omniscrape`:
>
> ```python
> import omniscrape
> ```
>
> ```bash
> omniscrape --version
> ```

## Optional extras

The base install covers HTTP fetching (tier 1), parsing, extraction, Markdown, the crawler and the CLI. Everything else is opt-in.

| Extra | Adds | Install |
|---|---|---|
| `browser` | Playwright Chromium rendering, actions, screenshots, PDF | `pip install "omni-scraper[browser]"` then `playwright install chromium` |
| `stealth` | Camoufox for opt-in stealth (`tier=3`) | `pip install "omni-scraper[stealth]"` |
| `fast` | Opt-in `selectolax` Lexbor CSS backend | `pip install "omni-scraper[fast]"` |
| `httpx` | Alternative HTTP/2 client (`tier="httpx"`) | `pip install "omni-scraper[httpx]"` |
| `storage` | DuckDB output | `pip install "omni-scraper[storage]"` |
| `markdown` | Exact token counts via `tiktoken` | `pip install "omni-scraper[markdown]"` |
| `mcp` | MCP server for AI agents | `pip install "omni-scraper[mcp]"` |
| `shell` | IPython for `omniscrape shell` | `pip install "omni-scraper[shell]"` |
| `all` | All of the above | `pip install "omni-scraper[all]"` |

Quote the requirement (`"omni-scraper[browser]"`) so your shell does not interpret the brackets.

## Browser rendering

Tier 2 (JavaScript rendering) uses Playwright. After installing the `browser` extra, download the browser once:

```bash
pip install "omni-scraper[browser]"
playwright install chromium
```

## From source

```bash
git clone https://github.com/loganathan-ai-dev/Omni-Scrape.git && cd Omni-Scrape
pip install -e ".[dev,browser,mcp,storage,fast]" && playwright install chromium
ruff check . && pytest
```

## Verify

```bash
omniscrape --version
omniscrape get https://books.toscrape.com/
```

Next: [[Quick-Start]]. Trouble? See [[FAQ-and-Troubleshooting]].
