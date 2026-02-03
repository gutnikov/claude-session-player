# Issue #88: Add SearchStateManager for pagination state

## Summary

Implemented `SearchStateManager` to track active search sessions per chat, enabling pagination and action buttons to reference the correct results without storing full session IDs in callback data.

## Changes Made

### New Files

1. **`claude_session_player/watcher/search_state.py`**
   - `SearchState`: Dataclass storing search query, filters, results, and pagination offset
   - `SearchStateManager`: Manages search state per chat with TTL expiration

2. **`tests/watcher/test_search_state.py`**
   - 30 tests covering all functionality

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestSearchStateGetPage | 5 | get_page() with various offsets and limits |
| TestSearchStateSessionAtIndex | 4 | session_at_index() mapping page-relative index to results |
| TestSearchStatePaginationHelpers | 5 | has_next_page() and has_prev_page() |
| TestSearchStateManagerSaveAndGet | 3 | Save/retrieve state, replacement on new search |
| TestSearchStateManagerTTL | 3 | TTL expiration behavior |
| TestSearchStateManagerUpdateOffset | 3 | Pagination offset updates |
| TestSearchStateManagerDelete | 2 | State deletion |
| TestSearchStateChatIdFormat | 3 | Telegram and Slack chat ID formats |
| TestSearchStateMessageId | 2 | Integer and string message ID types |

**Total: 30 new tests, all passing**

## Design Decisions

### Thread Safety

Used `threading.Lock` for thread-safe access since the manager may be accessed from multiple async handlers concurrently:
```python
class SearchStateManager:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._states: dict[str, SearchState] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
```

### TTL Expiration

States expire after a configurable TTL (default 5 minutes):
- Checked on `get()` - returns None if expired
- Checked on `update_offset()` - returns None if expired
- Cleanup runs on each `save()` to prevent memory leaks

### Chat ID Format

Follows spec convention for platform-prefixed chat IDs:
- Telegram: `"telegram:{chat_id}"` (e.g., `"telegram:123456789"`)
- Slack: `"slack:{channel_id}"` (e.g., `"slack:C0123456789"`)

### One State Per Chat

New searches replace previous state for the same chat. This is intentional per spec - users can only have one active search at a time in a chat.

## Test Results

- **New tests:** 30 tests, all passing
- **Search-related tests:** 121 passing (indexer + search + search_state)
- **Core tests:** 474 passing (2 failures due to missing optional slack_sdk dependency)

## Acceptance Criteria Status

- [x] `SearchState` dataclass with helper methods
- [x] `SearchStateManager` with save/get/update/delete
- [x] TTL expiration working correctly
- [x] Cleanup of expired states on save
- [x] Thread-safe access
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Save and retrieve state
- [x] Unit test: State expires after TTL
- [x] Unit test: New search replaces old state
- [x] Unit test: `get_page()` returns correct slice
- [x] Unit test: `session_at_index()` maps page index to result
- [x] Unit test: Pagination helpers (`has_next_page`, `has_prev_page`)
- [x] Unit test: Expired states cleaned up

## Spec Reference

Implements issue #88 from `.claude/specs/session-search-api.md`:
- Search State Management section (lines 1052-1102)

## Notes

- No external runtime dependencies (stdlib only)
- Uses `threading.Lock` rather than `asyncio.Lock` since the manager stores simple in-memory state
- Message ID can be either `int` (Telegram) or `str` (Slack timestamp)
