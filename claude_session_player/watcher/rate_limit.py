"""Rate limiter for API and bot commands.

This module provides:
- RateLimiter: Sliding window rate limiter for API endpoints and bot commands

Rate limits (from spec):
- REST API:
  - GET /search: 30 requests per minute per IP
  - GET /projects: 30 requests per minute per IP
  - GET /sessions/{id}/preview: 60 requests per minute per IP
  - POST /index/refresh: 1 request per 60 seconds global

- Bot Commands:
  - Slack: 10 searches per minute per user
  - Telegram: 10 searches per minute per chat

Key formats:
- API by IP: "api:192.168.1.1"
- Slack by user: "slack:U0123456789"
- Telegram by chat: "telegram:123456789"
- Global (for refresh): "global:refresh"
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone


class RateLimiter:
    """Sliding window rate limiter.

    Uses a sliding window algorithm to track requests within a time window.
    Each key (IP, user ID, chat ID, or "global") has its own bucket of
    request timestamps.

    Thread-safe for concurrent access.

    Example:
        # Allow 30 requests per 60 seconds
        limiter = RateLimiter(rate=30, window_seconds=60)

        # Check if request is allowed
        allowed, retry_after = limiter.check("api:192.168.1.1")
        if not allowed:
            return {"error": "rate_limited", "retry_after_seconds": retry_after}
    """

    def __init__(self, rate: int, window_seconds: int) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Maximum number of requests allowed within the window.
            window_seconds: Time window in seconds.
        """
        self.rate = rate
        self.window = window_seconds
        self._buckets: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Check if a request is allowed.

        If allowed, records the request timestamp. If not allowed,
        returns the number of seconds until the next request will be
        allowed (when the oldest request in the window expires).

        Args:
            key: Identifier (IP, user_id, chat_id, or "global").

        Returns:
            A tuple of (allowed, retry_after_seconds):
            - allowed: True if the request should proceed.
            - retry_after_seconds: Seconds to wait (0 if allowed).
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=self.window)

            # Get or create bucket and clean old entries
            bucket = self._buckets.setdefault(key, [])
            bucket[:] = [t for t in bucket if t > cutoff]

            if len(bucket) >= self.rate:
                # Over limit - calculate retry_after
                oldest = min(bucket)
                retry_after_td = (oldest + timedelta(seconds=self.window)) - now
                retry_after = int(retry_after_td.total_seconds())
                return False, max(1, retry_after)

            # Under limit - record request and allow
            bucket.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Removes all recorded requests for the given key, effectively
        resetting its rate limit counter.

        Args:
            key: Identifier to reset.
        """
        with self._lock:
            self._buckets.pop(key, None)

    def get_remaining(self, key: str) -> int:
        """Get the number of remaining requests for a key.

        Args:
            key: Identifier to check.

        Returns:
            Number of requests remaining in the current window.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=self.window)

            bucket = self._buckets.get(key, [])
            # Count only non-expired entries
            current_count = sum(1 for t in bucket if t > cutoff)
            return max(0, self.rate - current_count)

    def cleanup(self) -> int:
        """Clean up expired entries from all buckets.

        This is called automatically during check(), but can be called
        manually for memory management.

        Returns:
            Number of empty buckets removed.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(seconds=self.window)

            # Clean entries from all buckets
            empty_keys: list[str] = []
            for key, bucket in self._buckets.items():
                bucket[:] = [t for t in bucket if t > cutoff]
                if not bucket:
                    empty_keys.append(key)

            # Remove empty buckets
            for key in empty_keys:
                del self._buckets[key]

            return len(empty_keys)
