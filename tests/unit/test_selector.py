"""Unit tests for CSS/XPath selector and element traversal."""

import pytest
from omniscrape.parsers.selector import Selector

HTML_SAMPLE = """
<!DOCTYPE html>
<html>
<head><title>Test Store</title></head>
<body>
    <div id="main" class="container">
        <h1 class="header">Sample Product</h1>
        <div class="pricing">
            <span class="price" data-currency="INR">₹1,499.00</span>
            <span class="discount">20% off</span>
        </div>
        <ul class="specs">
            <li>Color: Blue</li>
            <li>Weight: 500g</li>
        </ul>
        <a href="/buy" class="btn-buy">Buy Now</a>
    </div>
</body>
</html>
"""


def test_selector_css():
    sel = Selector(HTML_SAMPLE)
    h1 = sel.css("h1.header")
    assert len(h1) == 1
    assert h1[0].text == "Sample Product"
    assert h1[0].tag == "h1"

    price = sel.css(".pricing .price")
    assert len(price) == 1
    assert price[0].text == "₹1,499.00"
    assert price[0].get("data-currency") == "INR"


def test_selector_xpath():
    sel = Selector(HTML_SAMPLE)
    items = sel.xpath("//ul[@class='specs']/li")
    assert len(items) == 2
    assert "Color: Blue" in items[0].text


def test_selector_find_by_text():
    sel = Selector(HTML_SAMPLE)
    matches = sel.find_by_text("Buy Now", exact=True)
    assert len(matches) == 1
    assert matches[0].tag == "a"
    assert matches[0].get("href") == "/buy"


def test_selector_find_by_regex():
    sel = Selector(HTML_SAMPLE)
    matches = sel.find_by_regex(r"₹\d+,\d+\.\d+")
    assert len(matches) >= 1
    assert "₹1,499.00" in matches[0].text


def test_element_hierarchy():
    sel = Selector(HTML_SAMPLE)
    price = sel.css(".price")[0]
    parent = price.parent()
    assert parent is not None
    assert parent.get("class") == "pricing"
    assert len(parent.children()) == 2
