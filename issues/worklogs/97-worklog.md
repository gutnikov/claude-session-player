# Issue #97: Add end-to-end tests for search flow

## Summary

Added comprehensive end-to-end tests for the session search flow, covering REST API endpoints, Slack and Telegram command handlers, and index operations.

## Changes Made

### New Files

1. **`tests/watcher/test_search_e2e.py`**
   - New E2E test module with 29 test cases
   - Covers the complete search flow from indexing through bot interactions

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestSearchApiBasic | 3 | Basic search queries with filters |
| TestSearchApiProjectFilter | 2 | Project filtering |
| TestSearchApiPagination | 2 | Limit and offset pagination |
| TestSearchApiRateLimiting | 1 | Rate limit enforcement |
| TestProjectsApi | 2 | Projects endpoint |
| TestPreviewApi | 1 | Session preview endpoint |
| TestPreviewApiNotFound | 1 | Preview 404 handling |
| TestSlackSearchCommand | 2 | Slack /search command |
| TestSlackFormatSearchResults | 1 | Block Kit formatting |
| TestSlackWatchInteraction | 1 | Watch button callback |
| TestSlackPaginationInteraction | 1 | Pagination callbacks |
| TestTelegramSearchCommand | 1 | Telegram /search command |
| TestTelegramFormatSearchResults | 1 | Markdown + keyboard formatting |
| TestTelegramWatchCallback | 1 | Watch callback |
| TestTelegramPaginationCallback | 1 | Pagination callbacks |
| TestTelegramExpiredState | 1 | Expired state handling |
| TestIndexIncrementalRefresh | 1 | Incremental refresh detection |
| TestIndexPersistence | 1 | Index save/load |
| TestIndexNewSessions | 1 | New session detection |
| TestIndexDeletedSessions | 1 | Deleted session cleanup |
| TestSearchE2EIntegration | 3 | Full flow integration tests |

**Total: 29 tests, all passing**

## Test Fixtures

### search_test_sessions
Creates a temporary directory with test session files:
- `trello-clone/sessions/` - 2 sessions (auth feature, task management)
- `api-server/sessions/` - 1 session (database optimization)
- `mobile-app/sessions/` - 1 session (UI work)

Each session file contains properly structured JSONL with:
- User prompt with session summary
- Assistant response
- Tool calls
- Turn duration

### populated_indexer
Creates a `SessionIndexer` pointed at the test sessions directory with a pre-built index.

### search_engine, search_state_manager, rate_limiters
Standard search components initialized for testing.

## Design Decisions

### Test Isolation
Each test class uses fixtures that create fresh instances, ensuring tests don't affect each other.

### Real Components Over Mocks
Tests use real `SessionIndexer`, `SearchEngine`, and `SearchStateManager` instances rather than mocks, providing higher confidence in integration behavior.

### File-Based Test Data
Test sessions are written to actual files rather than using in-memory structures, testing the full file parsing and indexing pipeline.

### Async Test Pattern
All handler tests are async using `pytest-asyncio`, matching the actual async nature of the handlers.

## Acceptance Criteria Status

- [x] REST API tests: Search with query
- [x] REST API tests: Search with filters (project)
- [x] REST API tests: Pagination (limit, offset)
- [x] REST API tests: Rate limiting
- [x] REST API tests: Projects endpoint
- [x] REST API tests: Preview endpoint
- [x] REST API tests: Preview not found
- [x] Slack tests: /search command returns Block Kit
- [x] Slack tests: Watch callback calls attach
- [x] Slack tests: Pagination updates offset
- [x] Telegram tests: /search sends message
- [x] Telegram tests: Watch callback calls attach
- [x] Telegram tests: Pagination works
- [x] Telegram tests: Expired state handled
- [x] Index tests: Incremental refresh
- [x] Index tests: Persistence (save/load)
- [x] Index tests: New session detection
- [x] Index tests: Deleted session cleanup
- [x] Integration test: Full REST API flow
- [x] Integration test: Full Slack flow
- [x] Integration test: Full Telegram flow

## Test Requirements Status (from issue)

- [x] REST API E2E: GET /search with query
- [x] REST API E2E: GET /search with filters
- [x] REST API E2E: GET /search pagination
- [x] REST API E2E: GET /projects
- [x] REST API E2E: GET /sessions/{id}/preview
- [x] Slack E2E: /search command
- [x] Slack E2E: Watch/Preview buttons
- [x] Slack E2E: Pagination
- [x] Telegram E2E: /search command
- [x] Telegram E2E: Inline keyboard callbacks
- [x] Index E2E: Persistence
- [x] Index E2E: Incremental refresh

## Dependencies

This issue tests components from:
- SessionIndexer (issue #85)
- SearchEngine (issue #86)
- SearchStateManager (issue #88)
- RateLimiter (issue #89)
- SlackCommandHandler (issue #91)
- TelegramCommandHandler (issue #92)
- REST API endpoints (issue #94)

## Notes

- Tests use the actual file parsing pipeline via `transformer.transform()` to verify session content extraction.
- Rate limiter tests verify both per-IP and global rate limiting behavior.
- The Slack handler processes searches asynchronously via `asyncio.create_task()`, so integration tests pre-populate search state for deterministic testing.
- Telegram handler processes searches synchronously, allowing direct state verification.
- Preview endpoint tests verify both success case (events returned) and 404 case (session not found).
