"""Thread-safe proxy pool with rotation strategies and health-aware selection."""

import random
from collections import defaultdict
from threading import Lock
from typing import Optional


class ProxyPoolManager:
    """Pool of HTTP/SOCKS proxies.

    Strategies: ``round_robin`` (default), ``random``, ``sticky`` (one proxy per domain).
    A proxy whose recent failure ratio exceeds ``max_fail_ratio`` (after ``min_samples``
    requests) is skipped, unless every proxy is unhealthy, in which case all are used.
    """

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        strategy: str = "round_robin",
        max_fail_ratio: float = 0.5,
        min_samples: int = 3,
    ):
        self._lock = Lock()
        self.proxies: list[str] = list(proxies or [])
        self.strategy = strategy
        self.max_fail_ratio = max_fail_ratio
        self.min_samples = min_samples
        self._index = 0
        self._domain_sticky: dict[str, str] = {}
        self._health: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "fail": 0})

    def add_proxy(self, proxy: str) -> None:
        with self._lock:
            if proxy not in self.proxies:
                self.proxies.append(proxy)

    def remove_proxy(self, proxy: str) -> None:
        with self._lock:
            if proxy in self.proxies:
                self.proxies.remove(proxy)
            self._domain_sticky = {d: p for d, p in self._domain_sticky.items() if p != proxy}

    def is_healthy(self, proxy: str) -> bool:
        stats = self._health.get(proxy)
        if not stats:
            return True
        total = stats["success"] + stats["fail"]
        return total < self.min_samples or stats["fail"] / total <= self.max_fail_ratio

    def _candidates(self) -> list[str]:
        healthy = [p for p in self.proxies if self.is_healthy(p)]
        return healthy or list(self.proxies)

    def get_proxy(self, domain: Optional[str] = None) -> Optional[str]:
        with self._lock:
            if not self.proxies:
                return None
            candidates = self._candidates()

            if self.strategy == "sticky" and domain:
                current = self._domain_sticky.get(domain)
                if current in candidates:
                    return current
                chosen = random.choice(candidates)
                self._domain_sticky[domain] = chosen
                return chosen

            if self.strategy == "random":
                return random.choice(candidates)

            proxy = candidates[self._index % len(candidates)]
            self._index += 1
            return proxy

    def record_result(self, proxy: str, success: bool) -> None:
        with self._lock:
            self._health[proxy]["success" if success else "fail"] += 1

    def stats(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {p: dict(self._health[p]) for p in self.proxies}
