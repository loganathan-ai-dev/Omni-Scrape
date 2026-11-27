"""In-memory telemetry and Prometheus-compatible metrics tracker."""

from collections import defaultdict, deque
from threading import Lock
from typing import Any


class MetricsTracker:
    """Thread-safe telemetry metrics aggregator."""

    def __init__(self):
        self._lock = Lock()
        self.counters: dict[str, int] = defaultdict(int)
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1000))
        self.gauges: dict[str, float] = {}

    def inc(self, metric: str, amount: int = 1):
        with self._lock:
            self.counters[metric] += amount

    def observe_latency(self, metric: str, duration_ms: float):
        with self._lock:
            self.latencies[metric].append(duration_ms)

    def set_gauge(self, metric: str, value: float):
        with self._lock:
            self.gauges[metric] = value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stats = {}
            for k, v in self.latencies.items():
                if v:
                    stats[k] = {
                        "count": len(v),
                        "avg_ms": round(sum(v) / len(v), 2),
                        "p95_ms": round(sorted(v)[int(len(v) * 0.95)], 2),
                    }
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "latency_stats": stats,
            }


# Singleton tracker
global_metrics = MetricsTracker()
