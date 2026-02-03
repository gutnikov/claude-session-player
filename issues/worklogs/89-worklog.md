# Issue #89: Add RateLimiter for API and bot commands

## Summary

Implemented a `RateLimiter` component using a sliding window algorithm to prevent abuse of search endpoints and bot commands.

## Changes Made

### New Files

1. **`claude_session_player/watcher/rate_limit.py`**
   - `RateLimiter`: Sliding window rate limiter with thread-safe access

2. **`tests/watcher/test_rate_limit.py`**
   - 34 tests covering all functionality

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestRateLimiterAllowRequests | 3 | Allow requests under limit |
| TestRateLimiterBlockRequests | 2 | Block requests over limit |
| TestRateLimiterRetryAfter | 3 | Return correct retry_after seconds |
| TestRateLimiterSlidingWindow | 2 | Sliding window allows requests after time passes |
| TestRateLimiterKeyIndependence | 3 | Different keys are independent |
| TestRateLimiterGlobalKey | 2 | Global key works for single-instance limits |
| TestRateLimiterReset | 3 | Reset functionality |
| TestRateLimiterGetRemaining | 4 | Get remaining requests |
| TestRateLimiterCleanup | 3 | Cleanup of old timestamps |
| TestRateLimiterKeyFormats | 4 | Key format handling |
| TestRateLimiterSpecLimits | 5 | Rate limits from spec |

**Total: 34 new tests, all passing**

## Design Decisions

### Sliding Window Algorithm

Uses a list of timestamps per key, cleaning entries outside the window on each check:

```python
def check(self, key: str) -> tuple[bool, int]:
    with self._lock:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window)

        bucket = self._buckets.setdefault(key, [])
        bucket[:] = [t for t in bucket if t > cutoff]

        if len(bucket) >= self.rate:
            oldest = min(bucket)
            retry_after_td = (oldest + timedelta(seconds=self.window)) - now
            return False, max(1, int(retry_after_td.total_seconds()))

        bucket.append(now)
        return True, 0
```

### Thread Safety

Used `threading.Lock` for thread-safe access since the limiter may be accessed from multiple async handlers concurrently, following the pattern established in `SearchStateManager`.

### Cleanup of Old Timestamps

Two mechanisms for preventing memory leaks:
1. **On each check()**: Removes expired timestamps from the accessed bucket
2. **Manual cleanup()**: Removes empty buckets across all keys

### Key Format Convention

Follows spec convention for platform-prefixed keys:
- API by IP: `"api:192.168.1.1"`
- Slack by user: `"slack:U0123456789"`
- Telegram by chat: `"telegram:123456789"`
- Global (for refresh): `"global:refresh"`

### Retry-After Calculation

Returns the number of seconds until the oldest request in the window expires:
- Always returns at least 1 second (never 0 when blocked)
- Never exceeds window_seconds

### Additional Methods

Added two helper methods beyond the spec:
- `get_remaining(key)`: Returns remaining requests for observability
- `cleanup()`: Manual cleanup for memory management

## Test Results

- **New tests:** 34 tests, all passing
- **Search-related tests:** 155 passing (indexer + search + search_state + rate_limit)
- **Core tests:** 474 passing (2 failures due to missing optional slack_sdk dependency - pre-existing)

## Acceptance Criteria Status

- [x] `RateLimiter` class implemented
- [x] Sliding window algorithm correct
- [x] Cleanup of old timestamps to prevent memory leak
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Allow requests under limit
- [x] Unit test: Block requests over limit
- [x] Unit test: Return correct retry_after seconds
- [x] Unit test: Sliding window allows requests after time passes
- [x] Unit test: Different keys are independent
- [x] Unit test: Global key works for single-instance limits

## Spec Reference

Implements issue #89 from `.claude/specs/session-search-api.md`:
- Rate Limiting section (lines 1106-1153)

## Notes

- No external runtime dependencies (stdlib only)
- Uses `threading.Lock` rather than `asyncio.Lock` since the limiter stores simple in-memory state
- The sliding window cleanup on each `check()` ensures memory stays bounded proportional to request rate
