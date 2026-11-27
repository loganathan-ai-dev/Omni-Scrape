"""Tests for the native content pipeline: money parsing, structured data, product, metadata, Markdown."""

import pytest

from omniscrape.content.chunking import chunk_markdown
from omniscrape.content.extract import extract_main
from omniscrape.content.filters import bm25_filter_markdown
from omniscrape.content.markdown import fit_markdown, html_to_markdown
from omniscrape.content.metadata import extract_metadata
from omniscrape.extract.product import extract_product
from omniscrape.normalizers.currency import parse_money
from omniscrape.parsers.structured import extract_structured


@pytest.mark.parametrize("raw, expected", [
    ("₹1,29,999", (129999.0, "INR")), ("1.299,00 €", (1299.0, "EUR")), ("A$12.50", (12.5, "AUD")),
    ("Offers from $5", (5.0, "USD")), ("1 299,90 SEK", (1299.9, "SEK")), ("€1.299", (1299.0, "EUR")),
    ("Rs. 499", (499.0, "INR")), ("Price: 7,799", (7799.0, None)),
])
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


def test_structured_jsonld_graph_microdata_rdfa_and_og_lists():
    html = """<html><head>
      <script type="application/ld+json">{"@context":"https://schema.org","@graph":[
        {"@type":"WebPage","name":"x"},{"@type":"Product","name":"Graph Lamp","offers":{"price":"10.00"}},]}</script>
      <meta property="og:image" content="/a.jpg"><meta property="og:image" content="/b.jpg">
      <meta name="DC.creator" content="Ada">
      </head><body>
      <div itemscope itemtype="https://schema.org/Product"><span itemprop="name">Micro Mug</span>
        <div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><meta itemprop="price" content="4.50"></div></div>
      <div vocab="https://schema.org/" typeof="Person"><span property="name">Grace</span></div>
    </body></html>"""
    s = extract_structured(html, "https://shop.example/")
    assert [i["name"] for i in s["json-ld"] if i.get("@type") == "Product"] == ["Graph Lamp"]  # trailing comma tolerated
    micro = s["microdata"][0]
    assert micro["@type"] == "Product" and micro["name"] == "Micro Mug" and micro["offers"]["price"] == "4.50"
    assert s["rdfa"][0] == {"@type": "Person", "name": "Grace"}
    assert s["opengraph"]["og:image"] == ["/a.jpg", "/b.jpg"]
    assert s["dublincore"]["creator"] == "Ada"


PRODUCT_NO_SCHEMA = """<html><head><title>Trail Kettle 1.2L | Basecamp Store</title></head><body>
<nav><a href="/">Home</a><a href="/cart">Cart</a></nav>
<div class="pdp"><h1 class="t1">Trail Kettle 1.2L</h1>
  <div class="maker">Brand: Basecamp</div>
  <div class="cost"><s class="x">$59.00</s> <span class="y"><span>$</span><span>44</span><span>.</span><span>90</span></span></div>
  <p>Item code: TK-1200</p><p class="avail">Only 3 left in stock</p>
  <div class="stars" title="4.4 out of 5 stars">★★★★</div><a href="#r">212 reviews</a>
</div>
<section><h3>Customers also bought</h3>
  <div class="c"><a href="/p/1">Mug</a><span class="price">$9.99</span></div>
  <div class="c"><a href="/p/2">Pot</a><span class="price">$19.99</span></div>
  <div class="c"><a href="/p/3">Cup</a><span class="price">$4.99</span></div>
</section></body></html>"""


def test_product_heuristics_without_structured_data():
    p = extract_product(PRODUCT_NO_SCHEMA, "https://shop.example/p/kettle")
    assert p.title == "Trail Kettle 1.2L"
    assert p.price == 44.9 and p.currency == "USD"   # split price, not the struck-through or carousel prices
    assert p.brand == "Basecamp"
    assert p.sku == "TK-1200"
    assert p.availability == "InStock"
    assert p.rating == 4.4 and p.review_count == 212


def test_product_from_opengraph_and_shopify_json():
    html = """<html><head><meta property="og:type" content="product"><meta property="og:title" content="Apron">
      <meta property="product:price:amount" content="48.00"><meta property="product:price:currency" content="usd">
      <script type="application/json" id="ProductJson-main">{"title":"Apron","vendor":"Fernhill",
        "variants":[{"sku":"FH-1","price":4800,"available":false}]}</script></head><body><h1>Apron</h1></body></html>"""
    p = extract_product(html, "https://fernhill.example/p")
    assert (p.title, p.price, p.currency, p.brand, p.sku, p.availability) == ("Apron", 48.0, "USD", "Fernhill", "FH-1", "OutOfStock")


def test_product_currency_is_none_when_not_shown():
    p = extract_product("<html><body><h1>Plain Item</h1><p>Price: 7,799</p></body></html>", "u")
    assert p.price == 7799.0 and p.currency is None


