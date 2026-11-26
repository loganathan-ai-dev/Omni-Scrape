"""Retry policies with exponential backoff and jitter."""

import asyncio
import random
from typing import Callable, TypeVar
from omniscrape.exceptions import OmniScrapeError
from omniscrape.observability.logging import get_logger

logger = get_logger("omniscrape.resilience.retry")

T = TypeVar("T")


async def with_retry(
    coro_fn: Callable[..., Any],
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs,
) -> Any:
    """Executes an async function with exponential backoff."""
    attempt = 0
    delay = initial_delay

    while True:
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            is_retryable = getattr(exc, "retryable", True)
            if attempt > max_retries or not is_retryable:
                raise

            jitter = random.uniform(0.8, 1.2)
            wait_time = delay * jitter
            logger.warning(f"Retry attempt {attempt}/{max_retries} after {wait_time:.2f}s due to: {exc}")
            await asyncio.sleep(wait_time)
            delay *= backoff_factor
