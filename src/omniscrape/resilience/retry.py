"""Retry policies with exponential backoff and jitter."""

import asyncio
import random
from typing import Any, Awaitable, Callable, Optional, TypeVar

from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.resilience.retry")

T = TypeVar("T")

MAX_RETRY_AFTER_SECONDS = 60.0


async def with_retry(
    coro_fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: Optional[tuple[type[BaseException], ...]] = None,
    **kwargs: Any,
) -> T:
    """Execute an async function, retrying failures with exponential backoff and jitter.

    An exception is retried when:
      * ``retry_on`` is None or the exception is an instance of one of its types, and
      * the exception does not set ``retryable = False``.

    If the exception carries a ``retry_after`` attribute (e.g. ``RateLimitError``), the wait is
    at least that long (capped at 60s).
    """
    attempt = 0
    delay = initial_delay

    while True:
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if retry_on is not None and not isinstance(exc, retry_on):
                raise
            if attempt > max_retries or not getattr(exc, "retryable", True):
                raise

            wait_time = delay * random.uniform(0.8, 1.2)
            retry_after = getattr(exc, "retry_after", None)
            if retry_after:
                wait_time = max(wait_time, min(float(retry_after), MAX_RETRY_AFTER_SECONDS))

            logger.warning(f"Retry attempt {attempt}/{max_retries} after {wait_time:.2f}s due to: {exc}")
            await asyncio.sleep(wait_time)
            delay *= backoff_factor
