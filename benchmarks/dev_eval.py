"""Tuning loop on the DEV split only (the holdout is never loaded here).

    python -m benchmarks.dev_eval [extract|markdown|all] [--show N]

Runs OmniScrape in-process and prints per-field / per-template scores plus the worst cases,
so extractors can be improved without looking at holdout pages.
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict

from benchmarks.adapters import load_adapter
from benchmarks.common import CORPUS_DIR, leakage, load_corpus, read_text, token_prf
from benchmarks.suites.extract import field_correct, score


def eval_extract(show: int) -> None:
    adapter = load_adapter("omniscrape")
    docs = []
    for d in load_corpus(split="dev"):
        t = d["truth"]
        if t["type"] in ("product", "article"):
            docs.append({"id": d["id"], "split": "dev", "html_path": d["html_path"], "url": t["url"], "kind": t["type"],
                         "fields": t["fields"], "mode": t.get("structured_mode", "none"), "template": t["template"]})
    results = [{"id": d["id"], "pred": adapter.extract(read_text(d["html_path"]), d["url"], d["kind"])} for d in docs]
    scored = score(docs, results, None)
    print("== extract (dev)")
    for g in ("dev:product", "dev:article"):
        print(f"  {g:14s}", scored["groups"].get(g))
    for mode in ("mode:jsonld", "mode:microdata", "mode:og_only", "mode:none"):
        print(f"  {mode:14s}", scored["groups"].get(mode))
    print("  per field:", json.dumps(scored["fields"]))
    by_id = {r["id"]: r["pred"] for r in results}
    misses = []
    for d in docs:
        for name, truth in d["fields"].items():
            ok = field_correct(name, by_id[d["id"]].get(name), truth)
            if not ok:
                misses.append((d["template"], d["mode"], d["id"], name, truth, by_id[d["id"]].get(name)))
    per_t: dict[str, int] = defaultdict(int)
    for m in misses:
        per_t[f"{m[0]}/{m[3]}"] += 1
    print("  misses by template/field:", dict(sorted(per_t.items(), key=lambda kv: -kv[1])))
    for m in misses[:show]:
        print("   MISS", m)


def eval_markdown(show: int) -> None:
    adapter = load_adapter("omniscrape")
    vocab = json.loads((CORPUS_DIR / "vocab.json").read_text(encoding="utf-8"))["boilerplate"]
    rows = []
    for d in load_corpus(split="dev", kind="article"):
        md = adapter.markdown(read_text(d["html_path"]), d["truth"]["url"])
        p, r, f = token_prf(md, d["truth"]["main_text"])
        rows.append((f, p, r, leakage(md, vocab), d["id"], md))
    print("== markdown (dev)")
    print(f"  F1={statistics.mean(x[0] for x in rows):.4f} P={statistics.mean(x[1] for x in rows):.4f} "
          f"R={statistics.mean(x[2] for x in rows):.4f} leakage={statistics.mean(x[3] for x in rows):.4f} n={len(rows)}")
    for f, p, r, lk, doc_id, md in sorted(rows)[:show]:
        print(f"   worst {doc_id}: F1={f:.3f} P={p:.3f} R={r:.3f} leak={lk:.3f} :: {md[:160]!r}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="all", choices=["extract", "markdown", "all"])
    ap.add_argument("--show", type=int, default=8)
    args = ap.parse_args()
    if args.what in ("extract", "all"):
        eval_extract(args.show)
    if args.what in ("markdown", "all"):
        eval_markdown(args.show)


if __name__ == "__main__":
    main()
