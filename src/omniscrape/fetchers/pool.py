"""Thread-safe proxy pool manager with rotation and health metrics."""

import random
from collections import defaultdict
from threading import Lock
from typing import Optional


class ProxyPoolManager:
    """Manages pool of HTTP / SOCKS proxies with multiple rotation strategies."""

    def __init__(
        self,
        proxies: Optional[list[str]] = None,
        strategy: str = "round_robin",
    ):
        self._lock = Lock()
        self.proxies: list[str] = list(proxies or [])
        self.strategy = strategy
        self._index = 0
        self._domain_sticky: dict[str, str] = {}
        self._health: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "fail": 0})

    def add_proxy(self, proxy: str) -> None:
        with self._lock:
            if proxy not in self.proxies:
                self.proxies.append(proxy)

    def get_proxy(self, domain: Optional[str] = None) -> Optional[str]:
        with self._lock:
            if not self.proxies:
                return None

            if self.strategy == "sticky" and domain:
                if domain in self._domain_sticky:
                    return self._domain_sticky[domain]
                chosen = random.choice(self.proxies)
                self._domain_sticky[domain] = chosen
                return chosen

            if self.strategy == "random":
                return random.choice(self.proxies)

            # Round robin default
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
            return proxy

    def record_result(self, proxy: str, success: bool) -> None:
        with self._lock:
            if success:
                self._health[proxy]["success"] += 1
            else:
                self._health[proxy]["fail"] += 1
