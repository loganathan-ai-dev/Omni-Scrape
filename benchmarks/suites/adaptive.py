"""Adaptive suite: can a tool re-find previously selected elements after a redesign?"""

import json
import tempfile
import time
from collections import defaultdict
from typing import Any

from benchmarks.common import norm_text, read_text


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    with open(params["cases_path"], encoding="utf-8") as f:
        pages = json.load(f)
    out = []
    for page in pages:
        with tempfile.TemporaryDirectory(prefix="adaptive-", ignore_cleanup_errors=True) as storage:
            adapter.adaptive_save(read_text(page["html_path"]), page["url"], page["selectors"], storage)
            for variant in page["variants"]:
                html = read_text(variant["html_path"])
                t0 = time.perf_counter()
                try:
                    found, err = adapter.adaptive_find(html, page["url"], page["selectors"], storage), None
                except Exception as exc:
                    found, err = {}, f"{type(exc).__name__}: {exc}"
                out.append({"page": page["id"], "mutation": variant["mutation"],
                            "found": {k: norm_text(v) if v is not None else None for k, v in found.items()},
                            "ms": (time.perf_counter() - t0) * 1000, "error": err})
    return {"results": out}


def run(ctx) -> dict[str, Any]:
    from benchmarks.corpus.adaptive_cases import ADAPTIVE_DIR, build

    cases_path = ADAPTIVE_DIR / "cases.json"
    if not cases_path.exists():
        ctx.say("  building adaptive cases")
        build()
    pages = json.loads(cases_path.read_text(encoding="utf-8"))
    if ctx.quick:
        pages = pages[::3]
        cases_path = ctx.out_dir / "adaptive_cases_quick.json"
        cases_path.write_text(json.dumps(pages), encoding="utf-8")
    split_of = {p["id"]: p["split"] for p in pages}
    expected = {(p["id"], v["mutation"], name): t for p in pages for v in p["variants"] for name, t in v["targets"].items()}

    from benchmarks.runner import tool_summary

    tools: dict[str, Any] = {}
    for tool in ctx.tools_for("adaptive"):
        ctx.say(f"  adaptive: {tool}")
        res = ctx.run_worker(tool, "adaptive", {"cases_path": str(cases_path)})
        entry = tool_summary(res)
        if res.get("ok"):
            groups: dict[str, dict[str, int]] = defaultdict(lambda: {"recovered": 0, "wrong": 0, "missed": 0, "n": 0})
            still_works = 0
            ms = []
            for r in res["data"]["results"]:
                ms.append(r["ms"])
                for name, got in r["found"].items():
                    t = expected[(r["page"], r["mutation"], name)]
                    if t["selector_still_works"]:
                        still_works += 1
                        continue
                    outcome = "missed" if got is None else ("recovered" if got == t["expected"] else "wrong")
                    for g in ("all", split_of[r["page"]], f"mutation:{r['mutation']}"):
                        groups[g][outcome] += 1
                        groups[g]["n"] += 1
            entry["groups"] = {g: {**c, "recovery_rate": round(c["recovered"] / c["n"], 4) if c["n"] else 0.0}
                               for g, c in sorted(groups.items())}
            entry["selector_still_works"] = still_works
            entry["ms_per_page_variant"] = round(sum(ms) / max(1, len(ms)), 3)
            entry["errors"] = [r["error"] for r in res["data"]["results"] if r.get("error")][:5]
        tools[tool] = entry
    return {"suite": "adaptive", "params": {"pages": len(pages)},
            "notes": ["Only cases where the original selector breaks are scored.",
                      "recovered = correct element; wrong = a different element returned (silent data error); "
                      "missed = nothing returned."],
            "tools": tools}
