# Issue #55: Add REST API for watch/unwatch/list operations

## Summary

Implemented `WatcherAPI` class that provides REST API endpoints for managing watched sessions: add, remove, list, health check, and SSE streaming delegation.

## Changes Made

### New Files

1. **`claude_session_player/watcher/api.py`**
   - `WatcherAPI` dataclass with:
     - `handle_watch(request)` - POST /watch endpoint
     - `handle_unwatch(request)` - DELETE /unwatch/{session_id} endpoint
     - `handle_list_sessions(request)` - GET /sessions endpoint
     - `handle_session_events(request)` - GET /sessions/{session_id}/events (SSE delegation)
     - `handle_health(request)` - GET /health endpoint
     - `create_app()` - Creates aiohttp Application with all routes
   - Coordinates between ConfigManager, StateManager, FileWatcher, EventBufferManager, and SSEManager

2. **`tests/watcher/test_api.py`**
   - 37 comprehensive tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added export for `WatcherAPI` class

2. **`pyproject.toml`**
   - Added `aiohttp>=3.0` to `[watcher]` optional dependency

## Design Decisions

### HTTP Framework

Used `aiohttp.web` for the HTTP server:
- Already used by the Slack integration (in optional deps)
- Good async support compatible with existing SSE module
- Lightweight and well-documented

### Request Handling

Each endpoint handler returns an aiohttp `Response` or `StreamResponse`:
- JSON responses use `web.json_response()` for proper content type
- SSE endpoint returns `StreamResponse` for streaming
- HTTP status codes follow spec: 201 (created), 204 (no content), 400 (bad request), 404 (not found), 409 (conflict)

### Resource Cleanup on Unwatch

When unwatching a session, cleanup happens in this order:
1. Notify SSE subscribers (emit `session_ended`)
2. Remove from file watcher
3. Remove event buffer
4. Delete state file
5. Remove from config

This ensures:
- Subscribers learn the session is ending
- No more file changes are processed
- Event buffer memory is freed
- State is cleaned up
- Config reflects current state

### Start Time Tracking

`WatcherAPI` tracks `_start_time` for the health endpoint's `uptime_seconds`:
- Set automatically on creation via `field(default_factory=time.time)`
- Can be overridden for testing

## Test Coverage

37 tests organized by endpoint and scenario:

- **TestHandleWatchSuccess** (4 tests): Success cases for POST /watch
- **TestHandleWatchMissingFields** (4 tests): Missing/invalid request body
- **TestHandleWatchFileNotFound** (1 test): Nonexistent file path
- **TestHandleWatchDuplicateSession** (1 test): Session ID already exists
- **TestHandleWatchInvalidPath** (1 test): Relative path validation
- **TestHandleUnwatchSuccess** (3 tests): Success cases for DELETE /unwatch
- **TestHandleUnwatchNotFound** (1 test): Session not found
- **TestHandleListSessions** (6 tests): GET /sessions with various states
- **TestHandleHealth** (4 tests): GET /health status and uptime
- **TestHandleSessionEventsNotFound** (1 test): SSE for nonexistent session
- **TestCreateApp** (2 tests): Application and route creation
- **TestIntegrationWatchUnwatchFlow** (2 tests): Full watch→unwatch workflow
- **TestIntegrationHealthWithSessions** (1 test): Health count updates
- **TestEdgeCases** (3 tests): Empty files, special chars, paths with spaces
- **TestUnwatchCleansUpResources** (1 test): Event buffer cleanup
- **TestWatcherAPIStartTime** (2 tests): Start time tracking

## Test Results

- **Before:** 714 tests total
- **After:** 751 tests total (37 new)
- All tests pass

## Acceptance Criteria Status

- [x] POST /watch returns 201 with session_id and status
- [x] POST /watch returns 400 for missing fields
- [x] POST /watch returns 404 for file not found
- [x] POST /watch returns 409 for duplicate session
- [x] DELETE /unwatch returns 204 on success
- [x] DELETE /unwatch returns 404 for not found
- [x] GET /sessions returns all sessions with status
- [x] GET /sessions returns empty list when no sessions
- [x] GET /health returns status, session count, uptime
- [x] GET /sessions/{id}/events returns 404 for unknown session
- [x] SSE endpoint delegates to SSE module

## Testing DoD Status

- [x] Test POST /watch success (201)
- [x] Test POST /watch missing fields (400)
- [x] Test POST /watch file not found (404)
- [x] Test POST /watch duplicate session (409)
- [x] Test DELETE /unwatch success (204)
- [x] Test DELETE /unwatch not found (404)
- [x] Test GET /sessions returns all sessions
- [x] Test GET /sessions empty list
- [x] Test GET /health returns status
- [x] Test GET /sessions/{id}/events returns SSE stream (404 case tested)
- [x] Integration test: watch → unwatch flow

## Dependencies

- Uses #49 (ConfigManager) - for session config CRUD
- Uses #50 (StateManager) - for state file management
- Uses #51 (FileWatcher) - for file watching
- Uses #53 (EventBufferManager) - for event buffering
- Uses #54 (SSEManager) - for SSE streaming

## Spec Reference

Implements § API Reference from `.claude/specs/session-watcher-service.md`.
