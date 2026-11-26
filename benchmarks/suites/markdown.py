"""Markdown suite: main-content Markdown quality on article pages."""

import json
import statistics
import time
from collections import defaultdict
from typing import Any

from benchmarks.common import CORPUS_DIR, leakage, load_corpus, read_text, rouge_l, token_prf, words


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    docs = params["docs"]
    if docs:
        adapter.markdown(read_text(docs[0]["html_path"]), docs[0]["url"])  # warmup
    out = []
    for d in docs:
        html = read_text(d["html_path"])
        t0 = time.perf_counter()
        try:
            md, err = adapter.markdown(html, d["url"]), None
        except Exception as exc:
            md, err = "", f"{type(exc).__name__}: {exc}"
        out.append({"id": d["id"], "output": md, "ms": (time.perf_counter() - t0) * 1000, "error": err})
    return {"results": out}


def run(ctx) -> dict[str, Any]:
    vocab = json.loads((CORPUS_DIR / "vocab.json").read_text(encoding="utf-8"))["boilerplate"]
    docs = []
    for d in load_corpus(kind="article"):
        t = d["truth"]
        docs.append({"id": d["id"], "split": d["split"], "html_path": d["html_path"], "url": t["url"],
                     "main_text": t["main_text"], "synthetic": not t.get("handwritten")})
    if ctx.quick:
        docs = docs[::3]
    from benchmarks.runner import tool_summary

    tools: dict[str, Any] = {}
    for tool in ctx.tools_for("markdown"):
        ctx.say(f"  markdown: {tool}")
        res = ctx.run_worker(tool, "markdown", {"docs": [{k: d[k] for k in ("id", "html_path", "url")} for d in docs]})
        entry = tool_summary(res)
        if res.get("ok"):
            by_id = {r["id"]: r for r in res["data"]["results"]}
            groups: dict[str, list[dict[str, float]]] = defaultdict(list)
            samples = {}
            for d in docs:
                r = by_id[d["id"]]
                p, rec, f1 = token_prf(r["output"], d["main_text"])
                m = {"precision": p, "recall": rec, "f1": f1, "rouge_l": rouge_l(r["output"], d["main_text"]),
                     "out_words": len(words(r["output"])), "ref_words": len(words(d["main_text"])), "ms": r["ms"]}
                if d["synthetic"]:
                    m["leakage"] = leakage(r["output"], vocab)
                for g in (d["split"], "all", "handwritten" if not d["synthetic"] else "synthetic"):
                    groups[g].append(m)
                if d["id"] in ("bem_article_00", "hand_article_news"):
                    samples[d["id"]] = r["output"][:1500]
            entry["groups"] = {
                g: {k: round(statistics.mean(m[k] for m in ms if k in m), 4)
                    for k in ("precision", "recall", "f1", "rouge_l", "leakage", "out_words", "ref_words", "ms")
                    if any(k in m for m in ms)} | {"n": len(ms)}
                for g, ms in sorted(groups.items())
            }
            entry["samples"] = samples
            entry["errors"] = [r["error"] for r in res["data"]["results"] if r.get("error")][:5]
        tools[tool] = entry
    return {"suite": "markdown", "params": {"docs": len(docs)},
            "notes": ["Reference = exact main text (title + body). Precision/recall are multiset word overlaps.",
                      "Leakage = share of output words from the boilerplate vocabulary (synthetic pages only).",
                      "markdownify and html2text convert the whole page by design (baselines)."],
            "tools": tools}
