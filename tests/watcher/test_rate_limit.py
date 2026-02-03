"""Tests for RateLimiter."""

from __future__ import annotations

import time

from claude_session_player.watcher.rate_limit import RateLimiter


# ---------------------------------------------------------------------------
# Basic functionality tests
# ---------------------------------------------------------------------------


class TestRateLimiterAllowRequests:
    """Tests for allowing requests under the limit."""

    def test_allow_first_request(self) -> None:
        """First request should always be allowed."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        allowed, retry_after = limiter.check("api:192.168.1.1")
        assert allowed is True
        assert retry_after == 0

    def test_allow_requests_under_limit(self) -> None:
        """Requests under the rate limit should be allowed."""
        limiter = RateLimiter(rate=5, window_seconds=60)
        key = "api:192.168.1.1"

        for i in range(5):
            allowed, retry_after = limiter.check(key)
            assert allowed is True, f"Request {i+1} should be allowed"
            assert retry_after == 0

    def test_allow_up_to_limit(self) -> None:
        """Should allow exactly rate number of requests."""
        limiter = RateLimiter(rate=3, window_seconds=60)
        key = "api:192.168.1.1"

        # First 3 should be allowed
        for i in range(3):
            allowed, _ = limiter.check(key)
            assert allowed is True, f"Request {i+1} should be allowed"

        # 4th should be blocked
        allowed, _ = limiter.check(key)
        assert allowed is False


class TestRateLimiterBlockRequests:
    """Tests for blocking requests over the limit."""

    def test_block_over_limit(self) -> None:
        """Request over limit should be blocked."""
        limiter = RateLimiter(rate=2, window_seconds=60)
        key = "api:192.168.1.1"

        limiter.check(key)
        limiter.check(key)

        allowed, retry_after = limiter.check(key)
        assert allowed is False
        assert retry_after > 0

    def test_block_multiple_over_limit(self) -> None:
        """Multiple requests over limit should all be blocked."""
        limiter = RateLimiter(rate=2, window_seconds=60)
        key = "api:192.168.1.1"

        limiter.check(key)
        limiter.check(key)

        # All subsequent requests should be blocked
        for _ in range(5):
            allowed, _ = limiter.check(key)
            assert allowed is False


class TestRateLimiterRetryAfter:
    """Tests for retry_after calculation."""

    def test_retry_after_is_positive(self) -> None:
        """retry_after should be a positive integer when blocked."""
        limiter = RateLimiter(rate=1, window_seconds=30)
        key = "api:192.168.1.1"

        limiter.check(key)
        allowed, retry_after = limiter.check(key)

        assert allowed is False
        assert retry_after >= 1

    def test_retry_after_max_is_window(self) -> None:
        """retry_after should not exceed window_seconds."""
        limiter = RateLimiter(rate=1, window_seconds=30)
        key = "api:192.168.1.1"

        limiter.check(key)
        allowed, retry_after = limiter.check(key)

        assert retry_after <= 30

    def test_retry_after_at_least_one(self) -> None:
        """retry_after should be at least 1 second."""
        limiter = RateLimiter(rate=1, window_seconds=1)
        key = "api:192.168.1.1"

        limiter.check(key)
        allowed, retry_after = limiter.check(key)

        assert retry_after >= 1


class TestRateLimiterSlidingWindow:
    """Tests for sliding window behavior."""

    def test_window_allows_after_expiry(self) -> None:
        """Requests should be allowed after window expires."""
        limiter = RateLimiter(rate=1, window_seconds=1)
        key = "api:192.168.1.1"

        # First request allowed
        allowed, _ = limiter.check(key)
        assert allowed is True

        # Immediate second request blocked
        allowed, _ = limiter.check(key)
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Now should be allowed
        allowed, _ = limiter.check(key)
        assert allowed is True

    def test_sliding_window_partial_expiry(self) -> None:
        """As old requests expire, new ones should be allowed."""
        limiter = RateLimiter(rate=2, window_seconds=1)
        key = "api:192.168.1.1"

        # Make 2 requests
        limiter.check(key)
        time.sleep(0.3)
        limiter.check(key)

        # Third should be blocked
        allowed, _ = limiter.check(key)
        assert allowed is False

        # Wait for first to expire
        time.sleep(0.8)

        # Now one slot should be free
        allowed, _ = limiter.check(key)
        assert allowed is True


class TestRateLimiterKeyIndependence:
    """Tests for key independence."""

    def test_different_keys_independent(self) -> None:
        """Different keys should have independent limits."""
        limiter = RateLimiter(rate=2, window_seconds=60)
        key1 = "api:192.168.1.1"
        key2 = "api:192.168.1.2"

        # Exhaust limit for key1
        limiter.check(key1)
        limiter.check(key1)
        allowed1, _ = limiter.check(key1)
        assert allowed1 is False

        # key2 should still have full limit
        allowed2, _ = limiter.check(key2)
        assert allowed2 is True

    def test_api_vs_slack_independent(self) -> None:
        """API and Slack keys are independent."""
        limiter = RateLimiter(rate=1, window_seconds=60)

        api_key = "api:192.168.1.1"
        slack_key = "slack:U0123456789"

        limiter.check(api_key)
        allowed_api, _ = limiter.check(api_key)
        assert allowed_api is False

        allowed_slack, _ = limiter.check(slack_key)
        assert allowed_slack is True

    def test_telegram_vs_slack_independent(self) -> None:
        """Telegram and Slack keys are independent."""
        limiter = RateLimiter(rate=1, window_seconds=60)

        telegram_key = "telegram:123456789"
        slack_key = "slack:U0123456789"

        limiter.check(telegram_key)
        limiter.check(slack_key)

        # Both should now be blocked
        allowed_tg, _ = limiter.check(telegram_key)
        allowed_slack, _ = limiter.check(slack_key)

        assert allowed_tg is False
        assert allowed_slack is False


class TestRateLimiterGlobalKey:
    """Tests for global key (single-instance limits)."""

    def test_global_key_works(self) -> None:
        """Global key works for single-instance limits."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        global_key = "global:refresh"

        allowed, _ = limiter.check(global_key)
        assert allowed is True

        allowed, retry_after = limiter.check(global_key)
        assert allowed is False
        assert retry_after > 0

    def test_global_key_independent_from_others(self) -> None:
        """Global key is independent from other keys."""
        limiter = RateLimiter(rate=1, window_seconds=60)

        # Exhaust global limit
        limiter.check("global:refresh")
        allowed_global, _ = limiter.check("global:refresh")
        assert allowed_global is False

        # API key should still work
        allowed_api, _ = limiter.check("api:192.168.1.1")
        assert allowed_api is True


