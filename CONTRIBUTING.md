# Contributing to OmniScrape

Thanks for helping. Bug reports, fixes, docs and benchmark corrections are all welcome.

## Set up

```bash
git clone https://github.com/loganathan-ai-dev/Omni-Scrape.git
cd Omni-Scrape
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev,browser,mcp,storage,fast]"
playwright install chromium
```

## Before you open a pull request

```bash
ruff check .          # lint (also run by CI)
pytest                # unit + local-site integration tests, no internet needed
mypy                  # advisory for now; please do not add new errors
```

- Tests live in `tests/unit` and `tests/integration`. Integration tests start a local HTTP site
  (`benchmarks/suites/crawl.py::SiteServer`), so they run from a git checkout, not from the sdist.
- Add a test with every bug fix. Put regressions in `tests/unit/test_bugfixes.py`.
- Keep the public API small. New public names go in `src/omniscrape/__init__.py` (lazy exports and `__all__`).
- Mark tests that need the internet with `@pytest.mark.network` and tests that need a browser with
  `@pytest.mark.browser`.

## Agent skills

The `omniscrape` skill is kept in two folders that must be identical. Edit `.agents/skills/omniscrape/`,
then run:

```bash
python scripts/sync_skills.py          # copy to .claude/skills
python scripts/sync_skills.py --check  # CI check; fails when they differ
```

## Benchmarks

Changing performance-sensitive code? Re-run the relevant suite (`python -m benchmarks run --suite parse`)
and mention the result. Do not edit published numbers by hand; they come from `benchmarks/published/`.
See [benchmarks/README.md](benchmarks/README.md).

## Commit and PR style

- One logical change per PR, a clear title, and a short description of the why.
- Conventional-style prefixes are appreciated: `fix:`, `feat:`, `docs:`, `test:`, `chore:`.
- Do not include secrets, scraped personal data or large fixtures.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md).

## Code of conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
