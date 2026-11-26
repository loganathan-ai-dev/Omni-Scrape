"""SQLite checkpoint state manager for pause/resume crawls."""

import sqlite3
from pathlib import Path
from typing import Optional, Set


class CheckpointManager:
    """Persists completed and pending URLs so crawls can resume after interruption."""

    def __init__(self, spider_name: str, db_path: Optional[str] = None):
        self.spider_name = spider_name
        if not db_path:
            cache_dir = Path.home() / ".omniscrape" / "checkpoints"
            cache_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(cache_dir / f"{spider_name}.db")

        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS completed_urls (
                    url TEXT PRIMARY KEY,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def is_completed(self, url: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM completed_urls WHERE url = ?", (url,))
            return cur.fetchone() is not None

    def mark_completed(self, url: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO completed_urls (url) VALUES (?)", (url,))
            conn.commit()

    def get_all_completed(self) -> Set[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT url FROM completed_urls")
            return {row[0] for row in cur.fetchall()}