class TestRateLimiterReset:
    """Tests for reset functionality."""

    def test_reset_clears_limit(self) -> None:
        """Reset should clear the rate limit for a key."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        key = "api:192.168.1.1"

        # Exhaust limit
        limiter.check(key)
        allowed, _ = limiter.check(key)
        assert allowed is False

        # Reset
        limiter.reset(key)

        # Should be allowed again
        allowed, _ = limiter.check(key)
        assert allowed is True

    def test_reset_only_affects_specified_key(self) -> None:
        """Reset only affects the specified key."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        key1 = "api:192.168.1.1"
        key2 = "api:192.168.1.2"

        # Exhaust both limits
        limiter.check(key1)
        limiter.check(key2)

        # Reset only key1
        limiter.reset(key1)

        # key1 should be allowed, key2 still blocked
        allowed1, _ = limiter.check(key1)
        allowed2, _ = limiter.check(key2)

        assert allowed1 is True
        assert allowed2 is False

    def test_reset_nonexistent_key(self) -> None:
        """Reset on nonexistent key should not raise."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        # Should not raise
        limiter.reset("api:nonexistent")


class TestRateLimiterGetRemaining:
    """Tests for get_remaining functionality."""

    def test_remaining_at_full_capacity(self) -> None:
        """Remaining should equal rate when no requests made."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        remaining = limiter.get_remaining("api:192.168.1.1")
        assert remaining == 10

    def test_remaining_decreases_with_requests(self) -> None:
        """Remaining should decrease as requests are made."""
        limiter = RateLimiter(rate=5, window_seconds=60)
        key = "api:192.168.1.1"

        assert limiter.get_remaining(key) == 5

        limiter.check(key)
        assert limiter.get_remaining(key) == 4

        limiter.check(key)
        assert limiter.get_remaining(key) == 3

    def test_remaining_at_zero_when_exhausted(self) -> None:
        """Remaining should be 0 when limit exhausted."""
        limiter = RateLimiter(rate=2, window_seconds=60)
        key = "api:192.168.1.1"

        limiter.check(key)
        limiter.check(key)

        assert limiter.get_remaining(key) == 0

    def test_remaining_for_unknown_key(self) -> None:
        """Remaining for unknown key should equal rate."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        remaining = limiter.get_remaining("api:unknown")
        assert remaining == 10


class TestRateLimiterCleanup:
    """Tests for cleanup functionality."""

    def test_cleanup_removes_expired_entries(self) -> None:
        """Cleanup should remove expired entries."""
        limiter = RateLimiter(rate=5, window_seconds=1)
        key = "api:192.168.1.1"

        # Make some requests
        limiter.check(key)
        limiter.check(key)
        assert key in limiter._buckets
        assert len(limiter._buckets[key]) == 2

        # Wait for entries to expire
        time.sleep(1.1)

        # Cleanup should remove the empty bucket
        removed = limiter.cleanup()
        assert removed == 1
        assert key not in limiter._buckets

    def test_cleanup_keeps_valid_entries(self) -> None:
        """Cleanup should keep non-expired entries."""
        limiter = RateLimiter(rate=5, window_seconds=60)
        key = "api:192.168.1.1"

        limiter.check(key)
        limiter.check(key)

        removed = limiter.cleanup()
        assert removed == 0
        assert key in limiter._buckets
        assert len(limiter._buckets[key]) == 2

    def test_cleanup_returns_count_of_removed_buckets(self) -> None:
        """Cleanup returns the number of empty buckets removed."""
        limiter = RateLimiter(rate=5, window_seconds=1)

        # Make requests on multiple keys
        limiter.check("api:1.1.1.1")
        limiter.check("api:2.2.2.2")
        limiter.check("api:3.3.3.3")

        # Wait for entries to expire
        time.sleep(1.1)

        removed = limiter.cleanup()
        assert removed == 3


class TestRateLimiterKeyFormats:
    """Tests for different key format handling."""

    def test_api_ip_format(self) -> None:
        """API IP key format works."""
        limiter = RateLimiter(rate=30, window_seconds=60)
        key = "api:192.168.1.1"

        allowed, _ = limiter.check(key)
        assert allowed is True

    def test_slack_user_format(self) -> None:
        """Slack user key format works."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        key = "slack:U0123456789"

        allowed, _ = limiter.check(key)
        assert allowed is True

    def test_telegram_chat_format(self) -> None:
        """Telegram chat key format works."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        key = "telegram:123456789"

        allowed, _ = limiter.check(key)
        assert allowed is True

    def test_global_format(self) -> None:
        """Global key format works."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        key = "global:refresh"

        allowed, _ = limiter.check(key)
        assert allowed is True


