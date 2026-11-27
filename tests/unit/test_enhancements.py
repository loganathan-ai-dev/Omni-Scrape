"""Unit tests for Phase 1-5 enhancements: @id resolution, metadata, throttling, caching, batch, schemas, listings."""

import time

import pytest

from omniscrape.classifier.detector import detect_defense
from omniscrape.client import OmniClient
from omniscrape.content.metadata import extract_metadata
from omniscrape.crawler.throttle import DomainThrottle
from omniscrape.exceptions import SchemaValidationError
from omniscrape.extract.listings import extract_listings
from omniscrape.models import DefenseSystem, FetchResult
from omniscrape.parsers.selector import Selector
from omniscrape.parsers.semantic import SemanticExtractor
from omniscrape.parsers.structured import extract_structured


def test_jsonld_id_reference_resolution():
    html = """<html><head><script type="application/ld+json">{
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "Person", "@id": "https://site.example/#/person/1", "name": "Elena Rostova"},
        {"@type": "Article", "headline": "Graph Refs", "datePublished": "2026-11-23T08:00:00Z",
         "author": {"@id": "https://site.example/#/person/1"}}
      ]
    }</script></head><body><h1>Graph Refs</h1><p>Body text.</p></body></html>"""
    s = extract_structured(html, "https://site.example/post")
    articles = [i for i in s["json-ld"] if i.get("@type") == "Article"]
    assert articles[0]["author"]["name"] == "Elena Rostova"
    meta = extract_metadata(html, "https://site.example/post")
    assert meta["author"] == "Elena Rostova"
    assert meta["published_date"] == "2026-11-23"


def test_metadata_ordinal_date_citation_and_url_fallback():
    html = """<html><head>
      <meta name="citation_author" content="Dr. Samira Patel">
      <meta name="citation_publication_date" content="2025/09/03">
    </head><body><h1>Research Note</h1></body></html>"""
    meta = extract_metadata(html, "https://journal.example/paper")
    assert meta["author"] == "Dr. Samira Patel"
    assert meta["published_date"] == "2025-09-03"

    html_ord = """<html><body><article><h1>Update</h1>
      <address>By Kofi Mensah</address>
      <p class="published-date">Nov 23rd, 2026</p>
      <p>Content body here.</p></article></body></html>"""
    meta2 = extract_metadata(html_ord, "https://news.example/story")
    assert meta2["author"] == "Kofi Mensah"
    assert meta2["published_date"] == "2026-11-23"

    meta3 = extract_metadata("<html><body><h1>Post</h1></body></html>", "https://blog.example/2024/05/19/hello")
    assert meta3["published_date"] == "2024-05-19"


def test_semantic_extractor_caches_product_and_article():
    html = """<html><head><script type="application/ld+json">
      {"@type":"Product","name":"Desk Lamp","offers":{"price":"29.99","priceCurrency":"USD"}}
    </script></head><body><h1>Desk Lamp</h1></body></html>"""
    sem = SemanticExtractor(html, "https://shop.example/lamp")
    p1 = sem.extract_product()
    p2 = sem.extract_all()["product"]
    assert p1 is p2 and p1.price == 29.99


def test_soft_block_detection_200_challenge_shells():
    dd = "<html><head><title>Verify</title></head><body><script src='https://geo.captcha-delivery.com/captcha.js'></script></body></html>"
    px = "<html><body><div id='px-captcha'></div><script src='/px.js'></script></body></html>"
    normal = "<html><body>" + ("<p>Real article content.</p>" * 120) + "<script src='https://geo.captcha-delivery.com/x.js'></script></body></html>"
    assert detect_defense(200, {}, dd) == DefenseSystem.DATADOME
    assert detect_defense(200, {}, px) == DefenseSystem.PERIMETERX
    assert detect_defense(200, {}, normal) == DefenseSystem.NONE