def test_article_metadata_from_visible_markup_and_url_authors_ignored():
    html = """<html><head><title>Rivers of Light - Field Notes</title></head><body>
      <article itemscope itemtype="https://schema.org/Article"><h1 itemprop="headline">Rivers of Light</h1>
      <p class="byline">By <a href="/people/mara-quinn" itemprop="author">Mara Quinn</a></p>
      <time datetime="2025-03-14T09:00:00Z">March 14, 2025</time><p>Body text.</p></article></body></html>"""
    meta = extract_metadata(html, "https://notes.example/rivers")
    assert meta["title"] == "Rivers of Light"
    assert meta["author"] == "Mara Quinn"           # microdata value is the href; the visible name is used
    assert meta["published_date"] == "2025-03-14"


ARTICLE_PAGE = """<html><head><title>Copper Tides | Harbor Weekly</title></head><body>
<header><a href="/">Harbor Weekly</a><nav><a href="/a">News</a><a href="/b">Sport</a><a href="/c">Weather</a></nav></header>
<div id="cookie-banner" class="cookie-consent">We use cookies to improve your experience. Accept all cookies?</div>
<main><article><h1>Copper Tides</h1>
<p>The harbor turned copper at dusk, and the fishing fleet came home early for the first time in a decade.</p>
<p>Local skippers said the water temperature had risen by two degrees, changing where the mackerel feed.</p>
<div class="share-bar"><a href="#">Share</a><a href="#">Tweet</a></div>
<h2>What changes next</h2>
<p>The council will publish new mooring rules in spring, after a public consultation with the fleet.</p>
<table><tr><th>Month</th><th>Catch (t)</th></tr><tr><td>June</td><td>120</td></tr></table>
<pre><code class="language-python">print("tide")</code></pre>
</article><aside class="related"><h3>Related</h3><a href="/x">Storm season ahead</a><a href="/y">New ferry route</a></aside></main>
<footer><a href="/privacy">Privacy</a> <a href="/terms">Terms</a> © Harbor Weekly</footer></body></html>"""


def test_fit_markdown_keeps_article_and_drops_boilerplate():
    md = fit_markdown(ARTICLE_PAGE, "https://harbor.example/copper-tides")
    assert md.startswith("# Copper Tides")
    assert "fishing fleet came home early" in md and "public consultation" in md
    assert "## What changes next" in md
    assert "| Month | Catch (t) |" in md
    assert '```python\nprint("tide")\n```' in md
    for junk in ("cookies", "Privacy", "Storm season", "Tweet", "Sport"):
        assert junk not in md


def test_html_to_markdown_links_images_lists_and_citations():
    html = """<body><p>See <a href="/docs">the docs</a> and <img src="i.png" alt="logo"></p>
      <ol><li>One<ul><li>Nested</li></ul></li><li>Two</li></ol><blockquote><p>Quoted</p></blockquote></body>"""
    md = html_to_markdown(html, "https://site.example/a/")
    assert "[the docs](https://site.example/docs)" in md
    assert "![logo](https://site.example/a/i.png)" in md
    assert "1. One\n   - Nested\n2. Two" in md
    assert "> Quoted" in md
    cited = html_to_markdown(html, "https://site.example/a/", citations=True)
    assert "the docs [1]" in cited and "[1]: https://site.example/docs" in cited


def test_main_extraction_reports_title_and_text():
    main = extract_main(ARTICLE_PAGE)
    assert main.title == "Copper Tides"
    assert "mooring rules" in main.text and "Privacy" not in main.text


def test_sibling_blocks_are_merged_without_crashing():
    # The best block has qualifying siblings, so extraction returns several nodes (regression: crashed).
    html = """<html><body><div class="wrap">
      <div class="entry-content"><p>Roast the tomatoes slowly, with garlic, thyme, and a little oil, for ninety minutes.</p>
        <p>Blend everything with stock, then season, taste, and adjust the thickness with water.</p></div>
      <div class="notes"><p>Leftovers keep for four days in the fridge, or three months in the freezer, well sealed.</p>
        <p>Reheat gently, stirring often, so the soup does not catch on the bottom of the pan.</p></div>
      <p>Serve it hot, with grilled cheese, crusty bread, or a simple green salad on the side.</p>
    </div></body></html>"""
    main = extract_main(html)
    for phrase in ("ninety minutes", "three months", "green salad"):
        assert phrase in main.text


def test_bm25_filter_and_chunking():
    md = "# Guide\n\n## Pricing\n\nPlans cost ten dollars per seat each month.\n\n## Weather\n\nSunny skies tomorrow."
    filtered = bm25_filter_markdown(md, "pricing plans cost")
    assert "ten dollars" in filtered and "Sunny" not in filtered and filtered.startswith("# Guide")
    chunks = chunk_markdown(md, max_tokens=12)
    assert len(chunks) >= 2
    assert any(c.headings[-1] == "Weather" and "Sunny" in c.text for c in chunks)
    assert all(c.tokens <= 12 for c in chunks)
