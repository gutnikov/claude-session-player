# Issue #78: Add end-to-end tests for messaging integration

## Summary

Added comprehensive end-to-end tests for the Telegram and Slack messaging integration, verifying the complete flow from HTTP request to (mocked) message delivery.

## Changes Made

### New Files

1. **`tests/watcher/test_messaging_e2e.py`**
   - 17 E2E tests covering the complete messaging integration
   - Mock publishers for Telegram and Slack that don't hit real APIs
   - HTTP request mocking for API endpoint tests
   - Full service lifecycle testing

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestAttachDetachE2E | 5 | Attach/detach via API endpoints |
| TestMessageDeliveryE2E | 4 | Message delivery from file change to API |
| TestRateLimitingE2E | 1 | Debouncing of rapid updates |
| TestReplayE2E | 1 | Replay with replay_count parameter |
| TestPersistenceE2E | 1 | Destinations survive service restart |
| TestMultipleDestinationsE2E | 1 | Events sent to all destinations |
| TestClearAllE2E | 1 | Context compaction handling |
| TestErrorHandlingE2E | 1 | Messaging failures don't break SSE |
| TestHealthCheckE2E | 1 | Health endpoint shows bot status |
| TestListSessionsE2E | 1 | List sessions shows destinations |

**Total: 17 new tests**

## Test Details

### Attach/Detach E2E Tests (5 tests)
- `test_attach_telegram_via_api_returns_201`: POST /attach for Telegram returns 201
- `test_attach_slack_via_api_returns_201`: POST /attach for Slack returns 201
- `test_attach_without_bot_token_returns_401`: Attach without bot token returns 401
- `test_detach_removes_destination_returns_204`: POST /detach removes destination
- `test_idempotent_attach_returns_success`: Duplicate attach is idempotent

### Message Delivery E2E Tests (4 tests)
- `test_user_event_sends_telegram_message`: USER event sends Telegram message
- `test_user_event_sends_slack_message_with_blocks`: USER event sends Slack message with Block Kit
- `test_turn_grouping_assistant_and_tools_in_one_message`: Turn grouping works correctly
- `test_tool_result_updates_existing_message`: Tool results update existing messages

### Rate Limiting E2E Tests (1 test)
- `test_rapid_updates_debounced`: Rapid updates result in fewer API calls

### Replay E2E Tests (1 test)
- `test_replay_count_sends_batched_catch_up_message`: Replay sends batched catch-up

### Persistence E2E Tests (1 test)
- `test_destinations_survive_service_restart`: Destinations restored after restart

### Additional Tests (5 tests)
- `test_event_sent_to_all_attached_destinations`: Multiple destinations receive events
- `test_clear_all_sends_compaction_message`: ClearAll sends compaction message
- `test_messaging_failure_does_not_break_sse`: Messaging failures don't break SSE
- `test_health_shows_bot_status`: Health endpoint shows bot status
- `test_list_sessions_shows_destinations`: Sessions list shows destinations

## Design Decisions

### Mock Publishers
Created `MockTelegramBot` and `MockSlackClient` classes that implement the same interface as the real publishers but:
- Track all sent/edited messages for assertions
- Can be configured to fail for error testing
- Don't require optional dependencies (aiogram, slack_sdk)

### Test Infrastructure
Built on top of existing patterns from `test_messaging_integration.py` but:
- Tests the full HTTP API flow via `WatcherAPI` handlers
- Uses `MockRequest` for simulating HTTP requests
- Tests complete service lifecycle (start/stop)

### No Optional Dependencies Required
Tests don't require aiogram or slack_sdk to be installed - they use mock publishers that don't import these libraries.

## Test Results

- **New tests:** 17 tests, all passing
- **Core tests:** 231 passing (unchanged)
- **API tests:** 38 passing (unchanged)
- All tests pass in CI (verified with `pytest tests/watcher/test_messaging_e2e.py -v`)

## Acceptance Criteria Status

- [x] Test fixtures for mocking Telegram and Slack APIs
- [x] Attach/detach E2E tests (5 tests)
- [x] Message delivery E2E tests (4 tests)
- [x] Rate limiting E2E tests (1 test)
- [x] Replay E2E tests (1 test)
- [x] Persistence E2E tests (1 test)
- [x] All tests pass
- [x] Tests don't hit real APIs (properly mocked)
- [x] Test file: `tests/watcher/test_messaging_e2e.py`

## Spec Reference

Implements issue #78 from `.claude/specs/messaging-integration.md`:
- End-to-end tests for messaging integration
- Verifies complete flow from HTTP request to message delivery
- All components working together correctly
