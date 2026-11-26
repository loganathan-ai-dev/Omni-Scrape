"""Query-focused filtering of Markdown blocks with BM25 (keeps headings of kept sections)."""

import math
import re
from collections import Counter
from typing import Optional

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were will with".split())


def tokenize(text: str) -> list[str]:
    return [t for t in (w.casefold() for w in _TOKEN.findall(text)) if t not in STOP and len(t) > 1]


def bm25_scores(docs: list[list[str]], query: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    if not n or not query:
        return [0.0] * n
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for q in set(query):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            s += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(d) / avgdl))
        scores.append(s)
    return scores


def bm25_filter_markdown(md: str, query: str, min_score: Optional[float] = None, relative: float = 0.3) -> str:
    """Keep content blocks relevant to ``query`` and the heading of each kept block's section.

    A block is kept when its BM25 score is at least ``min_score`` or, by default, ``relative`` x the best
    block's score. Headings are context only; they are never kept on their own.
    """
    blocks = [b for b in re.split(r"\n{2,}", md) if b.strip()]
    if not blocks:
        return md
    is_heading = [b.lstrip().startswith("#") for b in blocks]
    content_idx = [i for i, h in enumerate(is_heading) if not h]
    raw = bm25_scores([tokenize(blocks[i]) for i in content_idx], tokenize(query))
    scores = {i: s for i, s in zip(content_idx, raw)}
    best = max(scores.values(), default=0.0)
    if best <= 0:
        return md
    cutoff = min_score if min_score is not None else best * relative
    keep = set()
    last_heading = None
    for i, block in enumerate(blocks):
        if is_heading[i]:
            last_heading = i
            continue
        if scores[i] > 0 and scores[i] >= cutoff:
            keep.add(i)
            if last_heading is not None:
                keep.add(last_heading)
    if blocks[0].startswith("# "):
        keep.add(0)  # page title
    return "\n\n".join(blocks[i] for i in sorted(keep))
