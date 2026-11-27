"""Unit tests for zero-config semantic data extraction."""

from omniscrape.parsers.semantic import SemanticExtractor

PRODUCT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Awesome Wireless Headphones" />
    <meta property="og:description" content="Noise-cancelling bluetooth headphones." />
    <script type="application/ld+json">
    {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": "Awesome Wireless Headphones",
        "image": "https://example.com/headphones.jpg",
        "description": "Noise-cancelling bluetooth headphones.",
        "sku": "HEADPHONE-101",
        "brand": {
            "@type": "Brand",
            "name": "AudioTech"
        },
        "offers": {
            "@type": "Offer",
            "priceCurrency": "USD",
            "price": "99.99",
            "availability": "https://schema.org/InStock"
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "4.6",
            "reviewCount": "125"
        }
    }
    </script>
</head>
<body>
    <h1>Awesome Wireless Headphones</h1>
</body>
</html>
"""


def test_extract_json_ld_product():
    extractor = SemanticExtractor(PRODUCT_HTML, url="https://example.com/item")
    prod = extractor.extract_product()

    assert prod is not None
    assert prod.title == "Awesome Wireless Headphones"
    assert prod.price == 99.99
    assert prod.currency == "USD"
    assert prod.brand == "AudioTech"
    assert prod.sku == "HEADPHONE-101"
    assert prod.rating == 4.6
    assert prod.review_count == 125
    assert prod.in_stock is True
    assert prod.images == ["https://example.com/headphones.jpg"]


def test_extract_opengraph():
    extractor = SemanticExtractor(PRODUCT_HTML)
    og = extractor.extract_opengraph()
    assert og.get("og:title") == "Awesome Wireless Headphones"
    assert "Noise-cancelling" in og.get("og:description", "")
