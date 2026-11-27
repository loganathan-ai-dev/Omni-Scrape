# CLI Reference

The `omniscrape` command ships with the package (`pip install omni-scraper`). Source: [`cli/main.py`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/cli/main.py).

```text
omniscrape [--version] COMMAND [ARGS]...

Commands:
  get      Scrape and extract data from a single URL.
  crawl    Crawl a site from URL, extracting each page, and save items to a file.
  map      List a site's URLs from its sitemaps and start page (robots.txt respected).
  extract  Extract fields from URL using a JSON schema of CSS/XPath selectors.
  curl     Replay a curl command (e.g. a browser's "Copy as cURL") and extract the response.
  shell    Interactive shell with omniscrape preloaded.
  mcp      Start the Model Context Protocol (MCP) server for AI agents.
```

> [!NOTE]
> **Data goes to stdout; logs, spinners and tables go to stderr.** So `omniscrape get URL -f json | jq` and `omniscrape get URL -f markdown > page.md` stay clean. The one exception is the default `summary` format of `get`, which is a human-facing table printed to stderr. On failure a one-line `error: ...` message is printed to stderr and the exit code is `1` (`130` on Ctrl-C).

## Shared fetch options

`get` and `extract` accept the same fetch options:

| Flag | Default | Description |
|---|---|---|
| `--tier`, `-t INT` | auto | Force fetcher tier (1 HTTP, 2 browser, 3 stealth) |
| `--stealth` | off | Allow escalation to the stealth browser tier |
| `--proxy URL` | none | Proxy URL, e.g. `http://user:pass@host:8080` |
| `--header`, `-H "Name: value"` | none | Extra request header (repeatable) |
| `--timeout FLOAT` | `30.0` | Request timeout in seconds |
| `--wait-for SELECTOR` | none | CSS selector to wait for (browser tiers) |
| `--impersonate PROFILE` | `chrome` | Browser profile for the HTTP tier: `chrome`, `edge`, `safari`, `firefox`, `chrome_android`, `safari_ios` |
| `--http-version` | `2` | `1.1`, `2` or `3` (HTTP/3) for the HTTP tier |

Tiers 2 and 3 need extras; see [[Installation]] and [[Fetching-and-Stealth]].

## `omniscrape get URL`

Scrape and extract data from a single URL.

| Flag | Default | Description |
|---|---|---|
| `--format`, `-f` | from `-o`, else `summary` | `summary`, `json`, `markdown`, `html` or `text` |
| `--css`, `-s SELECTOR` | none | Print the matching elements' text (one per line) instead of the chosen format. `::text` and `::attr(name)` selectors print the values directly, e.g. `--css "a::attr(href)"`. Exits with an error if nothing matches |
| `--output`, `-o FILE` | stdout | Write output to a file; without `-f`, `.json`, `.md`, `.html` and `.txt` choose the format |
| *shared fetch options* | | See above |

- `summary` prints a table to stderr: status, page type, latency, fetcher tier, product/article fields and any recipe, jobs, events, rating, FAQ, contacts, breadcrumbs, next page and tables found, plus the link count.
- `json` prints the full `ScrapeResult` as JSON.
- `markdown` prints the page's `markdown` field; `html` the raw HTML; `text` the plain main-content text.

```bash
omniscrape get https://books.toscrape.com/                         # summary table
omniscrape get https://books.toscrape.com/ -f markdown             # clean Markdown on stdout
omniscrape get https://example.com/app -f json --tier 2 > page.json
omniscrape get https://example.com --css "h1" -H "Accept-Language: en" --proxy http://p:8080
omniscrape get https://example.com/shop --tier 2 --wait-for ".product-card" -f markdown -o shop.md
omniscrape get https://blocked.example/ --stealth -f json
```

## `omniscrape curl COMMAND`

Replay a curl command, typically one copied from the browser's dev tools (*Copy as cURL*, bash or Windows `cmd`
style), through OmniScrape's HTTP tier, then extract the response like `get` does. Pass the whole command as one
quoted argument.

| Flag | Default | Description |
|---|---|---|
| `--format`, `-f` | from `-o`, else `summary` | `summary`, `json`, `markdown`, `html` or `text` |
| `--css`, `-s SELECTOR` | none | Print matching text instead |
| `--output`, `-o FILE` | stdout | Write output to a file |
| `--tier`, `-t INT` | `1` | Fetcher tier to replay with |
| `--impersonate PROFILE` | `chrome` | Browser profile for the HTTP tier |

```bash
omniscrape curl "curl 'https://api.example.com/items?page=2' -H 'accept: application/json' -b 'sid=abc'" -f json
```

Supported curl options: `-X -H -b -d/--data* --data-urlencode --json -A -e -u -x -G -I -m -k --http1.1/--http2/--http3 --url`.
`-d @file` and `-F` uploads are rejected with a clear error; output-only flags such as `-s`, `-v` and `--compressed` are ignored.

## `omniscrape crawl URL`

Crawl a site starting at URL, staying on the start URL's host, and save one item per page.

