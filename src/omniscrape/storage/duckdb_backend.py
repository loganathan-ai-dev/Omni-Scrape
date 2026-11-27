"""DuckDB local analytical columnar storage."""

import json
from typing import Any, Sequence

from omniscrape.observability.logging import get_logger
from omniscrape.storage.base import BaseStorage

logger = get_logger("omniscrape.storage.duckdb")


def _to_cell(value: Any) -> Any:
    """Every column is VARCHAR: keep None as NULL, JSON-encode containers, ISO-format dates."""
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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
            sanitized = {k: _to_cell(v) for k, v in d.items()}
            rows.append(sanitized)

        if not rows:
            return

        # DuckDB identifiers are case-insensitive: "Title" and "title" are the same column. Map every
        # record key onto one canonical spelling (the table's existing one, else the first seen).
        table = self.table_name
        existing_cols = [r[1] for r in con.execute(
            "SELECT column_name, column_name FROM information_schema.columns WHERE table_name = ?", [table]
        ).fetchall()]
        canonical: dict[str, str] = {c.lower(): c for c in existing_cols}
        for row in rows:
            for key in row:
                canonical.setdefault(key.lower(), key)

        if not existing_cols:
            first = list(dict.fromkeys(canonical[k.lower()] for row in rows for k in row))
            col_defs = ", ".join(f'"{col}" VARCHAR' for col in first)
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
            existing_cols = first
        # Schema evolution: a later record may carry keys the table does not have yet.
        known = {c.lower() for c in existing_cols}
        for col in dict.fromkeys(canonical[k.lower()] for row in rows for k in row):
            if col.lower() not in known:
                con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" VARCHAR')
                known.add(col.lower())

        # Merge each row's keys onto the canonical names (later duplicates of a key win).
        merged_rows = []
        for row in rows:
            merged: dict[str, Any] = {}
            for key, value in row.items():
                merged[canonical[key.lower()]] = value
            merged_rows.append(merged)
        cols = list(dict.fromkeys(k for row in merged_rows for k in row))
        placeholders = ", ".join(["?"] * len(cols))
        quoted_cols = ", ".join(f'"{col}"' for col in cols)
        insert_sql = f'INSERT INTO "{table}" ({quoted_cols}) VALUES ({placeholders})'
        con.executemany(insert_sql, [[row.get(col) for col in cols] for row in merged_rows])

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        if self._con:
            self._con.close()
            self._con = None
