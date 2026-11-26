"""Extract suite: zero-config field extraction accuracy (no per-site selectors)."""

import re
import time
from collections import defaultdict
from typing import Any, Optional

from benchmarks.common import load_corpus, norm_text, parse_price, read_text

TOOL_KINDS = {"trafilatura": {"article"}}  # tools that only claim article metadata


def worker(adapter, params: dict[str, Any]) -> dict[str, Any]:
    out = []
    for d in params["docs"]:
        html = read_text(d["html_path"])
        t0 = time.perf_counter()
        try:
            pred, err = adapter.extract(html, d["url"], d["kind"]), None
        except Exception as exc:
            pred, err = {}, f"{type(exc).__name__}: {exc}"
        out.append({"id": d["id"], "pred": pred, "ms": (time.perf_counter() - t0) * 1000, "error": err})
    return {"results": out}


def _availability(v: Any) -> Optional[str]:
    s = norm_text(v).replace(" ", "").replace("_", "")
    if not s:
        return None
    if "outofstock" in s or "soldout" in s or s == "false":
        return "OutOfStock"
    if "instock" in s or s == "true" or "available" in s:
        return "InStock"
    return s


def field_correct(name: str, pred: Any, truth: Any) -> Optional[bool]:
    """None = not predicted; True/False = predicted correctly / incorrectly."""
    if pred is None or (isinstance(pred, str) and not pred.strip()):
        return None
    try:
        if name == "price":
            p = parse_price(pred)
            return p is not None and abs(p - float(truth)) < 0.011
        if name == "rating":
            return abs(float(pred) - float(truth)) < 0.051
        if name == "review_count":
            return int(float(re.sub(r"[^\d.]", "", str(pred)))) == int(truth)
        if name == "published_date":
            m = re.search(r"\d{4}-\d{2}-\d{2}", str(pred))
            return bool(m) and m.group(0) == truth
        if name == "availability":
            return _availability(pred) == truth
        if name == "currency":
            return str(pred).strip().upper() == truth
        if name == "author":
            return norm_text(truth) in norm_text(pred)
    except (TypeError, ValueError):
        return False
    return norm_text(pred) == norm_text(truth)


def score(docs: list[dict[str, Any]], results: list[dict[str, Any]], kinds: Optional[set[str]]) -> dict[str, Any]:
    by_id = {r["id"]: r for r in results}
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "predicted": 0, "truth": 0})
    per_field: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "truth": 0})
    for d in docs:
        if kinds and d["kind"] not in kinds:
            continue
        pred = (by_id.get(d["id"]) or {}).get("pred") or {}
        groups = [f"{d['split']}", f"{d['split']}:{d['kind']}", f"mode:{d['mode']}", "all", f"all:{d['kind']}"]
        for name, truth in d["fields"].items():
            ok = field_correct(name, pred.get(name), truth)
            for g in groups:
                agg[g]["truth"] += 1
                agg[g]["predicted"] += ok is not None
                agg[g]["correct"] += bool(ok)
            per_field[f"{d['kind']}.{name}"]["truth"] += 1
            per_field[f"{d['kind']}.{name}"]["correct"] += bool(ok)

    def prf(c: dict[str, int]) -> dict[str, float]:
        p = c["correct"] / c["predicted"] if c["predicted"] else 0.0
        r = c["correct"] / c["truth"] if c["truth"] else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4),
                "f1": round(0.0 if p + r == 0 else 2 * p * r / (p + r), 4), "n_fields": c["truth"]}

    return {"groups": {g: prf(c) for g, c in sorted(agg.items())},
            "fields": {f: round(c["correct"] / c["truth"], 4) for f, c in sorted(per_field.items())}}


def run(ctx) -> dict[str, Any]:
    docs = []
    for d in load_corpus():
        t = d["truth"]
        if t["type"] not in ("product", "article"):
            continue
        docs.append({"id": d["id"], "split": d["split"], "html_path": d["html_path"], "url": t["url"],
                     "kind": t["type"], "fields": t["fields"], "mode": t.get("structured_mode", "none")})
    if ctx.quick:
        docs = docs[::3]
    from benchmarks.runner import tool_summary

    tools: dict[str, Any] = {}
    for tool in ctx.tools_for("extract"):
        ctx.say(f"  extract: {tool}")
        res = ctx.run_worker(tool, "extract", {"docs": docs})
        entry = tool_summary(res)
        if res.get("ok"):
            results = res["data"]["results"]
            entry.update(score(docs, results, TOOL_KINDS.get(tool)))
            entry["kinds"] = sorted(TOOL_KINDS.get(tool, {"product", "article"}))
            entry["ms_per_doc"] = round(sum(r["ms"] for r in results) / max(1, len(results)), 3)
            entry["errors"] = [r for r in results if r.get("error")][:5]
        tools[tool] = entry
    return {"suite": "extract", "params": {"docs": len(docs)},
            "notes": ["Field F1 = harmonic mean of precision (correct/predicted) and recall (correct/ground-truth).",
                      "Trafilatura is scored on article metadata only (title, author, date)."],
            "tools": tools}
