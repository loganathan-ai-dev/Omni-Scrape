"""Keep the Claude Code copy of the omniscrape skill identical to the canonical one.

    python scripts/sync_skills.py           # copy .agents/skills/omniscrape -> .claude/skills/omniscrape
    python scripts/sync_skills.py --check   # exit 1 if the copies differ (used by CI)
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".agents" / "skills" / "omniscrape"
TARGETS = [ROOT / ".claude" / "skills" / "omniscrape"]


def _files(folder: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(folder)).replace("\\", "/"): p.read_bytes().replace(b"\r\n", b"\n")
        for p in sorted(folder.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def differences(source: Path, target: Path) -> list[str]:
    a, b = _files(source), (_files(target) if target.exists() else {})
    return [f"{name}: {'missing' if name not in b else 'extra' if name not in a else 'differs'}"
            for name in sorted(set(a) | set(b)) if a.get(name) != b.get(name)]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    status = 0
    for target in TARGETS:
        diff = differences(SOURCE, target)
        if check:
            if diff:
                print(f"{target.relative_to(ROOT)} is out of sync with {SOURCE.relative_to(ROOT)}:")
                print("\n".join(f"  {d}" for d in diff))
                print("Run: python scripts/sync_skills.py")
                status = 1
            else:
                print(f"{target.relative_to(ROOT)}: in sync")
        else:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__"))
            print(f"synced {SOURCE.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
