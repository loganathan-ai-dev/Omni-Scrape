"""Storage module exports."""

from omniscrape.storage.base import BaseStorage
from omniscrape.storage.duckdb_backend import DuckDBStorage
from omniscrape.storage.jsonl_backend import JSONLStorage

__all__ = [
    "BaseStorage",
    "DuckDBStorage",
    "JSONLStorage",
]
