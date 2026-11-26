"""Worker process: runs ONE (tool, suite) job inside the tool's environment.

    python -m benchmarks.worker job.json result.json

Peak memory is sampled from the process tree (worker + children such as browsers) with psutil,
which captures C-extension allocations that tracemalloc misses.
"""

import json
import os
import platform
import sys
import threading
import time
import traceback
from importlib import import_module
from typing import Any


class RssSampler(threading.Thread):
    def __init__(self, interval: float = 0.02):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0.0
        self.available = True
        self._stop_event = threading.Event()
        try:
            import psutil

            self._proc = psutil.Process(os.getpid())
        except Exception:
            self.available = False

    def current(self) -> float:
        if not self.available:
            return 0.0
        try:
            total = self._proc.memory_info().rss
            for child in self._proc.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except Exception:
                    pass
            return total / (1024 * 1024)
        except Exception:
            return 0.0

    def run(self) -> None:
        while not self._stop_event.is_set():
            self.peak = max(self.peak, self.current())
            time.sleep(self.interval)

    def stop(self) -> float:
        self._stop_event.set()
        self.peak = max(self.peak, self.current())
        return self.peak


def main(job_path: str, out_path: str) -> None:
    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    sampler = RssSampler()
    sampler.start()
    result: dict[str, Any] = {"tool": job["tool"], "suite": job["suite"], "ok": False,
                              "python": platform.python_version(), "memory_sampled": sampler.available}
    try:
        from benchmarks.adapters import load_adapter

        adapter = load_adapter(job["tool"])
        t0 = time.perf_counter()
        adapter.prepare()
        result["import_seconds"] = round(time.perf_counter() - t0, 4)
        result["version"] = adapter.version()
        result["rss_after_import_mb"] = round(sampler.current(), 1)
        suite = import_module(f"benchmarks.suites.{job['suite']}")
        result["data"] = suite.worker(adapter, job["params"])
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=20)
    finally:
        result["peak_rss_mb"] = round(sampler.stop(), 1)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, default=str)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
