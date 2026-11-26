"""Shared paths, text normalization and scoring helpers (stdlib only)."""

import json
import os
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

BENCH_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCH_DIR.parent
CORPUS_DIR = BENCH_DIR / "corpus" / "data"
RESULTS_DIR = BENCH_DIR / "results"


def _default_envs_dir() -> Path:
    """Per-tool virtualenvs hold thousands of files, so keep them out of synced folders (OneDrive)."""
    override = os.environ.get("OMNISCRAPE_BENCH_ENVS")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "omniscrape-bench" / "envs"


ENVS_DIR = _default_envs_dir()

_WORD = re.compile(r"[^\W\d_]{2,}", re.UNICODE)
_WS = re.compile(r"\s+")


def norm_text(value: Any) -> str:
    return _WS.sub(" ", str(value or "")).strip().casefold()


def words(text: str) -> list[str]:
    """Lower-cased alphabetic tokens (>=2 letters). Markdown syntax and numbers are ignored."""
    return [w.casefold() for w in _WORD.findall(text or "")]


def token_prf(output: str, reference: str) -> tuple[float, float, float]:
    """Multiset token precision / recall / F1 of ``output`` against ``reference``."""
    out, ref = Counter(words(output)), Counter(words(reference))
    if not out or not ref:
        return 0.0, 0.0, 0.0
    overlap = sum((out & ref).values())
    p = overlap / sum(out.values())
    r = overlap / sum(ref.values())
    f = 0.0 if p + r == 0 else 2 * p * r / (p + r)
    return p, r, f


def leakage(output: str, boilerplate_vocab: Iterable[str]) -> float:
    """Share of output tokens that come from the boilerplate vocabulary."""
    vocab = set(boilerplate_vocab)
    toks = words(output)
    if not toks:
        return 0.0
    return sum(1 for t in toks if t in vocab) / len(toks)


def lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def rouge_l(output: str, reference: str, max_tokens: int = 3000) -> float:
    """ROUGE-L F1 over word sequences (truncated for speed)."""
    o, r = words(output)[:max_tokens], words(reference)[:max_tokens]
    lcs = lcs_len(o, r)
    if not lcs:
        return 0.0
    p, rec = lcs / len(o), lcs / len(r)
    return 2 * p * rec / (p + rec)


def summarize(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"median": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0, "n": 0}
    s = sorted(samples)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    return {"median": statistics.median(s), "p95": p95, "min": s[0], "max": s[-1], "n": len(s)}


def load_corpus(split: Optional[str] = None, kind: Optional[str] = None) -> list[dict[str, Any]]:
    """Load corpus documents: [{"id", "split", "html_path", "truth": {...}}]."""
    docs = []
    splits = [split] if split else ["dev", "holdout"]
    for sp in splits:
        folder = CORPUS_DIR / sp
        if not folder.exists():
            continue
        for truth_path in sorted(folder.glob("*.json")):
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            if kind and truth.get("type") != kind:
                continue
            docs.append({
                "id": truth_path.stem,
                "split": sp,
                "html_path": str(truth_path.with_suffix(".html")),
                "truth": truth,
            })
    return docs


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def parse_price(value: Any) -> Optional[float]:
    """Lenient price parser for scoring (handles 1,299.00 / 1.299,00 / 1 299,00)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d.,]", "", str(value))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = s.replace(",", "") if len(tail) == 3 and head else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
