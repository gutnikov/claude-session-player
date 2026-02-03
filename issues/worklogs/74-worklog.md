# Issue #74: Add MessageDebouncer for rate-limiting message updates

## Summary

Implemented `MessageDebouncer` class for rate-limiting message updates to prevent hitting Telegram and Slack rate limits. This component coalesces rapid updates to the same message, ensuring we stay within platform rate limits (targeting 50% of actual limits).

## Changes Made

### New Files

1. **`claude_session_player/watcher/debouncer.py`**
   - `PendingUpdate`: Dataclass tracking a pending debounced update (task, update_fn, content)
   - `MessageDebouncer` class with:
     - `__init__(telegram_delay_ms, slack_delay_ms)`: Initialize with configurable delays (defaults: 500ms Telegram, 2000ms Slack)
     - `schedule_update()`: Schedule a debounced update for a message at a destination
     - `flush()`: Execute all pending updates immediately
     - `cancel_all()`: Cancel all pending updates without executing (for shutdown)
     - `pending_count()`: Return count of pending updates
     - `has_pending()`: Check if there's a pending update for a specific message
     - `get_pending_content()`: Get the latest pending content for a message

2. **`tests/watcher/test_debouncer.py`**
   - 26 tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added imports for `MessageDebouncer` and `PendingUpdate`
   - Updated `__all__` list with 2 new exports

## Design Decisions

### Debounce Key Structure

Updates are debounced using a composite key of `(destination_type, identifier, message_id)`:
- `destination_type`: "telegram" or "slack"
- `identifier`: chat_id (Telegram) or channel (Slack)
- `message_id`: The message being updated

This ensures that:
- Updates to different messages are not coalesced
- Updates to the same message in different chats/channels are independent
- Telegram and Slack updates to the same logical message are independent

### Update Function Pattern

The `schedule_update()` method accepts an `update_fn` callback that will be called when the debounce delay expires. This function should capture all the content it needs (via closure). The `content` parameter is stored for inspection/debugging but the actual update logic is in `update_fn`.

### Error Handling

- Update failures are logged but don't raise exceptions (fire-and-forget pattern)
- This prevents a single failed update from blocking other pending updates
- Callers can handle errors in their `update_fn` if needed

### Flush vs Cancel

- `flush()`: Cancels pending timers and executes all updates immediately. Used when we need to ensure updates are delivered (e.g., before session ends).
- `cancel_all()`: Cancels pending timers without executing. Used for clean shutdown when updates should not be delivered.

### Delay Defaults

Following the spec's 50% target of actual rate limits:
- Telegram: 500ms (allows ~2 updates/sec vs 30 msg/sec limit)
- Slack: 2000ms (allows ~0.5 updates/sec vs 1 req/sec limit)

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestMessageDebouncerInit | 3 | initialization |
| TestGetDelay | 2 | delay selection |
| TestSingleUpdate | 2 | single update execution |
| TestRapidUpdateCoalescing | 4 | coalescing behavior |
| TestFlush | 4 | flush functionality |
| TestCancelAll | 3 | cancel functionality |
| TestErrorHandling | 1 | error handling |
| TestUtilityMethods | 3 | utility methods |
| TestPendingUpdate | 1 | dataclass |
| TestModuleImports | 3 | package imports |

## Test Results

- **Before:** 1071 tests
- **After:** 1097 tests (26 new)
- All new tests pass

## Acceptance Criteria Status

- [x] `MessageDebouncer` class in `claude_session_player/watcher/debouncer.py`
- [x] Configurable delays: 500ms default for Telegram, 2000ms for Slack
- [x] `schedule_update()` cancels and reschedules on rapid updates
- [x] Latest content preserved for coalesced updates
- [x] `flush()` executes pending updates immediately
- [x] `cancel_all()` for clean shutdown
- [x] Unit tests cover:
  - [x] Single update executes after delay
  - [x] Rapid updates coalesced (only last one executes)
  - [x] Different delays for Telegram vs Slack
  - [x] Flush executes immediately
  - [x] Cancel prevents execution
  - [x] Multiple messages debounced independently
- [x] No updates lost (latest content always delivered)

## Spec Reference

Implements issue #74 from `.claude/specs/messaging-integration.md`:
- MessageDebouncer component for rate-limiting message updates
- Per-message per-destination debouncing strategy
- Integration-ready for MessagingCoordinator
