"""Unit tests for top-level OmniScrape API and CLI."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest
import omniscrape
from omniscrape.cli.main import cli
from omniscrape.models import FetchResult, PageClassification, PageType


@pytest.mark.asyncio
async def test_scrape_api_mocked():
    sample_html = """
    <html>
        <head><title>Mocked E-Store</title></head>
        <body>
            <h1>Featured Gaming Chair</h1>
            <p>Ergonomic high-back office chair with lumbar support.</p>
            <a href="/cart">Cart</a>
        </body>
    </html>
    """

    mock_result = FetchResult(
        url="https://fake-store.com/item/1",
        status_code=200,
        html=sample_html,
        fetcher_tier=1,
    )

    with patch("omniscrape.fetchers.http.FastFetcher.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_result
        res = await omniscrape.scrape("https://fake-store.com/item/1", tier=1)

        assert res.url == "https://fake-store.com/item/1"
        assert res.title == "Mocked E-Store"
        assert "# Featured Gaming Chair" in res.markdown
        assert "https://fake-store.com/cart" in res.links  # links are absolute since 0.2.0


def test_version_exported():
    assert hasattr(omniscrape, "__version__")
    assert omniscrape.__version__ == "0.1.0"
