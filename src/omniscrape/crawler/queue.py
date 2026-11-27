"""Priority request queue with fingerprint dedup and optional SQLite persistence (pause/resume).

Higher ``priority`` is served first; ties are FIFO. With a ``path``, every request and its state
(pending / done / failed) is stored, so an interrupted crawl resumes with nothing lost or repeated.
"""

import heapq
import itertools
import json
import sqlite3
import time
from typing import Optional

from omniscrape.crawler.spider import Request


class RequestQueue:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._heap: list[tuple[int, int, str]] = []
        self._requests: dict[str, Request] = {}
        self._seen: set[str] = set()
        self._counter = itertools.count()
        self._conn: Optional[sqlite3.Connection] = None
        if path:
            self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("""CREATE TABLE IF NOT EXISTS requests (
                fp TEXT PRIMARY KEY, url TEXT, method TEXT, priority INTEGER, depth INTEGER,
                callback TEXT, meta TEXT, headers TEXT, state TEXT, seq INTEGER, updated REAL, tier TEXT)""")
            columns = {row[1] for row in self._conn.execute("PRAGMA table_info(requests)")}
            if "tier" not in columns:  # queue files written by older versions
                self._conn.execute("ALTER TABLE requests ADD COLUMN tier TEXT")
            self._load()

    # ------------------------------------------------------------------ persistence
    def _load(self) -> None:
        assert self._conn is not None
        rows = self._conn.execute("SELECT fp, url, method, priority, depth, callback, meta, headers, state, tier "
                                  "FROM requests ORDER BY seq").fetchall()
        for fp, url, method, priority, depth, callback, meta, headers, state, tier in rows:
            self._seen.add(fp)
            if state == "pending":
                req = Request(url=url, method=method, priority=priority, depth=depth,
                              meta=json.loads(meta or "{}"), headers=json.loads(headers or "{}"),
                              tier=json.loads(tier) if tier else None)
                req.callback_name = callback
                self._push(req, fp)

    def has_unfinished(self) -> bool:
        return bool(self._heap)

    def reset(self) -> None:
        """Forget everything (start a fresh crawl)."""
        self._heap.clear()
        self._requests.clear()
        self._seen.clear()
        if self._conn is not None:
            self._conn.execute("DELETE FROM requests")

    def _save(self, fp: str, req: Request, state: str) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO requests (fp, url, method, priority, depth, callback, meta, headers, state, seq, updated, tier) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fp) DO UPDATE SET state=excluded.state, updated=excluded.updated",
            (fp, req.url, req.method, req.priority, req.depth, getattr(req, "callback_name", None),
             json.dumps(req.meta, default=str), json.dumps(req.headers), state, next(self._counter), time.time(),
             json.dumps(req.tier) if req.tier is not None else None),
        )

    def _set_state(self, fp: str, state: str) -> None:
        if self._conn is not None:
            self._conn.execute("UPDATE requests SET state=?, updated=? WHERE fp=?", (state, time.time(), fp))

    # ------------------------------------------------------------------ queue ops
    def _push(self, req: Request, fp: str) -> None:
        self._requests[fp] = req
        heapq.heappush(self._heap, (-req.priority, next(self._counter), fp))

    def add(self, req: Request) -> bool:
        """Queue a request; returns False if an equivalent request was already seen."""
        fp = req.fingerprint()
        if fp in self._seen and not req.dont_filter:
            return False
        self._seen.add(fp)
        self._save(fp, req, "pending")
        self._push(req, fp)
        return True

    def pop(self) -> Optional[tuple[str, Request]]:
        while self._heap:
            _, _, fp = heapq.heappop(self._heap)
            req = self._requests.pop(fp, None)
            if req is not None:
                return fp, req
        return None

    def mark_done(self, fp: str) -> None:
        self._set_state(fp, "done")

    def mark_failed(self, fp: str) -> None:
        self._set_state(fp, "failed")

    def __len__(self) -> int:
        return len(self._heap)

    def counts(self) -> dict[str, int]:
        if self._conn is None:
            return {"pending": len(self._heap)}
        rows = self._conn.execute("SELECT state, COUNT(*) FROM requests GROUP BY state").fetchall()
        return {state: n for state, n in rows}

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass
