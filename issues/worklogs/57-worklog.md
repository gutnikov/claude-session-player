# Issue #57: Add end-to-end tests and update documentation

## Summary

Added comprehensive end-to-end tests for the Session Watcher Service and updated project documentation (README.md and CLAUDE.md) with watcher service information, API endpoints, and usage examples.

## Changes Made

### New Files

1. **`tests/watcher/test_e2e.py`**
   - 20 end-to-end tests covering the complete watcher service flow
   - Tests organized by scenario:
     - `TestWatchAndReceiveEvents` (3 tests): Watch file → append lines → receive SSE events
     - `TestSSEReconnectReplay` (3 tests): Reconnect with Last-Event-ID → replay
     - `TestFileDeletedSessionEnded` (2 tests): File deletion → session_ended event
     - `TestServiceRestartResumption` (2 tests): Service restart → resume from saved state
     - `TestMultipleConcurrentSessions` (3 tests): Multiple sessions concurrently
     - `TestContextCompactionClearAll` (3 tests): Context compaction flows through
     - `TestProgressUpdates` (1 test): Progress message handling
     - `TestEventBufferLimits` (1 test): Event buffer eviction
     - `TestErrorRecovery` (2 tests): Error recovery scenarios

### Modified Files

1. **`README.md`**
   - Added "Session Watcher Service" section
   - Documented CLI usage with all options
   - Documented all API endpoints with curl examples
   - Documented SSE event format
   - Added Python example for subscribing to events

2. **`CLAUDE.md`**
   - Added Watcher Module section to file locations
   - Added watcher test files to test section
   - Added "Running the Watcher Service" task
   - Added "Adding a Session to Watch" task
   - Added "Subscribing to Session Events" task
   - Added "Watcher Architecture" section with component diagram
   - Added "Event Flow" section explaining file change → SSE pipeline
   - Added "Key Components" summary

## Test Coverage

20 new E2E tests covering:

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestWatchAndReceiveEvents | 3 | Watch → append → SSE events |
| TestSSEReconnectReplay | 3 | Last-Event-ID replay |
| TestFileDeletedSessionEnded | 2 | File deletion handling |
| TestServiceRestartResumption | 2 | State persistence across restart |
| TestMultipleConcurrentSessions | 3 | Concurrent session isolation |
| TestContextCompactionClearAll | 3 | ClearAll event flow |
| TestProgressUpdates | 1 | Progress message handling |
| TestEventBufferLimits | 1 | Buffer eviction behavior |
| TestErrorRecovery | 2 | Graceful error handling |

## Test Results

- **E2E tests:** 20 tests, all pass
- **All watcher tests (excluding test_service.py):** 299 tests pass
- **Full test suite (excluding slack + service):** 739 tests pass

Note: `test_service.py` has pre-existing event loop issues when running under Python 3.9 (project targets Python 3.12+). These tests pass individually but fail when run with the full test suite due to async event loop conflicts.

## Design Decisions

### MockStreamResponse

Created a test utility that mimics aiohttp.web.StreamResponse:
- Captures written data for inspection
- Provides `get_events()` helper to parse SSE messages
- Handles connection lifecycle (prepare, write, close)

### Test Isolation

Each E2E test:
- Creates its own WatcherService instance
- Uses temporary directories for config and state
- Uses port 0 to let OS assign ports
- Properly stops the service in finally blocks

### Event Verification

Tests verify:
- Event types (`add_block`, `update_block`, `clear_all`, `session_ended`)
- Event data structure
- Event ordering
- Event replay behavior

## Acceptance Criteria Status

- [x] E2E tests cover happy path
- [x] E2E tests cover error cases
- [x] E2E tests cover reconnection/replay
- [x] README documents all watcher features
- [x] CLAUDE.md updated for watcher module
- [x] All tests pass (excluding pre-existing failures)

## Testing DoD Status

- [x] E2E test: watch → append → SSE event received
- [x] E2E test: SSE reconnect with replay
- [x] E2E test: file deletion handling
- [x] E2E test: service restart persistence
- [x] E2E test: multiple concurrent sessions
- [x] E2E test: context compaction
- [x] Documentation reviewed for accuracy
- [x] Example commands tested and working

## Documentation Added

### README.md
- Installation instructions for watcher dependencies
- CLI usage with all options
- API endpoints with curl examples
- SSE event format reference
- Reconnection and replay behavior
- State persistence explanation
- Python subscription example

### CLAUDE.md
- Watcher module file locations
- Watcher test file locations
- Quick commands for running/using watcher
- Architecture diagram
- Event flow explanation
- Key components summary

## Spec Reference

Implements documentation requirements from `.claude/specs/session-watcher-service.md`, including:
- § API Reference
- § SSE Endpoint
- § Event Buffer (replay semantics)
- § Operational Considerations (startup/shutdown)
