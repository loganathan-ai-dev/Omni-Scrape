"""Crawl suite: full crawl of the local test site; ground truth measured server-side."""

import json
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from typing import Any

from benchmarks.common import REPO_ROOT


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    import tempfile

    workdir = tempfile.mkdtemp(prefix="crawl-")
    t0 = time.perf_counter()
    pages = adapter.crawl(params["start_url"], params["max_pages"], params["concurrency"], params["obey_robots"], workdir)
    return {"seconds": time.perf_counter() - t0, "pages": pages}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SiteServer:
    def __init__(self, pages: int = 300, latency: tuple[float, float] = (5.0, 25.0)):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "benchmarks.site.server", "--port", str(self.port), "--pages", str(pages),
             "--latency-min", str(latency[0]), "--latency-max", str(latency[1])],
            cwd=str(REPO_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                self.get("/__meta")
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("test site did not start")

    def get(self, path: str) -> dict[str, Any]:
        with urllib.request.urlopen(self.base + path, timeout=5) as r:
            return json.loads(r.read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def run(ctx) -> dict[str, Any]:
    from benchmarks.runner import tool_summary

    n_pages = 120 if ctx.quick else 300
    repeats = 1 if ctx.quick else min(3, ctx.repeats)
    server = SiteServer(pages=n_pages)
    try:
        meta = server.get("/__meta")
        params = {"start_url": server.base + "/", "max_pages": meta["expected_allowed"] + 50,
                  "concurrency": 8, "obey_robots": True}
        tools: dict[str, Any] = {}
        for tool in ctx.tools_for("crawl"):
            runs = []
            entry: dict[str, Any] = {}
            for i in range(repeats):
                ctx.say(f"  crawl: {tool} run {i + 1}/{repeats}")
                server.get("/__reset")
                res = ctx.run_worker(tool, "crawl", params, timeout=900, tag=f"run{i + 1}")
                entry = tool_summary(res)
                if not res.get("ok"):
                    break
                stats = server.get("/__stats")
                secs = res["data"]["seconds"]
                runs.append({**stats, "seconds": round(secs, 3), "peak_rss_mb": res.get("peak_rss_mb"),
                             "pages_per_sec": round(stats["unique_allowed_fetched"] / secs, 2) if secs else 0.0,
                             "pages_returned": len(res["data"]["pages"])})
            if runs:
                med = sorted(runs, key=lambda r: r["seconds"])[len(runs) // 2]
                entry.update({k: med[k] for k in med})
                entry["peak_rss_mb"] = max(r["peak_rss_mb"] or 0 for r in runs)
                entry["seconds_all_runs"] = [r["seconds"] for r in runs]
                entry["pages_per_sec_stdev"] = round(statistics.pstdev([r["pages_per_sec"] for r in runs]), 2)
            tools[tool] = entry
    finally:
        server.stop()
    return {"suite": "crawl",
            "params": {"site_pages": n_pages, "expected_allowed": meta["expected_allowed"], "concurrency": 8,
                       "latency_ms": "5-25 per request", "repeats": repeats, "obey_robots": True},
            "notes": ["Coverage, duplicates and robots violations are counted by the server, not by the tool.",
                      "Flaky pages return HTTP 500 once; recovered = fetched again successfully.",
                      "Crawl4AI drives a real browser (its default), so it is expected to be slower."],
            "tools": tools}
