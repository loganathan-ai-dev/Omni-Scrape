"""Turn a results directory into flat metrics, a self-contained HTML report and run-to-run diffs."""

import html
import json
from pathlib import Path
from typing import Any, Iterator, Optional

SUITE_TITLES = {
    "parse": "Parsing speed", "extract": "Metadata extraction", "markdown": "Main-content Markdown",
    "adaptive": "Self-healing selectors", "render": "JavaScript rendering", "crawl": "Local crawl",
    "live": "Live sandbox crawl",
}

# (label, higher_is_better, format)
METRICS: dict[str, tuple[str, bool, str]] = {
    "docs_per_sec": ("docs/s", True, "{:.1f}"),
    "count_accuracy": ("selector count accuracy", True, "{:.1%}"),
    "recovery_rate": ("recovered", True, "{:.1%}"),
    "wrong_rate": ("wrong element", False, "{:.1%}"),
    "f1": ("F1", True, "{:.3f}"),
    "leakage": ("boilerplate leakage", False, "{:.1%}"),
    "success_rate": ("rendered", True, "{:.1%}"),
    "pages_per_sec": ("pages/s", True, "{:.2f}"),
    "coverage": ("coverage", True, "{:.1%}"),
    "robots_violations": ("robots violations", False, "{:.0f}"),
    "duplicate_requests": ("duplicate requests", False, "{:.0f}"),
    "flaky_recovered": ("flaky pages recovered", True, "{:.0f}"),
    "peak_rss_mb": ("peak memory MB", False, "{:.0f}"),
    "ok_ratio": ("HTTP 2xx", True, "{:.1%}"),
}


