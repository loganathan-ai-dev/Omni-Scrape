"""Render suite: JavaScript-rendered pages loaded in each tool's browser path (cold batch)."""

import time
from typing import Any


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    urls = params["urls"]
    t0 = time.perf_counter()
    pages = adapter.render(urls, params["concurrency"])
    seconds = time.perf_counter() - t0
    markers = params["markers"]
    ok = 0
    errors = []
    for page in pages:
        marker = markers.get(page["url"])
        if marker and marker in (page.get("html") or ""):
            ok += 1
        elif len(errors) < 5:
            errors.append({"url": page["url"], "status": page.get("status"), "error": page.get("error", "marker missing")})
    return {"seconds": seconds, "rendered_ok": ok, "total": len(urls), "returned": len(pages), "failures": errors}


def run(ctx) -> dict[str, Any]:
    from benchmarks.runner import tool_summary
    from benchmarks.suites.crawl import SiteServer

    n = 16 if ctx.quick else 60
    concurrency = 4
    server = SiteServer(pages=20, latency=(1.0, 3.0))
    try:
        urls = [f"{server.base}/js/{i}" for i in range(n)]
        markers = {u: f"Hydrated content for page {u.rsplit('/', 1)[1]}" for u in urls}
        tools: dict[str, Any] = {}
        for tool in ctx.tools_for("render"):
            ctx.say(f"  render: {tool}")
            res = ctx.run_worker(tool, "render", {"urls": urls, "markers": markers, "concurrency": concurrency}, timeout=900)
            entry = tool_summary(res)
            if res.get("ok"):
                d = res["data"]
                entry.update({"rendered_ok": d["rendered_ok"], "total": d["total"],
                              "success_rate": round(d["rendered_ok"] / d["total"], 4),
                              "seconds": round(d["seconds"], 2),
                              "pages_per_sec": round(d["rendered_ok"] / d["seconds"], 2) if d["seconds"] else 0.0,
                              "failures": d["failures"]})
            tools[tool] = entry
    finally:
        server.stop()
    return {"suite": "render", "params": {"pages": n, "concurrency": concurrency, "page": "inline-script hydration"},
            "notes": ["Cold batch: includes browser launch, so it measures what a one-off job costs.",
                      "Each tool uses its own default browser path (OmniScrape tier 2, Crawl4AI AsyncWebCrawler, "
                      "Scrapling AsyncStealthySession)."],
            "tools": tools}
