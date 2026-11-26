"""Offline checks that the README's examples still work as documented."""

from pathlib import Path

import omniscrape
from omniscrape import fit_markdown, parse_date, parse_price, register_fetcher
from omniscrape.client import build_scrape_result
from omniscrape.fetchers.base import BaseFetcher
from omniscrape.models import FetchResult
from omniscrape.normalizers.currency import parse_money

BOOK = Path(__file__).resolve().parents[2] / "benchmarks/corpus/data/holdout/snap_books_product_00.html"


def test_readme_intro_product_example():
    url = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    page = build_scrape_result(FetchResult(url=url, status_code=200, html=BOOK.read_text(encoding="utf-8")))
    assert (page.product.title, page.product.price, page.product.currency) == ("A Light in the Attic", 51.77, "GBP")
    assert page.markdown.startswith("# A Light in the Attic")


def test_readme_utilities():
    assert parse_money("₹1,29,999") == (129999.0, "INR")
    assert parse_money("1.299,00 €") == (1299.0, "EUR")
    assert parse_money("Price: 7,799") == (7799.0, None)
    assert parse_price("$49.99") == (49.99, "USD")
    assert parse_date("Nov 23, 2026") == "2026-11-23T00:00:00"


async def test_readme_custom_fetcher():
    class MyApiFetcher(BaseFetcher):
        async def fetch(self, url, **kwargs):
            return FetchResult(url=url, status_code=200, html="<html><title>ok</title></html>")

        async def close(self):
            pass

    register_fetcher("readme-api", MyApiFetcher, override=True)
    res = await omniscrape.fetch("https://example.com", tier="readme-api")
    assert res.status_code == 200 and "ok" in res.html


def test_readme_citations():
    html = ('<html><body><article><h1>Tides</h1><p>The council published the <a href="/rules">new mooring rules</a> '
            'today, after a long public consultation with the fleet and harbour users.</p></article></body></html>')
    md = fit_markdown(html, url="https://harbor.example/n", links=True, citations=True)
    assert "new mooring rules [1]" in md and "[1]: https://harbor.example/rules" in md
