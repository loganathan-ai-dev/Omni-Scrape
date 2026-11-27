"""Unit tests for crawler components and storage."""

import asyncio
import tempfile
from pathlib import Path
import pytest
from omniscrape.crawler.autothrottle import AutoThrottle
from omniscrape.crawler.checkpoint import CheckpointManager
from omniscrape.crawler.dedup import URLFilter
from omniscrape.models import Product
from omniscrape.storage.duckdb_backend import DuckDBStorage
from omniscrape.storage.jsonl_backend import JSONLStorage


def test_url_filter():
    dedup = URLFilter()
    assert dedup.add("https://example.com/p1") is True
    assert dedup.add("https://example.com/p1") is False
    assert dedup.add("https://example.com/p1/") is False
    assert dedup.add("https://example.com/p1#heading") is False
    assert dedup.add("https://example.com/p2") is True


def test_checkpoint_manager():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    cp = CheckpointManager("test_spider", db_path=db_path)
    assert cp.is_completed("https://example.com/item1") is False

    cp.mark_completed("https://example.com/item1")
    assert cp.is_completed("https://example.com/item1") is True
    assert "https://example.com/item1" in cp.get_all_completed()


@pytest.mark.asyncio
async def test_autothrottle_adaptation():
    throttle = AutoThrottle(target_latency_sec=1.0, min_delay_sec=0.1, max_delay_sec=5.0)

    # Fast responses should lower delay
    for _ in range(5):
        throttle.record_latency(200.0)
    assert throttle._current_delay <= 0.2

    # High latency should increase delay
    for _ in range(5):
        throttle.record_latency(3000.0)
    assert throttle._current_delay > 0.3


@pytest.mark.asyncio
async def test_jsonl_storage():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        file_path = f.name

    storage = JSONLStorage(file_path=file_path)
    prod = Product(url="https://example.com/prod1", title="Test Item", price=19.99)
    await storage.write(prod)
    await storage.close()

    content = Path(file_path).read_text(encoding="utf-8")
    assert "Test Item" in content
    assert "19.99" in content


@pytest.mark.asyncio
async def test_duckdb_storage():
    duckdb = pytest.importorskip("duckdb")
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        db_path = f.name
    import os
    if os.path.exists(db_path):
        os.unlink(db_path)

    storage = DuckDBStorage(db_path=db_path, table_name="test_products")
    prod = Product(url="https://example.com/prod2", title="DuckDB Item", price=45.0)
    await storage.write(prod)
    await storage.close()

    con = duckdb.connect(db_path)
    res = con.execute("SELECT title, price FROM test_products").fetchall()
    con.close()
    assert len(res) == 1
    assert res[0][0] == "DuckDB Item"
    assert float(res[0][1]) == 45.0
