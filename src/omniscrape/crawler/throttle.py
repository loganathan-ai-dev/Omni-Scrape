"""Per-domain politeness: concurrency slots, fixed delays, robots Crawl-delay and AutoThrottle.

AutoThrottle follows Scrapy's published algorithm: target delay = latency / target_concurrency;
the next delay is the mean of the current delay and the target; non-2xx responses may raise the
delay but never lower it; the result is clamped to [download_delay, max_delay].
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Slot:
    semaphore: asyncio.Semaphore
    delay: float
    last_request: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DomainThrottle:
    def __init__(self, per_domain_concurrency: int = 8, download_delay: float = 0.0, autothrottle: bool = False,
                 start_delay: float = 1.0, max_delay: float = 60.0, target_concurrency: float = 1.0):
        self.per_domain_concurrency = per_domain_concurrency
        self.download_delay = download_delay
        self.autothrottle = autothrottle
        self.start_delay = start_delay
        self.max_delay = max_delay
        self.target_concurrency = max(0.01, target_concurrency)
        self._slots: dict[str, _Slot] = {}
        self._floors: dict[str, float] = {}
        self._paused_until: dict[str, float] = {}

    def pause(self, domain: str, seconds: float) -> None:
        """Pause all workers targeting ``domain`` for at least ``seconds`` (e.g. HTTP 429 Retry-After)."""
        if seconds <= 0:
            return
        until = time.monotonic() + min(float(seconds), 60.0)
        if until > self._paused_until.get(domain, 0.0):
            self._paused_until[domain] = until

    def set_floor(self, domain: str, delay: Optional[float]) -> None:
        """Minimum delay for a domain (e.g. robots.txt Crawl-delay)."""
        if delay:
            self._floors[domain] = max(self._floors.get(domain, 0.0), float(delay))
            slot = self._slots.get(domain)
            if slot:
                slot.delay = max(slot.delay, self._floors[domain])

    def _slot(self, domain: str) -> _Slot:
        if domain not in self._slots:
            initial = self.start_delay if self.autothrottle else self.download_delay
            self._slots[domain] = _Slot(asyncio.Semaphore(self.per_domain_concurrency),
                                        max(initial, self._floors.get(domain, 0.0)))
        return self._slots[domain]

    async def acquire(self, domain: str) -> None:
        slot = self._slots.get(domain) or self._slot(domain)
        await slot.semaphore.acquire()
        paused_until = self._paused_until.get(domain, 0.0)
        if paused_until > 0:
            wait = paused_until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
        if slot.delay > 0:
            async with slot.lock:  # space out request *starts* on this domain
                wait = slot.last_request + slot.delay - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                slot.last_request = time.monotonic()

    def release(self, domain: str, latency_s: Optional[float] = None, status: Optional[int] = None) -> None:
        slot = self._slots[domain]
        slot.semaphore.release()
        if self.autothrottle and latency_s is not None:
            target = latency_s / self.target_concurrency
            new = (slot.delay + target) / 2.0
            if status is not None and not 200 <= status < 300 and new < slot.delay:
                new = slot.delay  # errors never speed the crawl up
            floor = max(self.download_delay, self._floors.get(domain, 0.0))
            slot.delay = min(self.max_delay, max(floor, new))

    def delay_of(self, domain: str) -> float:
        return self._slot(domain).delay
