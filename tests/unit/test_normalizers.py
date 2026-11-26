"""Unit tests for data normalizers."""

import pytest
from omniscrape.normalizers.currency import parse_price
from omniscrape.normalizers.dates import parse_date
from omniscrape.normalizers.markdown import html_to_markdown
from omniscrape.normalizers.units import parse_unit


def test_parse_price():
    assert parse_price("₹1,299.00") == (1299.0, "INR")
    assert parse_price("$49.99") == (49.99, "USD")
    assert parse_price("€ 1.299,50") == (1299.50, "EUR")
    assert parse_price("£15.00") == (15.0, "GBP")
    assert parse_price("FREE") == (0.0, "USD")
    assert parse_price("") == (None, "USD")


def test_parse_unit():
    assert parse_unit("500 g") == (500.0, "g")
    assert parse_unit("1.5 kg") == (1500.0, "g")
    assert parse_unit("200 ml") == (200.0, "ml")
    assert parse_unit("1 L") == (1000.0, "ml")
    assert parse_unit("Pack of 6") == (6.0, "pcs")
    assert parse_unit("250 g x 2") == (500.0, "g")


def test_parse_date():
    parsed = parse_date("Nov 23, 2026")
    assert parsed is not None
    assert "2026-11-23" in parsed


def test_html_to_markdown():
    html = """
    <div>
        <nav><a href="/">Home</a></nav>
        <h1>Article Header</h1>
        <p>This is the first paragraph with a <a href="https://example.com">link</a>.</p>
        <script>console.log('remove me');</script>
    </div>
    """
    md = html_to_markdown(html)
    assert "# Article Header" in md
    assert "[link](https://example.com)" in md
    assert "remove me" not in md
    assert "Home" not in md  # nav element was stripped
