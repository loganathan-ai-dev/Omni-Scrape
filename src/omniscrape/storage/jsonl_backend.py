"""JSONL storage backend (one JSON object per line)."""

import json
from pathlib import Path
from typing import Any, Sequence

from omniscrape.storage.base import BaseStorage


class JSONLStorage(BaseStorage):
    """Appends records to a line-delimited JSON (JSONL) file.

    The file is opened lazily and line-buffered, so every record reaches the OS as soon as it is
    written (a crash loses nothing already written), and the object can be reused after ``close()``.
    """

    def __init__(self, file_path: str = "scraped_data.jsonl"):
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = None

    def _open(self):
        if self._file is None or self._file.closed:
            self._file = open(self.path, "a", encoding="utf-8", buffering=1)
        return self._file

    async def write(self, record: Any) -> None:
        if hasattr(record, "model_dump_json"):
            line = record.model_dump_json()
        elif hasattr(record, "model_dump"):
            line = json.dumps(record.model_dump(), default=str)
        elif isinstance(record, dict):
            line = json.dumps(record, default=str)
        else:
            line = json.dumps({"value": str(record)})

        self._open().write(line + "\n")

    async def write_batch(self, records: Sequence[Any]) -> None:
        for r in records:
            await self.write(r)

    async def flush(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.flush()

    async def close(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.flush()
            self._file.close()
        self._file = None
