"""Token counting: tiktoken (cl100k_base) when installed, otherwise a ~4 characters/token estimate."""

from functools import lru_cache
from typing import Any, Optional


@lru_cache(maxsize=1)
def _encoder() -> Optional[Any]:
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:  # not installed, or the encoding file cannot be downloaded
        return None


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return max(1, len(text) // 4) if text else 0


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    enc = _encoder()
    if enc is not None:
        ids = enc.encode(text, disallowed_special=())
        return enc.decode(ids[:max_tokens])
    return text[: max_tokens * 4]
