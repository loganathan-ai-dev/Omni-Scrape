"""JSONL / Parquet data lake storage backend."""

import json
from pathlib import Path
from typing import Any, Sequence
from omniscrape.storage.base import BaseStorage


class JSONLStorage(BaseStorage):
    """Appends records to a line-delimited JSON (JSONL) file."""

    def __init__(self, file_path: str = "scraped_data.jsonl"):
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a", encoding="utf-8")

    async def write(self, record: Any) -> None:
        if hasattr(record, "model_dump_json"):
            line = record.model_dump_json()
        elif hasattr(record, "model_dump"):
            line = json.dumps(record.model_dump(), default=str)
        elif isinstance(record, dict):
            line = json.dumps(record, default=str)
        else:
            line = json.dumps({"value": str(record)})

        self._file.write(line + "\n")

    async def write_batch(self, records: Sequence[Any]) -> None:
        for r in records:
            await self.write(r)
        self._file.flush()

    async def flush(self) -> None:
        self._file.flush()

    async def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()
