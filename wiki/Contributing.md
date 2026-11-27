# Contributing

Contributions are welcome. The full guidelines live in [CONTRIBUTING.md](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/CONTRIBUTING.md); please read them before opening a pull request.

## Dev setup

```bash
git clone https://github.com/loganathan-ai-dev/Omni-Scrape.git && cd Omni-Scrape
pip install -e ".[dev,browser,mcp,storage,fast]" && playwright install chromium
ruff check . && pytest
```

## Useful links

- [Issues](https://github.com/loganathan-ai-dev/Omni-Scrape/issues): bug reports and feature requests
- [Code of Conduct](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/CODE_OF_CONDUCT.md)
- [Security policy](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/SECURITY.md): how to report a vulnerability privately
- [Changelog](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/CHANGELOG.md)
- [Benchmark harness](https://github.com/loganathan-ai-dev/Omni-Scrape/blob/main/benchmarks/README.md): see also [[Benchmarks]]

Setup details are also on the [[Installation]] page.