def load(result_dir: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"dir": str(result_dir), "suites": {}}
    meta = result_dir / "meta.json"
    out["meta"] = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    for path in sorted(result_dir.glob("*.json")):
        if path.name in ("meta.json",) or path.stem.startswith("adaptive_cases"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "tools" in data:
            out["suites"][data.get("suite", path.stem)] = data
    return out


def flatten(run: dict[str, Any]) -> Iterator[tuple[str, str, str, float]]:
    """Yield (suite, tool, metric_key, value). Metric keys are stable across runs."""
    for suite, data in run["suites"].items():
        for tool, e in data["tools"].items():
            if not e.get("ok"):
                continue
            if e.get("peak_rss_mb") is not None:
                yield suite, tool, "peak_rss_mb", e["peak_rss_mb"]
            if suite == "parse":
                yield suite, tool, "docs_per_sec", e.get("docs_per_sec", 0)
                yield suite, tool, "count_accuracy", e.get("count_accuracy", 0)
            elif suite == "extract":
                for g in ("holdout:product", "holdout:article", "all"):
                    if g in e.get("groups", {}):
                        yield suite, tool, f"f1[{g}]", e["groups"][g]["f1"]
            elif suite == "markdown":
                for g in ("holdout", "handwritten", "all"):
                    if g in e.get("groups", {}):
                        yield suite, tool, f"f1[{g}]", e["groups"][g].get("f1", 0)
                if "leakage" in e.get("groups", {}).get("all", {}):
                    yield suite, tool, "leakage", e["groups"]["all"]["leakage"]
            elif suite == "adaptive":
                g = e.get("groups", {}).get("all")
                if g:
                    yield suite, tool, "recovery_rate", g["recovery_rate"]
                    yield suite, tool, "wrong_rate", g["wrong"] / g["n"] if g["n"] else 0
                for k, g in e.get("groups", {}).items():
                    if k.startswith("mutation:"):
                        yield suite, tool, f"recovery_rate[{k[9:]}]", g["recovery_rate"]
            elif suite == "render":
                yield suite, tool, "success_rate", e.get("success_rate", 0)
                yield suite, tool, "pages_per_sec", e.get("pages_per_sec", 0)
            elif suite == "crawl":
                for k in ("pages_per_sec", "coverage", "robots_violations", "duplicate_requests", "flaky_recovered"):
                    if k in e:
                        yield suite, tool, k, e[k]
            elif suite == "live":
                for name, t in e.get("targets", {}).items():
                    if "pages_per_sec" in t:
                        yield suite, tool, f"pages_per_sec[{name}]", t["pages_per_sec"]
                        yield suite, tool, f"ok_ratio[{name}]", t["ok_ratio"]


def _meta_for(key: str) -> tuple[str, bool, str]:
    base = key.split("[")[0]
    label, hib, fmt = METRICS.get(base, (key, True, "{:.3f}"))
    return (label + (key[len(base):] if "[" in key else ""), hib, fmt)


def compare(base_dir: Path, new_dir: Path) -> list[str]:
    a = {(s, t, k): v for s, t, k, v in flatten(load(base_dir))}
    b = {(s, t, k): v for s, t, k, v in flatten(load(new_dir))}
    lines = [f"{'suite':9s} {'tool':16s} {'metric':34s} {'base':>10s} {'new':>10s} {'change':>9s}"]
    for key in sorted(set(a) & set(b)):
        s, t, k = key
        label, hib, fmt = _meta_for(k)
        old, new = a[key], b[key]
        if old == new:
            continue
        pct = (new - old) / old * 100 if old else float("inf")
        better = (new > old) == hib
        lines.append(f"{s:9s} {t:16s} {label:34s} {fmt.format(old):>10s} {fmt.format(new):>10s} "
                     f"{pct:+8.1f}% {'better' if better else 'worse'}")
    for key in sorted(set(b) - set(a)):
        s, t, k = key
        lines.append(f"{s:9s} {t:16s} {_meta_for(k)[0]:34s} {'-':>10s} {_meta_for(k)[2].format(b[key]):>10s}  (new)")
    return lines if len(lines) > 1 else ["no differences"]


# --------------------------------------------------------------------------- html
CSS = """
:root{--bg:#f7f8f6;--fg:#1c2421;--muted:#5d6b64;--line:#dfe4df;--card:#fff;--head:#eef1ed;--best:#e1f0e6;--bestfg:#17623a;--bad:#a1322a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#141a17;--fg:#e6ebe7;--muted:#9aa9a0;--line:#2a3530;--card:#1b231f;--head:#222c27;--best:#1f3a2b;--bestfg:#8fd8ad;--bad:#f08a80;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141a17;--fg:#e6ebe7;--muted:#9aa9a0;--line:#2a3530;--card:#1b231f;--head:#222c27;--best:#1f3a2b;--bestfg:#8fd8ad;--bad:#f08a80;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding-block:24px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
main{max-width:1000px;margin:0 auto}h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:28px 0 6px}
p.sub,p.note{color:var(--muted);margin:2px 0}p.note{font-size:.88rem}
.wrap{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--card);margin-top:8px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}thead th{background:var(--head);font-weight:600}
tr:last-child td{border-bottom:0}td.best{background:var(--best);color:var(--bestfg);font-weight:600}
td.fail{color:var(--bad);white-space:normal;text-align:left}
"""


def _table(suite: str, run: dict[str, Any]) -> str:
    rows = [(t, k, v) for s, t, k, v in flatten(run) if s == suite]
    if not rows:
        return "<p class='note'>No results.</p>"
    tools = list(dict.fromkeys(t for t, _, _ in rows))
    keys = list(dict.fromkeys(k for _, k, _ in rows))
    val = {(t, k): v for t, k, v in rows}
    head = "".join(f"<th>{html.escape(t)}</th>" for t in tools)
    body = []
    for k in keys:
        label, hib, fmt = _meta_for(k)
        present = {t: val[(t, k)] for t in tools if (t, k) in val}
        best = (max if hib else min)(present.values()) if len(present) > 1 else None
        cells = "".join(
            f"<td class='{'best' if best is not None and present.get(t) == best else ''}'>"
            f"{fmt.format(present[t]) if t in present else '&ndash;'}</td>" for t in tools)
        body.append(f"<tr><td>{html.escape(label)}</td>{cells}</tr>")
    failed = [(t, e.get("error") or "skipped") for t, e in run["suites"][suite]["tools"].items() if not e.get("ok")]
    fail_html = "".join(f"<p class='note'><b>{html.escape(t)}</b> did not run: {html.escape(str(err))[:240]}</p>"
                        for t, err in failed)
    return f"<div class='wrap'><table><thead><tr><th>metric</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>{fail_html}"


def build_report(result_dir: Path, baseline: Optional[Path] = None) -> Path:
    run = load(result_dir)
    meta = run["meta"]
    m = meta.get("machine", {})
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>OmniScrape benchmark</title><style>{CSS}</style></head><body><main>",
             f"<h1>OmniScrape benchmark</h1><p class='sub'>Run {html.escape(str(meta.get('run_id', result_dir.name)))} "
             f"&middot; commit {html.escape(str(m.get('git_commit', '?')))}"
             f"{' (uncommitted changes)' if m.get('git_dirty') else ''} &middot; {html.escape(str(m.get('platform', '')))} "
             f"&middot; {m.get('cpu_count', '?')} CPUs &middot; {m.get('ram_gb', '?')} GB RAM</p>",
             "<p class='note'>Green cells mark the best value in a row. Each tool ran in its own isolated environment and process.</p>"]
    for suite, data in run["suites"].items():
        versions = ", ".join(f"{t} {e.get('version', '')}".strip() for t, e in data["tools"].items() if e.get("ok"))
        parts.append(f"<h2>{html.escape(SUITE_TITLES.get(suite, suite))}</h2><p class='sub'>{html.escape(versions)}</p>")
        parts.append(_table(suite, run))
        for note in data.get("notes", []):
            parts.append(f"<p class='note'>{html.escape(note)}</p>")
    if baseline:
        parts.append("<h2>Change since baseline</h2><div class='wrap'><pre style='margin:0;padding:12px;overflow-x:auto'>"
                     + html.escape("\n".join(compare(baseline, result_dir))) + "</pre></div>")
    parts.append("</main></body></html>")
    out = result_dir / "report.html"
    out.write_text("".join(parts), encoding="utf-8")
    return out