class TestRateLimiterSpecLimits:
    """Tests for rate limits defined in the spec."""

    def test_api_search_limit(self) -> None:
        """GET /search: 30 requests per minute per IP."""
        limiter = RateLimiter(rate=30, window_seconds=60)
        key = "api:192.168.1.1"

        # Should allow 30 requests
        for i in range(30):
            allowed, _ = limiter.check(key)
            assert allowed is True, f"Request {i+1} should be allowed"

        # 31st should be blocked
        allowed, retry_after = limiter.check(key)
        assert allowed is False
        assert retry_after > 0

    def test_api_preview_limit(self) -> None:
        """GET /sessions/{id}/preview: 60 requests per minute per IP."""
        limiter = RateLimiter(rate=60, window_seconds=60)
        key = "api:192.168.1.1"

        # Should allow 60 requests
        for i in range(60):
            allowed, _ = limiter.check(key)
            assert allowed is True, f"Request {i+1} should be allowed"

        # 61st should be blocked
        allowed, _ = limiter.check(key)
        assert allowed is False

    def test_api_refresh_limit(self) -> None:
        """POST /index/refresh: 1 request per 60 seconds global."""
        limiter = RateLimiter(rate=1, window_seconds=60)
        key = "global:refresh"

        # First request allowed
        allowed, _ = limiter.check(key)
        assert allowed is True

        # Second should be blocked
        allowed, retry_after = limiter.check(key)
        assert allowed is False
        assert retry_after <= 60

    def test_slack_search_limit(self) -> None:
        """Slack: 10 searches per minute per user."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        key = "slack:U0123456789"

        for i in range(10):
            allowed, _ = limiter.check(key)
            assert allowed is True

        allowed, _ = limiter.check(key)
        assert allowed is False

    def test_telegram_search_limit(self) -> None:
        """Telegram: 10 searches per minute per chat."""
        limiter = RateLimiter(rate=10, window_seconds=60)
        key = "telegram:123456789"

        for i in range(10):
            allowed, _ = limiter.check(key)
            assert allowed is True

        allowed, _ = limiter.check(key)
        assert allowed is False
