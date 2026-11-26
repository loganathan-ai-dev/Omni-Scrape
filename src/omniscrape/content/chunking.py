"""Split Markdown into retrieval-sized chunks that keep their heading path."""

import re
from dataclasses import dataclass, field

from omniscrape.content.tokens import count_tokens

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Chunk:
    text: str
    headings: list[str] = field(default_factory=list)
    tokens: int = 0


def chunk_markdown(md: str, max_tokens: int = 512, overlap_blocks: int = 0) -> list[Chunk]:
    """Pack whole blocks into chunks of at most ``max_tokens``; a new top-level section starts a new chunk.

    Oversized single blocks are split by sentences. Each chunk records its heading path.
    """
    blocks = [b.strip() for b in re.split(r"\n{2,}", md) if b.strip()]
    chunks: list[Chunk] = []
    path: list[tuple[int, str]] = []
    current: list[str] = []
    current_tokens = 0
    current_path: list[str] = []

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            text = "\n\n".join(current)
            chunks.append(Chunk(text=text, headings=list(current_path), tokens=count_tokens(text)))
            current = current[-overlap_blocks:] if overlap_blocks else []
            current_tokens = sum(count_tokens(c) for c in current)

    for block in blocks:
        m = _HEADING.match(block)
        if m:
            level = len(m.group(1))
            if level <= 2:
                flush()
            path = [(lv, t) for lv, t in path if lv < level] + [(level, m.group(2).strip())]
            if not current:
                current_path = [t for _, t in path]
        pieces = [block]
        if count_tokens(block) > max_tokens:
            pieces = _split_sentences(block, max_tokens)
        for piece in pieces:
            t = count_tokens(piece)
            if current and current_tokens + t > max_tokens:
                flush()
                current_path = [x for _, x in path]
            if not current:
                current_path = [x for _, x in path]
            current.append(piece)
            current_tokens += t
    flush()
    return chunks


def _split_sentences(text: str, max_tokens: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out, buf = [], ""
    for s in sentences:
        candidate = f"{buf} {s}".strip()
        if buf and count_tokens(candidate) > max_tokens:
            out.append(buf)
            buf = s
        else:
            buf = candidate
    if buf:
        out.append(buf)
    return out
