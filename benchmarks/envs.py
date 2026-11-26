"""Isolated per-tool virtual environments (managed with uv, Python 3.12).

    python -m benchmarks envs                 # create/update all groups, write lock files
    python -m benchmarks envs --groups scrapy crawlee
    python -m benchmarks envs --locked        # reinstall exactly from benchmarks/requirements/*.txt

Competitor packages pin conflicting playwright/httpx/lxml versions, so they never share an
environment. Only conflict-free, light libraries are grouped ("parsers").
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from benchmarks.common import BENCH_DIR, ENVS_DIR, REPO_ROOT

PYTHON_VERSION = "3.12"
LOCK_DIR = BENCH_DIR / "requirements"

ENV_GROUPS: dict[str, dict] = {
    "omniscrape": {"packages": ["psutil", "playwright"], "editable": True,
                   "post": [["-m", "playwright", "install", "chromium"]]},
    "parsers": {"packages": ["lxml", "cssselect", "beautifulsoup4", "selectolax", "parsel", "trafilatura",
                             "markdownify", "html2text", "psutil"]},
    "scrapling": {"packages": ["scrapling[fetchers]", "psutil"],
                  "post": [["-m", "patchright", "install", "chromium"]]},
    "crawl4ai": {"packages": ["crawl4ai", "psutil"], "post": [["-m", "playwright", "install", "chromium"]]},
    "scrapy": {"packages": ["scrapy", "psutil"]},
    "crawlee": {"packages": ["crawlee[parsel]", "psutil"]},
}


def env_python(group: str) -> Path:
    base = ENVS_DIR / group
    return base / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def python_for_group(group: str) -> Optional[str]:
    py = env_python(group)
    return str(py) if py.exists() else None


def _run(cmd: list[str]) -> None:
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def create(group: str, locked: bool = False) -> None:
    spec = ENV_GROUPS[group]
    py = env_python(group)
    print(f"[envs] {group}", flush=True)
    if not py.exists():
        _run(["uv", "venv", "--python", PYTHON_VERSION, str(ENVS_DIR / group)])
    lock = LOCK_DIR / f"{group}.txt"
    if locked and lock.exists():
        _run(["uv", "pip", "install", "--python", str(py), "-r", str(lock)])
    else:
        _run(["uv", "pip", "install", "--python", str(py), *spec["packages"]])
    if spec.get("editable"):
        _run(["uv", "pip", "install", "--python", str(py), "-e", str(REPO_ROOT)])
    for post in spec.get("post", []):
        _run([str(py), *post])
    if not locked:
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        frozen = subprocess.run(["uv", "pip", "freeze", "--python", str(py)], check=True,
                                capture_output=True, text=True).stdout
        lines = [ln for ln in frozen.splitlines() if ln and not ln.startswith("-e") and "omniscrape" not in ln]
        lock.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_all(groups: Optional[list[str]] = None, locked: bool = False) -> dict[str, str]:
    status = {}
    for group in groups or list(ENV_GROUPS):
        try:
            create(group, locked=locked)
            status[group] = "ok"
        except subprocess.CalledProcessError as exc:
            status[group] = f"failed: {exc}"
            print(f"[envs] {group} FAILED: {exc}", flush=True)
    return status
