from datetime import datetime, timedelta
from typing import Dict, Tuple
import threading

from fastapi import HTTPException


class RateLimiter:
    """In-memory rate limiter using fixed-window counters.

    Single-instance, not suitable for multi-process deployments.
    For production, use Redis or similar shared store.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # (ip/user_key, window_start): count
        self._ip_counts: Dict[Tuple[str, int], int] = {}
        self._user_counts: Dict[Tuple[str, int], int] = {}
        # Window size: 1 minute
        self.window_seconds = 60

    def _get_window_start(self, now: datetime) -> int:
        """Get window start timestamp (floor to window)."""
        return int(now.timestamp()) // self.window_seconds * self.window_seconds

    def _cleanup_old_entries(self, counts: Dict[Tuple[str, int], int], current_window: int) -> None:
        """Remove old entries (older than 2 windows ago)."""
        to_remove = [k for k in counts.keys() if k[1] < current_window - self.window_seconds * 2]
        for k in to_remove:
            del counts[k]

    def check_ip_rate(self, ip: str, max_requests: int = 60) -> None:
        """Check IP rate limit. Raises HTTPException if exceeded."""
        from backend.app.config.settings import settings
        if settings.environment == 'test':
            return
        now = datetime.now()
        window_start = self._get_window_start(now)
        key = (ip, window_start)

        with self._lock:
            self._cleanup_old_entries(self._ip_counts, window_start)
            count = self._ip_counts.get(key, 0)
            if count >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail={"code": "RATE_LIMITED", "message": "Too many requests from this IP"}
                )
            self._ip_counts[key] = count + 1

    def check_user_rate(self, user_id: int, max_requests: int = 120) -> None:
        """Check user rate limit. Raises HTTPException if exceeded."""
        from backend.app.config.settings import settings
        if settings.environment == 'test':
            return
        now = datetime.now()
        window_start = self._get_window_start(now)
        key = (str(user_id), window_start)

        with self._lock:
            self._cleanup_old_entries(self._user_counts, window_start)
            count = self._user_counts.get(key, 0)
            if count >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail={"code": "RATE_LIMITED", "message": "Too many requests from this user"}
                )
            self._user_counts[key] = count + 1


# Global instance
rate_limiter = RateLimiter()