@pytest.mark.asyncio
async def test_domain_throttle_pause():
    throttle = DomainThrottle(per_domain_concurrency=2)
    throttle.pause("slow.example", 0.08)
    t0 = time.monotonic()
    await throttle.acquire("slow.example")
    throttle.release("slow.example")
    assert time.monotonic() - t0 >= 0.06


@pytest.mark.asyncio
async def test_client_conditional_etag_cache_and_batch():
    calls = []

    class MockFetcher:
        async def fetch(self, url, *, headers=None, **kwargs):
            calls.append((url, dict(headers or {})))
            if (headers or {}).get("If-None-Match") == '"v1"':
                return FetchResult(url=url, status_code=304, html="", headers={})
            return FetchResult(url=url, status_code=200, html=f"<html><title>{url}</title><body><h1>{url}</h1></body></html>",
                               headers={"ETag": '"v1"'})

        async def close(self):
            pass

    async with OmniClient(retries=0, cache_responses=True) as client:
        client._fetchers["http"] = MockFetcher()
        r1 = await client.fetch("https://ex.test/a", tier=1)
        r2 = await client.fetch("https://ex.test/a", tier=1)
        assert r1.status_code == 200 and r2.status_code == 200
        assert "<h1>https://ex.test/a</h1>" in r2.html
        assert calls[1][1].get("If-None-Match") == '"v1"'

        many = await client.scrape_many(["https://ex.test/1", "https://ex.test/2"], concurrency=2, tier=1)
        assert [m.title for m in many] == ["https://ex.test/1", "https://ex.test/2"]
        streamed = [u async for u, _ in client.iter_scrape(["https://ex.test/3", "https://ex.test/4"], concurrency=2, tier=1)]
        assert set(streamed) == {"https://ex.test/3", "https://ex.test/4"}


def test_selector_extract_schema_and_listings():
    html = """<html><body>
      <div class="pdp">
        <h1>Ceramic Mug</h1>
        <span class="price">$18.50</span>
        <span class="stock">In Stock</span>
        <ul class="tags"><li>home</li><li>kitchen</li></ul>
      </div>
      <div class="grid">
        <div class="card"><a href="/p/1"><h3>Cup A</h3></a><span class="price">$9.99</span><img src="/1.jpg"></div>
        <div class="card"><a href="/p/2"><h3>Cup B</h3></a><span class="price">$12.00</span><img src="/2.jpg"></div>
        <div class="card"><a href="/p/3"><h3>Cup C</h3></a><span class="price">$15.00</span><img src="/3.jpg"></div>
      </div>
    </body></html>"""
    sel = Selector(html, url="https://shop.example/")
    data = sel.extract({
        "title": "div.pdp h1::text",
        "price": {"selector": "div.pdp .price::text", "type": "price"},
        "in_stock": {"selector": "div.pdp .stock::text", "type": "bool"},
        "tags": {"selector": "ul.tags li::text", "all": True},
        "missing": {"selector": ".nope::text", "default": "N/A"},
    })
    assert data == {"title": "Ceramic Mug", "price": 18.5, "in_stock": True, "tags": ["home", "kitchen"], "missing": "N/A"}

    with pytest.raises(SchemaValidationError):
        sel.extract({"req": {"selector": ".nope::text", "required": True}})

    items = extract_listings(html, "https://shop.example/")
    assert len(items) == 3
    assert items[0] == {"title": "Cup A", "url": "https://shop.example/p/1", "price": 9.99, "currency": "USD", "image": "https://shop.example/1.jpg"}


def test_optional_selectolax_backend():
    pytest.importorskip("selectolax")
    html = "<html><body><div class='card'><h3>Lamp</h3><a href='/p/1'>Buy</a></div></body></html>"
    sel = Selector(html, url="https://shop.example/", backend="selectolax")
    assert sel.css("div.card h3::text").get() == "Lamp"
    assert sel.css("div.card a::attr(href)").get() == "/p/1"
    assert sel.xpath("//h3/text()").get() == "Lamp"
