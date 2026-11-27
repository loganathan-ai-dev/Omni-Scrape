# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

OmniScrape: a Python web-scraping library. **PyPI name `omni-scrape`**, import `omniscrape`, CLI `omniscrape`.
Source is in `src/omniscrape/` (src layout, hatchling build).

## Commands

```bash
pip install -e ".[dev,browser,mcp,storage,fast]" && playwright install chromium
ruff check .                         # must pass
pytest                               # offline; integration tests use a local site
mypy                                 # advisory, do not add new errors
python scripts/sync_skills.py        # after editing .agents/skills/omniscrape/
python -m build && twine check dist/*
```

## Layout

- `src/omniscrape/client.py`: `OmniClient` (fetch, scrape, batch, retries, escalation).
- `fetchers/`: tier 1 `FastFetcher` (curl_cffi), tier 2 `DynamicFetcher` (Playwright), tier 3 `StealthFetcher`.
- `parsers/`: `Selector`, adaptive engine, structured data. `extract/`, `content/`: extraction and Markdown.
- `crawler/`: `CrawlEngine`, `Spider`, robots, throttle, queue. `storage/`: JSONL and DuckDB.
- `cli/main.py` (Click), `mcp/server.py` (FastMCP).
- `tests/unit`, `tests/integration`. `benchmarks/`: harness and corpus (not shipped in the package).
- `.agents/skills/omniscrape/` is the canonical agent skill; `.claude/skills/omniscrape/` is a generated copy.

## Rules

- Logs go to **stderr**. Never print to stdout from library code: the CLI's JSON output and the MCP stdio
  transport depend on a clean stdout.
- Do not add dependencies to the core `dependencies` list without a strong reason; use an extra.
- Add a regression test with every fix (`tests/unit/test_bugfixes.py`). Update `CHANGELOG.md` under `[Unreleased]`.
- Public API changes: update `src/omniscrape/__init__.py` (lazy map and `__all__`), the skill cheatsheet and `docs/`.
- Do not hand-edit `benchmarks/published/`; README benchmark numbers must match those JSON files.
- Respect `robots.txt` by default and do not add CAPTCHA-solving or challenge-bypass code.
