"""Unit tests for crawler components and storage."""

import tempfile
from pathlib import Path

import pytest

from omniscrape.models import Product
from omniscrape.storage.duckdb_backend import DuckDBStorage
from omniscrape.storage.jsonl_backend import JSONLStorage


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
