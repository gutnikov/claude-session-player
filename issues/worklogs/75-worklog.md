# Issue #75: Update WatcherAPI with attach/detach endpoints

## Summary

Replaced the existing `/watch` and `/unwatch` endpoints with new `/attach` and `/detach` endpoints that support messaging destinations. This is a **breaking API change** that removes the old watch/unwatch model in favor of an attach/detach model for managing messaging destinations (Telegram, Slack).

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/api.py`**
   - Removed `handle_watch()` and `handle_unwatch()` methods
   - Added `handle_attach()` method for POST /attach endpoint
   - Added `handle_detach()` method for POST /detach endpoint
   - Added `_validate_destination()` helper to validate bot credentials
   - Added `_replay_to_destination()` helper (stub for issue #76)
   - Updated `handle_list_sessions()` to include destinations and SSE client count
   - Updated `handle_health()` to include bot status (configured/not_configured)
   - Updated `create_app()` to register new routes
   - Changed dataclass fields: now uses `DestinationManager` instead of `state_manager` and `file_watcher`

2. **`claude_session_player/watcher/service.py`**
   - Added import for `DestinationManager`
   - Added `destination_manager` field (optional, for dependency injection)
   - Updated `__post_init__()` to create DestinationManager and pass it to WatcherAPI
   - Added `_on_destination_session_start()` callback for starting file watching
   - Added `_on_destination_session_stop()` callback for stopping file watching
   - Updated `stop()` to call `destination_manager.shutdown()`

3. **`tests/watcher/test_api.py`**
   - Removed all old watch/unwatch tests (35 tests removed)
   - Added new fixtures: `destination_manager`, `watcher_api_with_telegram_token`, `watcher_api_with_slack_token`
   - Added 38 new tests covering:
     - Attach success (telegram, slack, idempotent, with replay_count)
     - Attach validation errors (missing fields, invalid types, relative path)
     - Attach not found (404)
     - Attach auth errors (401 not configured, 403 validation failed)
     - Detach success
     - Detach validation errors
     - Detach not found (404)
     - List sessions with destinations
     - Health check with bot status
     - Route registration (verifies old routes removed)
     - Integration attach/detach flow

## Design Decisions

### API Signature Change

The `WatcherAPI` dataclass now takes `DestinationManager` instead of `state_manager` and `file_watcher`. This reflects the shift from direct file watching to destination-based management:

```python
# Old signature (removed)
WatcherAPI(config_manager, state_manager, file_watcher, event_buffer, sse_manager)

# New signature
WatcherAPI(config_manager, destination_manager, event_buffer, sse_manager)
```

### Bot Credential Validation

Before attaching a destination, the API validates bot credentials:
1. Check if token is configured (401 if not)
2. Call `publisher.validate()` to verify credentials (403 if invalid)
3. Close publisher after validation

This ensures destinations are only attached if messaging will work.

### Replay Count Stub

The `_replay_to_destination()` method is a stub that returns the count of events available for replay. The actual replay logic (formatting and sending catch-up messages) will be implemented in issue #76 when `MessageStateTracker` is integrated into `WatcherService`.

### Service Integration

The `WatcherService` now creates a `DestinationManager` with callbacks:
- `_on_destination_session_start`: Starts file watching when first destination attaches
- `_on_destination_session_stop`: Stops file watching when keep-alive expires after last detach

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestHandleAttachSuccess | 4 | attach success cases |
| TestHandleAttachValidationErrors | 7 | 400 errors |
| TestHandleAttachNotFound | 1 | 404 error |
| TestHandleAttachAuthErrors | 4 | 401/403 errors |
| TestHandleDetachSuccess | 1 | detach success |
| TestHandleDetachValidationErrors | 5 | 400 errors |
| TestHandleDetachNotFound | 1 | 404 error |
| TestHandleListSessions | 3 | list with destinations |
| TestHandleHealth | 5 | health with bot status |
| TestHandleSessionEventsNotFound | 1 | SSE 404 |
| TestCreateApp | 2 | route registration |
| TestIntegrationAttachDetachFlow | 1 | end-to-end flow |
| TestWatcherAPIStartTime | 2 | start time tracking |
| TestModuleImports | 1 | module imports |

## Test Results

- **New API tests:** 38 tests, all passing
- **Total tests (excluding optional deps):** 883 passing
- Tests requiring `aiogram`/`slack_sdk` skipped (not installed in test env)

## Acceptance Criteria Status

- [x] `POST /watch` and `DELETE /unwatch/{session_id}` removed
- [x] `POST /attach` implemented with full validation
- [x] `POST /detach` implemented
- [x] `GET /sessions` updated to include destinations
- [x] `GET /health` updated to include bot status
- [x] `GET /sessions/{session_id}/events` unchanged (SSE still works)
- [x] Error responses match spec (400, 401, 403, 404)
- [x] Unit tests updated:
  - [x] Old endpoint tests removed
  - [x] Attach success (telegram)
  - [x] Attach success (slack)
  - [x] Attach idempotent (duplicate returns success)
  - [x] Attach with replay_count
  - [x] Attach validation errors (missing fields)
  - [x] Attach auth errors (401, 403)
  - [x] Detach success
  - [x] Detach not found (404)
  - [x] List sessions with destinations
  - [x] Health check with bot status
- [x] Integration tests pass

## Breaking Changes

This PR introduces breaking API changes:

| Old Endpoint | New Endpoint | Notes |
|--------------|--------------|-------|
| `POST /watch` | `POST /attach` | Now requires destination |
| `DELETE /unwatch/{id}` | `POST /detach` | Now POST with body |

Clients must be updated to use the new endpoints.

## Spec Reference

Implements issue #75 from `.claude/specs/messaging-integration.md`:
- Replace `/watch` and `/unwatch` with `/attach` and `/detach`
- Support messaging destinations in API
- Add bot status to health endpoint