| Flag | Default | Description |
|---|---|---|
| `--max-pages INT` | `50` | Stop after this many pages |
| `--depth INT` | unlimited | Maximum link depth from the start URL |
| `--concurrency`, `-c INT` | `5` | Concurrent requests |
| `--delay FLOAT` | `0.0` | Seconds between requests per domain |
| `--output`, `-o FILE` | `omniscrape-items.jsonl` | Output file; the extension picks the backend: `.jsonl` / `.ndjson` for JSONL, `.duckdb` for DuckDB (needs `omni-scraper[storage]`). `.json` and other extensions are rejected (items are one JSON object per line). An existing file is replaced unless `--resume` or `--append` is given |
| `--allow REGEX` | none | Only follow URLs matching this regex |
| `--deny REGEX` | none | Never follow URLs matching this regex |
| `--resume` / `--no-resume` | `--no-resume` | Persist the queue and resume an interrupted crawl (appends to `--output`) |
| `--append` | off | Append to an existing `--output` instead of replacing it |
| `--no-robots` | off | Do not obey `robots.txt` (only for sites you own or may crawl) |
| `--sitemap` | off | Also seed the queue from the site's sitemaps |
| `--tier`, `-t INT` | `1` | Fetcher tier for every page |

Each saved item contains `url`, `status`, `title`, `content_type` and `markdown` (the main-content Markdown), plus `product`, `article` and `entities` (recipe, events, jobs, reviews, FAQ, contacts, breadcrumbs, next page, tables) when the page has them. When the crawl finishes, a table of crawl statistics (pages, items, failed, `robots_blocked`, duplicates, pages per second and more) is printed to stderr.

With `--resume`, the request queue and de-duplication state are stored in SQLite under `~/.omniscrape/queues/` (one file per crawl, named after the start host). Re-run the same command after an interruption to continue.

```bash
omniscrape crawl https://books.toscrape.com/ --max-pages 100 -o books.jsonl --resume
omniscrape crawl https://example.com/ --depth 2 --allow "/docs/" --deny "/docs/archive" -o docs.duckdb
omniscrape crawl https://example.com/ --sitemap --concurrency 8 --delay 0.5 --max-pages 500
```

## `omniscrape map URL`

List a site's URLs from its sitemaps and start page. `robots.txt` is respected.

| Flag | Default | Description |
|---|---|---|
| `--search`, `-q TERMS` | none | Rank URLs by relevance to these terms |
| `--limit INT` | `200` | Maximum URLs to return |
| `--format`, `-f` | `text` | `text` (one URL per line) or `json` |

URLs go to stdout; the count goes to stderr.

```bash
omniscrape map https://example.com
omniscrape map https://example.com --search pricing --limit 20
omniscrape map https://example.com -f json > urls.json
```

## `omniscrape extract URL`

Fetch URL and extract fields using a JSON schema of CSS/XPath selectors (the same format as `Selector.extract`, see [[Selectors-and-Extraction]]).

| Flag | Default | Description |
|---|---|---|
| `--schema`, `-s FILE` | required | JSON file with a declarative schema (must be a JSON object) |
| `--output`, `-o FILE` | stdout | Write the extracted JSON to a file |
| *shared fetch options* | | See above |

`schema.json`:

```json
{
  "title": "h1::text",
  "price": {"selector": ".price::text", "type": "price"}
}
```

```bash
omniscrape extract https://example.com/item/1 --schema schema.json
omniscrape extract https://example.com/item/1 -s schema.json -o item.json --tier 2
```

## `omniscrape shell [URL]`

Open an interactive shell with `omniscrape` preloaded. IPython is used when installed (`pip install "omni-scraper[shell]"`), otherwise the standard Python REPL.

| Flag | Description |
|---|---|
| `--plain` | Use the standard Python REPL even if IPython is installed |

Names available in the shell: `omniscrape`, `Selector`, `scrape_sync(url)` (returns a `ScrapeResult`), `fetch_sync(url)` (returns a `FetchResult`), `curl(command)` (replays a pasted *Copy as cURL* command and returns a `FetchResult`), `uncurl(command)` (just parses it) and `entities(html, url)` (zero-config page entities). If you pass a URL, `response` (the `FetchResult`) and `page` (a `Selector` over its HTML) are loaded for you.

```bash
omniscrape shell https://example.com
>>> page.css("h1::text").get()
>>> response.status_code
```

## `omniscrape mcp`

Start the MCP server for AI agents. Needs `pip install "omni-scraper[mcp]"`. Full details are on [[MCP-Server]].

| Flag | Default | Description |
|---|---|---|
| `--transport` | `stdio` | `stdio` for desktop agents, or `http` for streamable HTTP served at `/mcp` |
| `--host TEXT` | `127.0.0.1` | Host for `--transport http` |
| `--port`, `-p INT` | `8000` | Port for `--transport http` |

```bash
omniscrape mcp                                   # stdio
omniscrape mcp --transport http --port 8000      # http://127.0.0.1:8000/mcp
```
