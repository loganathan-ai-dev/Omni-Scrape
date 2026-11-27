# Installation

OmniScrape requires **Python 3.11 or newer**.

```bash
pip install omni-scrape
```

> [!NOTE]
> The PyPI package is named **`omni-scrape`** (with a hyphen). The name `omniscrape` on PyPI belongs to an unrelated project, so `pip install omniscrape` installs the wrong thing. The import name and the command are still `omniscrape`:
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
| `browser` | Playwright Chromium rendering, actions, screenshots, PDF | `pip install "omni-scrape[browser]"` then `playwright install chromium` |
| `stealth` | Camoufox for opt-in stealth (`tier=3`) | `pip install "omni-scrape[stealth]"` |
| `fast` | Opt-in `selectolax` Lexbor CSS backend | `pip install "omni-scrape[fast]"` |
| `httpx` | Alternative HTTP/2 client (`tier="httpx"`) | `pip install "omni-scrape[httpx]"` |
| `storage` | DuckDB output | `pip install "omni-scrape[storage]"` |
| `markdown` | Exact token counts via `tiktoken` | `pip install "omni-scrape[markdown]"` |
| `mcp` | MCP server for AI agents | `pip install "omni-scrape[mcp]"` |
| `shell` | IPython for `omniscrape shell` | `pip install "omni-scrape[shell]"` |
| `all` | All of the above | `pip install "omni-scrape[all]"` |

Quote the requirement (`"omni-scrape[browser]"`) so your shell does not interpret the brackets.

## Browser rendering

Tier 2 (JavaScript rendering) uses Playwright. After installing the `browser` extra, download the browser once:

```bash
pip install "omni-scrape[browser]"
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
