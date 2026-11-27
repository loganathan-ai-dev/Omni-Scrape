"""Orchestrator: runs suites, launches one worker subprocess per (tool, suite), saves results."""

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Optional

from benchmarks.adapters import SUITE_TOOLS, TOOLS
from benchmarks.common import REPO_ROOT, RESULTS_DIR
from benchmarks.envs import python_for_group

ALL_SUITES = ["parse", "extract", "markdown", "adaptive", "render", "crawl", "live"]


@dataclass
class RunContext:
    out_dir: Path
    isolation: str = "auto"  # "env" (require per-tool env), "none" (current interpreter), "auto"
    tools: Optional[list[str]] = None
    repeats: int = 5
    quick: bool = False
    log: list[str] = field(default_factory=list)

    def say(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self.log.append(line)
        print(line, flush=True)

    def tools_for(self, suite: str) -> list[str]:
        eligible = SUITE_TOOLS[suite]
        return [t for t in eligible if self.tools is None or t in self.tools]

    def python_for(self, tool: str) -> tuple[Optional[str], str]:
        if self.isolation == "none":
            return sys.executable, "current"
        py = python_for_group(TOOLS[tool]["env"])
        if py:
            return py, f"env:{TOOLS[tool]['env']}"
        if self.isolation == "env":
            return None, "missing-env"
        return sys.executable, "current"

    def run_worker(self, tool: str, suite: str, params: dict[str, Any], timeout: int = 1200,
                   tag: str = "") -> dict[str, Any]:
        py, where = self.python_for(tool)
        if py is None:
            return {"tool": tool, "suite": suite, "ok": False, "skipped": True,
                    "error": f"environment for '{tool}' not found; run: python -m benchmarks envs"}
        jobs = self.out_dir / "jobs"
        jobs.mkdir(parents=True, exist_ok=True)
        stem = f"{suite}__{tool}" + (f"__{tag}" if tag else "")
        job_path, out_path = jobs / f"{stem}.json", jobs / f"{stem}.result.json"
        out_path.unlink(missing_ok=True)  # never mistake an earlier job's output for this one's
        job_path.write_text(json.dumps({"tool": tool, "suite": suite, "params": params}), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        start = time.perf_counter()
        try:
            proc = subprocess.run([py, "-m", "benchmarks.worker", str(job_path), str(out_path)],
                                  cwd=str(REPO_ROOT), env=env, timeout=timeout, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return {"tool": tool, "suite": suite, "ok": False, "error": f"timeout after {timeout}s", "where": where}
        wall = time.perf_counter() - start
        if not out_path.exists():
            return {"tool": tool, "suite": suite, "ok": False, "where": where,
                    "error": f"worker crashed (exit {proc.returncode}): {proc.stderr[-1500:]}"}
        result = json.loads(out_path.read_text(encoding="utf-8"))
        result["where"], result["wall_seconds"] = where, round(wall, 3)
        if not result.get("ok"):
            self.say(f"  {tool}: FAILED {result.get('error', '')[:300]}")
        return result

    def save(self, suite: str, payload: dict[str, Any]) -> Path:
        path = self.out_dir / f"{suite}.json"
        path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
        return path


def machine_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_orchestrator": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    try:
        import psutil

        info["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        freq = psutil.cpu_freq()
        info["cpu_mhz"] = round(freq.max or freq.current) if freq else None
    except Exception:
        pass
    try:
        info["git_commit"] = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                                            capture_output=True, text=True).stdout.strip()
        info["git_dirty"] = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                                                capture_output=True, text=True).stdout.strip())
    except Exception:
        pass
    return info


def run(suites: list[str], tools: Optional[list[str]] = None, isolation: str = "auto", repeats: int = 5,
        quick: bool = False, label: str = "", out_dir: Optional[Path] = None) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"-{label}" if label else "")
    out_dir = out_dir or RESULTS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = RunContext(out_dir=out_dir, isolation=isolation, tools=tools, repeats=repeats, quick=quick)
    meta = {"run_id": run_id, "label": label, "suites": suites, "isolation": isolation, "repeats": repeats,
            "quick": quick, "machine": machine_info()}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    for suite in suites:
        ctx.say(f"suite {suite}: tools {ctx.tools_for(suite)}")
        module = import_module(f"benchmarks.suites.{suite}")
        payload = module.run(ctx)
        payload.setdefault("suite", suite)
        ctx.save(suite, payload)
        ctx.say(f"suite {suite}: done")
    (out_dir / "run.log").write_text("\n".join(ctx.log), encoding="utf-8")
    latest = RESULTS_DIR / "LATEST"
    latest.write_text(str(out_dir), encoding="utf-8")
    return out_dir


def tool_summary(result: dict[str, Any]) -> dict[str, Any]:
    keys = ("ok", "skipped", "error", "version", "python", "where", "peak_rss_mb", "rss_after_import_mb",
            "import_seconds", "wall_seconds", "memory_sampled")
    return {k: result.get(k) for k in keys if k in result}
