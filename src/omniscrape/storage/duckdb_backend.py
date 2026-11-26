"""DuckDB local analytical columnar storage."""

import json
from typing import Any, Optional, Sequence
from omniscrape.storage.base import BaseStorage
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.storage.duckdb")


class DuckDBStorage(BaseStorage):
    """Stores extracted scraping records into DuckDB with automatic schema creation."""

    def __init__(self, db_path: str = "omniscrape.duckdb", table_name: str = "scraped_data"):
        self.db_path = db_path
        self.table_name = table_name
        self._con = None

    def _get_con(self):
        if self._con is None:
            import duckdb
            self._con = duckdb.connect(self.db_path)
        return self._con

    async def write(self, record: Any) -> None:
        await self.write_batch([record])

    async def write_batch(self, records: Sequence[Any]) -> None:
        if not records:
            return

        con = self._get_con()
        rows = []
        for r in records:
            if hasattr(r, "model_dump"):
                d = r.model_dump()
            elif isinstance(r, dict):
                d = dict(r)
            else:
                d = {"value": str(r)}
            # Serialize nested structures to JSON strings
            sanitized = {k: json.dumps(v) if isinstance(v, (dict, list)) else (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}
            rows.append(sanitized)

        if not rows:
            return

        cols = list(rows[0].keys())
        # Ensure table exists
        col_defs = ", ".join([f'"{col}" VARCHAR' for col in cols])
        con.execute(f'CREATE TABLE IF NOT EXISTS "{self.table_name}" ({col_defs})')

        # Insert rows
        placeholders = ", ".join(["?"] * len(cols))
        quoted_cols = ", ".join([f'"{col}"' for col in cols])
        insert_sql = f'INSERT INTO "{self.table_name}" ({quoted_cols}) VALUES ({placeholders})'
        data_tuples = [[row.get(col) for col in cols] for row in rows]
        con.executemany(insert_sql, data_tuples)

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        if self._con:
            self._con.close()
            self._con = None
