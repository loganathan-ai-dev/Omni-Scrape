# FAQ and Troubleshooting

## Installation

### `pip install omniscrape` installed a different project

The PyPI name `omniscrape` belongs to an unrelated project. This library is published as **`omni-scrape`**:

```bash
pip uninstall omniscrape
pip install omni-scrape
```

You still `import omniscrape` and run the `omniscrape` command. See [[Installation]].

### `ConfigError: selectolax is not installed` (or the `selectolax` backend fails)

`Selector(..., backend="selectolax")` needs the optional `fast` extra:

```bash
pip install "omni-scrape[fast]"
```

The `selectolax` backend is for fast CSS selection only; use the default `lxml` backend when you need XPath or `adaptive=True`. See [[Selectors-and-Extraction]].

### Tier 2 or `--tier 2` fails because no browser is installed

Install the extra and download Chromium once:

```bash
pip install "omni-scrape[browser]"
playwright install chromium
```

Tier 3 needs `pip install "omni-scrape[stealth]"`. DuckDB output needs `omni-scrape[storage]`, the MCP server needs `omni-scrape[mcp]`, and IPython in `omniscrape shell` needs `omni-scrape[shell]`.

## Fetching

### Why do I get an empty page (no content, just a JS shell)?

Tier 1 is a plain HTTP fetch and does not run JavaScript. In auto mode OmniScrape escalates an empty JS/SPA shell to the browser tier (tier 2) automatically, but that needs the `browser` extra. If you still get an empty page, force the browser tier and wait for something that proves the content loaded:

```python
res = await omniscrape.fetch("https://example.com/app", tier=2, wait_for=".product-card")
```

```bash
omniscrape get https://example.com/app --tier 2 --wait-for ".product-card" -f markdown
```

Note that `omniscrape crawl` and `CrawlEngine` default to `tier=1` for every page; pass `--tier 2` (or `tier=2`) for JavaScript-rendered sites. See [[Fetching-and-Stealth]].

### I am blocked (HTTP 403 or 429, Cloudflare, DataDome...)

OmniScrape **detects** anti-bot systems but does not defeat them. The detected system is recorded in `FetchResult.defense_detected` (`cloudflare`, `datadome`, `akamai`, `perimeterx`, `kasada`, `aws_waf` or `none`). By default a blocked response is returned as is, with a warning in the logs.

You can opt in to the stealth browser tier:

```python
res = await omniscrape.fetch(url, allow_stealth=True)   # or tier=3
print(res.status_code, res.defense_detected)
```

```bash
omniscrape get URL --stealth
```

This needs `omni-scrape[stealth]`. It does **not** solve CAPTCHAs or interactive challenges, so some sites will still block you. Only scrape what you are allowed to scrape. See [[Comparison]] for where OmniScrape is behind.

### Requests keep failing or time out

- Raise the timeout: `--timeout 60` on the CLI, or `OmniClient(timeout=60)`.
- Retries are on by default (`retries=2`) for transport errors, `429` (honouring `Retry-After`) and `408/500/502/503/504/520-524`. `DNSResolutionError` and `SSLHandshakeError` fail immediately by design.
- Add a `CircuitBreaker` and `DeadLetterQueue` to `OmniClient` to stop hammering a failing domain and to keep a record of failed URLs.

## Crawling

### `robots.txt` disallowed my URL

`CrawlEngine` and `map_site` obey `robots.txt` by default, including `Crawl-delay`. Disallowed URLs are skipped and counted under `robots_blocked` in the crawl statistics. If you own the site or have permission to crawl it, you can turn this off: `CrawlEngine(..., obey_robots=False)` or `omniscrape crawl URL --no-robots`. Do not do this for sites you do not control.

### How do I resume an interrupted crawl?

Persist the queue and de-duplication state in SQLite, then re-run the same program or command.

```python
CrawlEngine(Books(), storage=JSONLStorage("books.jsonl"), max_pages=200, queue_path="books-queue.db")
```

```bash
omniscrape crawl https://books.toscrape.com/ --max-pages 100 -o books.jsonl --resume
```

`use_checkpoint=True` does the same without naming a file: the queue is stored under `~/.omniscrape/queues/`. See [[Crawling-and-Storage]].

### My crawl only fetched a few pages

Check, in order: `max_pages` / `--max-pages` (the CLI default is `50`), `max_depth` / `--depth`, your `--allow` / `--deny` regexes, `allowed_domains` (the CLI only follows the start host), and the `filtered_*` and `robots_blocked` counters in the printed statistics.

### CLI output file must end in `.jsonl` or `.duckdb`

`omniscrape crawl` picks the storage backend from the `-o` extension: `.jsonl`, `.ndjson` or `.json` for JSON Lines, `.duckdb` for DuckDB (needs `omni-scrape[storage]`).

## Selectors

### My selector stopped matching after a site redesign

Use adaptive selectors: save a fingerprint once with `auto_save=True`, then call `css(..., adaptive=True)` on the new HTML. Adaptive mode needs the default `lxml` backend. See [[Selectors-and-Extraction]].

### `omniscrape get --css` exits with an error

It prints the text of the matching elements and exits with an error when the selector matches nothing. Check the selector, or use `--tier 2` if the elements are rendered by JavaScript.

## MCP

### MCP stdio output is corrupted or the client cannot parse the stream

On the stdio transport, stdout must carry only the MCP protocol. OmniScrape's logs go to **stderr**, so upgrade to a current version if you see log lines in stdout. Also make sure nothing else in your launch command prints to stdout (shell profile banners, wrapper scripts). See [[MCP-Server]].

### Claude Desktop cannot start the server

Install the extra (`pip install "omni-scrape[mcp]"`), and use the absolute path of the `omniscrape` executable in the config if it is not on the PATH that Claude Desktop sees.

## CLI

### Where does the output go?

Data goes to stdout, and logs, spinners and tables go to stderr. So `omniscrape get URL -f json > page.json` writes clean JSON. The default `summary` format is a table on stderr. See [[CLI-Reference]].
