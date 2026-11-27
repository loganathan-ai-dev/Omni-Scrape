# GitHub and PyPI setup checklist

Things only you can do in the GitHub and PyPI web UIs. Everything else is already in the repository.

## 1. Repository "About" box

Repository page → the gear icon next to **About**.

- **Description**

  > Adaptive web scraping for Python: tiered HTTP/browser/stealth fetching, self-healing selectors, zero-config product & article extraction, LLM-ready Markdown, resumable crawling and an MCP server.

- **Website**: `https://github.com/loganathan-ai-dev/Omni-Scrape/wiki` (or the PyPI URL once published)
- **Topics**: `web-scraping` `python` `scraper` `crawler` `playwright` `mcp-server` `llm` `markdown` `adaptive-scraping` `asyncio` `claude-code`
- Tick **Releases** and **Packages** in the sidebar options if they are not already shown.

## 2. Social preview image

Settings → General → **Social preview** → upload `docs/assets/social-preview.png` (1280×640).

## 3. Wiki

The wiki repository does not exist until a first page is created.

1. Repository → **Wiki** tab → **Create the first page** → save any text.
2. `git clone https://github.com/loganathan-ai-dev/Omni-Scrape.wiki.git`
3. Copy the contents of this repository's `wiki/` folder into the clone, then `git add -A && git commit -m "Add wiki" && git push`.

Details are in [`wiki/README.md`](../wiki/README.md).

## 4. Discussions (optional)

Settings → General → Features → **Discussions**. The issue chooser already links to it.

## 5. PyPI: publish `omni-scrape`

The name `omniscrape` is taken on PyPI by an unrelated project; this package is **`omni-scrape`**.
Check that the name is still free first: <https://pypi.org/project/omni-scrape/> should return 404.

Releases use PyPI **Trusted Publishing** (no API tokens stored in GitHub).

1. Create accounts on <https://pypi.org> and <https://test.pypi.org>.
2. On each site → **Publishing** → *Add a new pending publisher*:
   - PyPI project name: `omni-scrape`
   - Owner: `loganathan-ai-dev`, Repository: `Omni-Scrape`
   - Workflow name: `release.yml`
   - Environment name: `pypi` (on PyPI) / `testpypi` (on TestPyPI)
3. GitHub → Settings → Environments → create `pypi` and `testpypi` (optionally require your approval on `pypi`).
4. Merge `dev` into `main` and make sure CI is green.
5. Tag and push:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

   The **Release** workflow checks the tag matches `src/omniscrape/_version.py`, builds, publishes to TestPyPI,
   then PyPI, then creates the GitHub Release from `docs/RELEASE_NOTES_0.1.0.md`.
6. Verify in a clean environment: `pip install omni-scrape && omniscrape --version`.

Manual dry run: Actions → **Release** → *Run workflow* → target `testpypi`.

## 6. Branches and Dependabot

- CI runs on `main` and `dev`. Dependabot now targets `dev` and groups updates into one PR per ecosystem.
- Open Dependabot PRs created before this change target `main` and will conflict with the new `pyproject.toml`
  and workflows. Close them (Dependabot reopens grouped PRs against `dev` on its next run); see the notes in the
  hand-off message for each PR.
