"""
Simple in-process metrics registry for observability snapshots.
"""

from __future__ import annotations

import threading


class MetricsRegistry:
    """Thread-safe counter/gauge registry for lightweight instrumentation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {
            "stream_duration_seconds": 0.0,
            "quota_blocks_total": 0.0,
            "sse_pings_sent": 0.0,
        }
        self._gauges: dict[str, float] = {"active_streams": 0.0}

    def increment(self, name: str, amount: float = 1.0) -> None:
        """Increment a counter by the given amount."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + amount

    def observe(self, name: str, value: float) -> None:
        """Record an observation (e.g., duration) for a counter."""
        self.increment(name, value)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value (derived metric)."""
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Return a snapshot of current counters and gauges."""
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }


metrics = MetricsRegistry()
