"""Live suite: polite crawl of public scraping sandboxes (books/quotes.toscrape.com)."""

import time
from typing import Any

TARGETS = [
    {"name": "books", "start_url": "https://books.toscrape.com/", "max_pages": 40},
    {"name": "quotes", "start_url": "https://quotes.toscrape.com/", "max_pages": 20},
]


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    import tempfile

    t0 = time.perf_counter()
    pages = adapter.crawl(params["start_url"], params["max_pages"], params["concurrency"], True,
                          tempfile.mkdtemp(prefix="live-"))
    return {"seconds": time.perf_counter() - t0, "pages": pages}


def run(ctx) -> dict[str, Any]:
    from benchmarks.runner import tool_summary

    tools: dict[str, Any] = {}
    for tool in ctx.tools_for("live"):
        per_target = {}
        summaries = []
        for target in TARGETS:
            ctx.say(f"  live: {tool} -> {target['name']}")
            res = ctx.run_worker(tool, "live", {**target, "concurrency": 2}, timeout=600, tag=target["name"])
            summaries.append(tool_summary(res))
            if res.get("ok"):
                pages = res["data"]["pages"]
                secs = res["data"]["seconds"]
                ok = sum(1 for p in pages if 200 <= int(p.get("status") or 0) < 300)
                capped = min(len(pages), target["max_pages"])
                per_target[target["name"]] = {
                    "pages": len(pages), "ok_ratio": round(ok / len(pages), 3) if pages else 0.0,
                    "seconds": round(secs, 2), "pages_per_sec": round(capped / secs, 2) if secs else 0.0,
                    "titled": sum(1 for p in pages if p.get("title")),
                }
            else:
                per_target[target["name"]] = {"error": res.get("error")}
        ok = [s for s in summaries if s.get("ok")]
        entry = dict(ok[0] if ok else summaries[-1])
        entry["ok"] = bool(ok)
        entry["peak_rss_mb"] = max((s.get("peak_rss_mb") or 0) for s in summaries)
        entry["targets"] = per_target
        tools[tool] = entry
    return {"suite": "live", "params": {"targets": TARGETS, "concurrency": 2, "obey_robots": True},
            "notes": ["Single polite run per tool and target; network conditions vary between runs.",
                      "Tools may overshoot max_pages slightly because in-flight requests finish."],
            "tools": tools}
