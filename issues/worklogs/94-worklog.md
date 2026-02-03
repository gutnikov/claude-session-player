# Issue #94: Add /search, /projects, /sessions/{id}/preview REST endpoints

## Summary

Implemented REST API endpoints for session search functionality in `WatcherAPI`. These endpoints wrap the `SearchEngine` and `SessionIndexer` components to provide programmatic access to search, used by bots and potentially other clients.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/api.py`**
   - Added imports for datetime, timezone, Path, and search-related types
   - Added `_parse_iso_date()` helper function for date parsing
   - Added new optional fields to `WatcherAPI` dataclass:
     - `indexer`: SessionIndexer for index access
     - `search_engine`: SearchEngine for search queries
     - `search_limiter`: RateLimiter for GET /search (30/min per IP)
     - `preview_limiter`: RateLimiter for GET /sessions/{id}/preview (60/min per IP)
     - `refresh_limiter`: RateLimiter for POST /index/refresh (1/60s global)
   - Implemented new endpoint handlers:
     - `handle_search()`: GET /search - search sessions with filters and pagination
     - `handle_projects()`: GET /projects - list indexed projects with session counts
     - `handle_session_preview()`: GET /sessions/{id}/preview - get session preview events
     - `handle_index_refresh()`: POST /index/refresh - force refresh the session index
     - `handle_search_watch()`: POST /search/watch - attach session from search results
   - Added helper methods:
     - `_get_client_ip()`: Extract client IP for rate limiting (supports X-Forwarded-For)
     - `_get_index_age_seconds()`: Get age of search index
     - `_do_index_refresh()`: Background index refresh task
   - Updated `create_app()` to register new routes

### New Files

1. **`tests/watcher/test_api_search.py`**
   - 34 comprehensive unit tests covering all new endpoints

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestHandleSearchSuccess | 7 | Search success cases (query, filters, pagination, sort) |
| TestHandleSearchErrors | 2 | Search errors (503, 429) |
| TestHandleProjectsSuccess | 2 | Projects list success cases |
| TestHandleProjectsErrors | 1 | Projects error (503) |
| TestHandleSessionPreviewSuccess | 3 | Preview success cases (events, limit) |
| TestHandleSessionPreviewErrors | 2 | Preview errors (404, 503) |
| TestHandleIndexRefreshSuccess | 1 | Refresh success (202) |
| TestHandleIndexRefreshErrors | 2 | Refresh errors (503, 429) |
| TestHandleSearchWatchSuccess | 2 | Search/watch success cases |
| TestHandleSearchWatchErrors | 5 | Search/watch errors (400, 404, 503) |
| TestCreateAppSearchRoutes | 1 | Route registration |
| TestGetClientIp | 3 | Client IP extraction |
| TestGetIndexAgeSeconds | 2 | Index age calculation |
| TestSearchIntegration | 1 | Full search flow integration |

**Total: 34 new tests, all passing**

## Design Decisions

### Optional Search Components

Search components (indexer, search_engine, rate limiters) are optional fields on WatcherAPI. This allows the API to work without search functionality configured - endpoints return 503 when search is unavailable.

### Rate Limiting Strategy

- `GET /search`: 30 requests per minute per IP
- `GET /projects`: Shares search limiter (30/min per IP)
- `GET /sessions/{id}/preview`: 60 requests per minute per IP
- `POST /index/refresh`: 1 request per 60 seconds (global)

Rate limit keys use `api:{ip}` format consistent with spec. X-Forwarded-For header is respected for reverse proxy deployments.

### Preview Event Generation

Preview uses the existing `transformer.transform()` function to process session files and extract events. Only `AddBlock` events are counted and included in the preview, with content truncated to reasonable lengths.

### Search/Watch Endpoint

The `/search/watch` endpoint wraps the existing `/attach` endpoint, adding:
- Session path lookup from index
- Default `replay_count` of 5 (vs 0 for regular attach)
- `session_summary` field in response

Uses a mock request object pattern to reuse existing attach validation and logic.

## Test Results

- **New tests:** 34 tests, all passing
- **Existing API tests:** 38 tests, all passing
- **Total API tests:** 72 tests, all passing
- **Core tests:** 474 passing (2 pre-existing failures due to missing slack_sdk)

## Acceptance Criteria Status

- [x] GET /search with query
- [x] GET /search with filters (project, since, until)
- [x] GET /search pagination (limit, offset)
- [x] GET /search rate limiting
- [x] GET /projects
- [x] GET /sessions/{id}/preview
- [x] GET /sessions/{id}/preview not found (404)
- [x] POST /index/refresh
- [x] POST /index/refresh rate limiting
- [x] POST /search/watch
- [x] Integration test: Full search flow

## Definition of Done Status

- [x] All endpoints implemented
- [x] Request validation (limit bounds, date parsing)
- [x] Rate limiting applied correctly
- [x] Error responses follow spec format
- [x] JSON serialization handles all types
- [x] All tests passing

## Spec Reference

Implements issue #94 from `.claude/specs/session-search-api.md`:
- REST API section (lines 377-569)
- Rate Limiting section (lines 1106-1153)

## Notes

- The `match_score` field in search results is currently always 0.0. Implementing proper scoring would require using the `SearchEngine.search_ranked()` method or similar.
- Preview events don't include timestamps as they're not available from the processed events.
- Pre-existing test failures in `test_service.py` and `test_messaging_integration.py` are due to asyncio event loop issues in Python 3.9 and are unrelated to this change.
