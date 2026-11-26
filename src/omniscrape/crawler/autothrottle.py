"""EWMA latency-adaptive rate limiter."""

import asyncio
from typing import Optional


class AutoThrottle:
    """Dynamically throttles crawl speed according to target server latency."""

    def __init__(self, target_latency_sec: float = 1.0, min_delay_sec: float = 0.1, max_delay_sec: float = 15.0):
        self.target_latency = target_latency_sec
        self.min_delay = min_delay_sec
        self.max_delay = max_delay_sec
        self._ewma_latency: Optional[float] = None
        self._current_delay: float = min_delay_sec

    def record_latency(self, latency_ms: float):
        sec = latency_ms / 1000.0
        if self._ewma_latency is None:
            self._ewma_latency = sec
        else:
            self._ewma_latency = 0.15 * sec + 0.85 * self._ewma_latency

        # Adjust delay based on EWMA vs target
        if self._ewma_latency > self.target_latency:
            self._current_delay = min(self.max_delay, self._current_delay * 1.5)
        elif self._ewma_latency < (self.target_latency * 0.5):
            self._current_delay = max(self.min_delay, self._current_delay * 0.8)

    async def wait(self):
        if self._current_delay > 0:
            await asyncio.sleep(self._current_delay)
