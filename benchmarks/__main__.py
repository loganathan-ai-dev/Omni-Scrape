"""Benchmark CLI.

    python -m benchmarks corpus                 # (re)generate synthetic corpus + adaptive cases
    python -m benchmarks snapshot               # refresh toscrape.com snapshots (network)
    python -m benchmarks envs [--locked]        # create isolated per-tool environments (uv)
    python -m benchmarks run [--suite parse,crawl] [--tools omniscrape,scrapy] [--quick]
    python -m benchmarks report [RESULT_DIR]    # build the HTML report (default: latest run)
    python -m benchmarks compare BASE NEW       # print metric deltas between two runs
"""

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # tool error messages may contain non-cp1252 characters
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="python -m benchmarks", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("corpus", help="generate synthetic corpus and adaptive cases")
    p.add_argument("--seed", type=int, default=1337)
    sub.add_parser("snapshot", help="snapshot toscrape.com pages into the holdout corpus")

    p = sub.add_parser("envs", help="create isolated tool environments")
    p.add_argument("--groups", nargs="*")
    p.add_argument("--locked", action="store_true")

    p = sub.add_parser("run", help="run benchmark suites")
    p.add_argument("--suite", default="parse,extract,markdown,adaptive,render,crawl,live")
    p.add_argument("--tools", default="", help="comma-separated subset of tools")
    p.add_argument("--isolation", choices=["auto", "env", "none"], default="auto")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--quick", action="store_true", help="smaller corpus and fewer repeats")
    p.add_argument("--label", default="")
    p.add_argument("--no-report", action="store_true")

    p = sub.add_parser("report", help="build the HTML report")
    p.add_argument("result_dir", nargs="?")
    p.add_argument("--baseline", help="earlier result dir to compare against")

    p = sub.add_parser("compare", help="print deltas between two runs")
    p.add_argument("base")
    p.add_argument("new")

    args = ap.parse_args(argv)

    if args.cmd == "corpus":
        from benchmarks.corpus.adaptive_cases import build
        from benchmarks.corpus.generate import generate

        print("corpus:", generate(args.seed))
        print("adaptive cases:", build())
    elif args.cmd == "snapshot":
        from benchmarks.corpus.snapshot import main as snap

        snap()
    elif args.cmd == "envs":
        from benchmarks.envs import create_all

        print(create_all(args.groups, locked=args.locked))
    elif args.cmd == "run":
        from benchmarks.runner import ALL_SUITES, run

        suites = [s.strip() for s in args.suite.split(",") if s.strip()]
        unknown = set(suites) - set(ALL_SUITES)
        if unknown:
            ap.error(f"unknown suites: {sorted(unknown)}")
        tools = [t.strip() for t in args.tools.split(",") if t.strip()] or None
        out = run(suites, tools=tools, isolation=args.isolation, repeats=args.repeats, quick=args.quick,
                  label=args.label)
        print(f"results: {out}")
        if not args.no_report:
            from benchmarks.report.build import build_report

            print(f"report: {build_report(out)}")
    elif args.cmd == "report":
        from benchmarks.common import RESULTS_DIR
        from benchmarks.report.build import build_report

        result_dir = Path(args.result_dir) if args.result_dir else Path((RESULTS_DIR / "LATEST").read_text().strip())
        print(build_report(result_dir, baseline=Path(args.baseline) if args.baseline else None))
    elif args.cmd == "compare":
        from benchmarks.report.build import compare

        for line in compare(Path(args.base), Path(args.new)):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
