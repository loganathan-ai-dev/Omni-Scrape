"""Dead letter queue storing failed requests and errors (SQLite)."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Optional


class DeadLetterQueue:
    """Persists failed requests for analysis or later replay."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            cache_dir = Path.home() / ".omniscrape"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "dead_letters.db")
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def record(self, url: str, error_type: str, message: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO dead_letters (url, error_type, error_message) VALUES (?, ?, ?)",
                (url, error_type, message),
            )

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT url, error_type, error_message, failed_at FROM dead_letters ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(zip(("url", "error_type", "error_message", "failed_at"), r)) for r in rows]

    def clear(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM dead_letters")
