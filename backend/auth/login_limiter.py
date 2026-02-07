"""Login brute-force protection.

Tracks failed login attempts per username and per IP address using
in-memory sliding windows.  After a configurable number of failures
the account / IP is temporarily locked out.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    timestamps: deque[float] = field(default_factory=deque)


class LoginLimiter:
    """In-memory login attempt tracker with temporary lockout."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 900,
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        # key -> deque of failure timestamps
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        # key -> lockout-until timestamp
        self._lockouts: dict[str, float] = {}

    def _prune(self, key: str, now: float) -> None:
        bucket = self._failures.get(key)
        if bucket is None:
            return
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def is_locked(self, key: str) -> bool:
        """Return True if the key is currently locked out."""
        now = time.monotonic()
        lockout_until = self._lockouts.get(key)
        if lockout_until and now < lockout_until:
            return True
        # Clear expired lockout
        if lockout_until:
            self._lockouts.pop(key, None)
            self._failures.pop(key, None)
        return False

    def record_failure(self, key: str) -> bool:
        """Record a failed attempt. Returns True if the key is now locked out."""
        now = time.monotonic()
        self._prune(key, now)
        self._failures[key].append(now)
        if len(self._failures[key]) >= self.max_attempts:
            self._lockouts[key] = now + self.lockout_seconds
            return True
        return False

    def record_success(self, key: str) -> None:
        """Clear failures for a key after successful login."""
        self._failures.pop(key, None)
        self._lockouts.pop(key, None)

    def remaining_lockout_seconds(self, key: str) -> int:
        """Seconds remaining on lockout (0 if not locked)."""
        now = time.monotonic()
        lockout_until = self._lockouts.get(key)
        if lockout_until and now < lockout_until:
            return int(lockout_until - now)
        return 0


# Module-level singletons
_username_limiter = LoginLimiter(max_attempts=5, window_seconds=300, lockout_seconds=900)
_ip_limiter = LoginLimiter(max_attempts=15, window_seconds=300, lockout_seconds=600)


def get_username_limiter() -> LoginLimiter:
    return _username_limiter


def get_ip_limiter() -> LoginLimiter:
    return _ip_limiter
