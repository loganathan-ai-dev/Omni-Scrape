"""Export benchmark results to two JSON datasets ({rows, meta}) for the scoreboard dashboard.

    python -m benchmarks.report.export_dashboard <final_result_dir> <baseline_result_dir> <out_dir>

scoreboard.json  one row per (metric, tool) for the head-to-head charts
progress.json    OmniScrape baseline vs final per headline metric, with the best other tool
"""

import json
import sys
from pathlib import Path

from benchmarks.report.build import flatten, load

# (suite, metric key, label, higher is better, format)
METRICS = [
    ("extract", "f1[holdout:product]", "Product extraction F1 (holdout)", True, "f3"),
    ("extract", "f1[holdout:article]", "Article metadata F1 (holdout)", True, "f3"),
    ("markdown", "f1[holdout]", "Main-content Markdown F1 (holdout)", True, "f3"),
    ("markdown", "leakage", "Boilerplate leakage", False, "pct"),
    ("adaptive", "recovery_rate", "Elements recovered after a redesign", True, "pct"),
    ("adaptive", "wrong_rate", "Wrong element returned", False, "pct"),
    ("parse", "docs_per_sec", "Parse + CSS select (docs/s)", True, "int"),
    ("crawl", "pages_per_sec", "Local crawl speed (pages/s)", True, "dec1"),
    ("crawl", "robots_violations", "Crawl robots.txt violations", False, "int"),
    ("crawl", "flaky_recovered", "Flaky pages recovered (of 10)", True, "int"),
    ("crawl", "peak_rss_mb", "Crawl peak memory (MB)", False, "int"),
    ("render", "pages_per_sec", "JavaScript rendering (pages/s)", True, "dec1"),
    ("render", "peak_rss_mb", "Rendering peak memory (MB)", False, "int"),
]
OURS = {"omniscrape", "omniscrape-isolated"}
# The baseline measured rendering in isolated mode (then the only mode), so progress compares like with like.
PROGRESS_TOOL = {"render": "omniscrape-isolated"}


def export(final_dir: Path, baseline_dir: Path, out_dir: Path) -> None:
    final = {(s, t, k): v for s, t, k, v in flatten(load(final_dir))}
    base = {(s, t, k): v for s, t, k, v in flatten(load(baseline_dir))}
    commit = json.loads((final_dir / "meta.json").read_text(encoding="utf-8"))["machine"].get("git_commit", "")
    code = Path(__file__).read_text(encoding="utf-8")
    meta = [{"label": "export_dashboard.py", "value": code, "type": "code", "lang": "python"},
            {"label": "Final run", "value": f"{final_dir.name} (commit {commit})"},
            {"label": "Baseline run", "value": baseline_dir.name}]

    scoreboard, progress = [], []
    for order, (suite, key, label, hib, fmt) in enumerate(METRICS):
        tools = sorted({t for (s, t, k) in final if s == suite and k == key})
        for tool in tools:
            scoreboard.append({"chart": f"{suite}:{key}", "order": order, "suite": suite, "metric": label,
                               "tool": tool, "value": final[(suite, tool, key)], "higher_is_better": hib,
                               "format": fmt, "omniscrape": tool in OURS})
        ours_tool = PROGRESS_TOOL.get(suite, "omniscrape")
        ours = final.get((suite, ours_tool, key))
        others = {t: v for (s, t, k), v in final.items() if s == suite and k == key and t not in OURS}
        best_tool = (max if hib else min)(others, key=others.get) if others else None
        progress.append({"metric": label + (" (isolated mode)" if ours_tool != "omniscrape" else ""), "order": order, "format": fmt, "higher_is_better": hib,
                         "baseline": base.get((suite, "omniscrape", key)), "final": ours,
                         "best_other": others.get(best_tool) if best_tool else None, "best_other_tool": best_tool,
                         "leads": None if best_tool is None or ours is None else
                         (ours >= others[best_tool] if hib else ours <= others[best_tool])})
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scoreboard.json").write_text(json.dumps({"rows": scoreboard, "meta": meta}, indent=1), encoding="utf-8")
    (out_dir / "progress.json").write_text(json.dumps({"rows": progress, "meta": meta}, indent=1), encoding="utf-8")
    print(f"wrote {len(scoreboard)} scoreboard rows and {len(progress)} progress rows to {out_dir}")


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
