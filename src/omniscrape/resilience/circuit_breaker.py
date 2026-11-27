"""Per-domain circuit breaker pattern."""

import time
from threading import Lock

from omniscrape.exceptions import CircuitBreakerOpenError


class CircuitBreaker:
    """Tracks domain health and trips to OPEN state upon repeated failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self._lock = Lock()
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def record_success(self, domain: str):
        with self._lock:
            self._failures[domain] = 0
            self._opened_at.pop(domain, None)

    def record_failure(self, domain: str):
        with self._lock:
            count = self._failures.get(domain, 0) + 1
            self._failures[domain] = count
            if count >= self.failure_threshold:
                self._opened_at[domain] = time.time()

    def check(self, domain: str):
        with self._lock:
            opened = self._opened_at.get(domain)
            if opened:
                elapsed = time.time() - opened
                if elapsed < self.recovery_timeout:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN for domain '{domain}'. Remaining cooldown: {self.recovery_timeout - elapsed:.1f}s"
                    )
                # In half-open state: allow probe
                self._opened_at.pop(domain, None)
                self._failures[domain] = self.failure_threshold - 1
