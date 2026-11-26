"""Dead letter queue storing failed requests and errors."""

import sqlite3
from pathlib import Path
from typing import Optional


class DeadLetterQueue:
    """Persists failed requests for analysis or subsequent replay."""

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            cache_dir = Path.home() / ".omniscrape"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / "dead_letters.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record(self, url: str, error_type: str, message: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO dead_letters (url, error_type, error_message)
                VALUES (?, ?, ?)
            """, (url, error_type, message))
            conn.commit()
