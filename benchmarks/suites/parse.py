"""Parse suite: parse + CSS select + text extraction throughput and memory (parsers only)."""

import time
from typing import Any

from benchmarks.common import load_corpus, read_text, summarize

GENERIC_SELECTORS = ["a[href]", "p", "ul > li", "img[src]", "div > span", "h1, h2, h3"]


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    docs = [(read_text(d["html_path"]), d["selectors"], d["expected"]) for d in params["docs"]]
    total_bytes = sum(len(h.encode("utf-8")) for h, _, _ in docs)
    for html, sels, _ in docs[: params.get("warmup_docs", 5)]:
        adapter.select_texts(html, sels)

    matches = checks = 0
    mismatches = []
    for i, (html, sels, expected) in enumerate(docs):
        out = adapter.select_texts(html, sels)
        for sel, texts, exp in zip(sels, out, expected):
            checks += 1
            if len(texts) == exp:
                matches += 1
            elif len(mismatches) < 20:
                mismatches.append({"doc": params["docs"][i]["id"], "selector": sel, "got": len(texts), "expected": exp})

    passes = []
    for _ in range(params["repeats"]):
        t0 = time.perf_counter()
        for html, sels, _ in docs:
            adapter.select_texts(html, sels)
        passes.append(time.perf_counter() - t0)
    return {"pass_seconds": passes, "docs": len(docs), "bytes": total_bytes,
            "count_accuracy": matches / checks if checks else 0.0, "mismatches": mismatches}


def run(ctx) -> dict[str, Any]:
    import lxml.html

    docs = []
    for d in load_corpus():
        html = read_text(d["html_path"])
        root = lxml.html.fromstring(html)
        sels, expected = [], []
        if d["truth"]["type"] == "listing":
            for key, sel in d["truth"]["selectors"].items():
                sels.append(sel)
                expected.append(d["truth"]["expected_counts"][key])
        for sel in GENERIC_SELECTORS:
            sels.append(sel)
            expected.append(len(root.cssselect(sel)))  # reference: lxml/libxml2
        docs.append({"id": d["id"], "html_path": d["html_path"], "selectors": sels, "expected": expected})
    if ctx.quick:
        docs = docs[::4]
    params = {"docs": docs, "repeats": 2 if ctx.quick else ctx.repeats, "warmup_docs": 5}

    from benchmarks.runner import tool_summary

    tools: dict[str, Any] = {}
    for tool in ctx.tools_for("parse"):
        ctx.say(f"  parse: {tool}")
        res = ctx.run_worker(tool, "parse", params)
        entry = tool_summary(res)
        if res.get("ok"):
            data = res["data"]
            stats = summarize(data["pass_seconds"])
            entry.update({
                "docs_per_sec": round(data["docs"] / stats["median"], 2),
                "mb_per_sec": round(data["bytes"] / 1024 / 1024 / stats["median"], 2),
                "pass_seconds": {k: round(v, 4) if isinstance(v, float) else v for k, v in stats.items()},
                "count_accuracy": round(data["count_accuracy"], 4),
                "mismatches": data["mismatches"][:8],
            })
        tools[tool] = entry
    return {"suite": "parse", "params": {"docs": len(docs), "repeats": params["repeats"],
                                         "selectors_per_doc": "4 ground-truth (listings) + 6 generic"},
            "notes": ["Expected counts for generic selectors come from lxml (libxml2); html5 parsers may "
                      "legitimately differ on malformed markup, so count_accuracy is agreement, not truth, for those."],
            "tools": tools}
