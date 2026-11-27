# MCP Server

OmniScrape ships a [Model Context Protocol](https://modelcontextprotocol.io/) server built on FastMCP, so AI agents (Claude Code, Claude Desktop, Cursor and others) can scrape pages through tool calls. Source: [`mcp/server.py`](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/src/omniscrape/mcp/server.py).

## Install and run

```bash
pip install "omni-scrape[mcp]"
omniscrape mcp                                   # stdio (default)
omniscrape mcp --transport http --port 8000      # streamable HTTP at http://127.0.0.1:8000/mcp
```

If `fastmcp` is not installed the command exits with a message telling you to install `omni-scrape[mcp]`.

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `scrape_url` | `url`, `allow_stealth=False` | JSON with title, main-content Markdown, product/article data, metadata and links. Raw HTML and the raw structured-data dump are left out to save tokens |
| `scrape_product` | `url` | JSON `Product` fields: title, price, currency, brand, SKU, availability, rating |
| `scrape_article` | `url` | JSON `Article` fields: title, author, dates and body text |
| `get_markdown` | `url`, `query=None`, `max_tokens=None`, `allow_stealth=False` | Main-content Markdown. With `query`, only the blocks relevant to it (BM25); `max_tokens` caps the length. For a failed or blocked page it returns `Error: <url> returned HTTP <status>` (plus the detected anti-bot system) instead of handing the agent an error page as content |
| `map_site` | `url`, `search=None`, `limit=200` | JSON list of the site's URLs from its sitemaps and start page, `robots.txt` respected; `search` ranks them |

`allow_stealth` lets the call escalate to the stealth browser tier when blocked. It never solves CAPTCHAs; see [[Fetching-and-Stealth]].

## Transports

- **stdio** (default): the right choice for desktop agents that launch the server as a subprocess. stdout carries only the MCP protocol; OmniScrape's logs go to stderr so they cannot corrupt the stream.
- **HTTP**: streamable HTTP served at `/mcp`. Options: `--host` (default `127.0.0.1`) and `--port` / `-p` (default `8000`).

## Claude Code

```bash
claude mcp add omniscrape -- omniscrape mcp
```

Or install the repository's Claude Code plugin, which bundles the skill and an MCP server entry (install `omni-scrape[mcp]` first):

```text
/plugin marketplace add loganathan-ai-dev/Omni-Scrape
/plugin install omniscrape@omni-scrape
```

## Claude Desktop

Add the server to `claude_desktop_config.json` (Settings, Developer, Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "omniscrape": {
      "command": "omniscrape",
      "args": ["mcp"]
    }
  }
}
```

If Claude Desktop cannot find the `omniscrape` executable, use the absolute path to it (for example from `where omniscrape` on Windows or `which omniscrape` on macOS and Linux), or run it through your Python: `"command": "python", "args": ["-m", "omniscrape.cli.main", "mcp"]`.

## Security

> [!WARNING]
> The server fetches **any URL an agent asks for**, from the machine it runs on. That includes internal addresses such as `localhost`, private network hosts and cloud metadata endpoints. Run it only for agents you trust, prefer a sandboxed or network-restricted environment, and do not expose the HTTP transport beyond `127.0.0.1` without authentication in front of it. Content returned to the agent comes from the open web and should be treated as untrusted input (it can contain prompt-injection text).

## See also

- [[CLI-Reference]]: the `omniscrape mcp` flags.
- [[Markdown-and-Agents]]: the Markdown pipeline behind `get_markdown`, and the agent skills.
- [[FAQ-and-Troubleshooting]]: MCP troubleshooting.
