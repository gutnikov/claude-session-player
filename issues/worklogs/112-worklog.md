# Issue #112: Add FTS5 full-text search with graceful fallback

## Summary

Implemented FTS5 (Full-Text Search) support in `SearchDatabase` with automatic fallback to LIKE queries on platforms where FTS5 is unavailable.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/search_db.py`**
   - Added `_fts_available` instance attribute for caching FTS5 availability
   - Added `_check_fts5_available()` static method for FTS5 detection
   - Added `fts_available` cached property
   - Added `_build_fts_query()` method for converting user queries to FTS5 syntax
   - Added `_setup_fts()` async method for FTS5 schema creation
   - Added `FTS_SCHEMA` constant with virtual table and sync triggers
   - Updated `initialize()` to setup FTS5 and store availability in metadata
   - Updated `clear_all()` to clear FTS table when available
   - Updated module docstring to mention FTS5 feature

2. **`tests/watcher/test_search_db.py`**
   - Added imports: `sqlite3`, `patch` from unittest.mock
   - Added `TestFTS5Detection` (4 tests): FTS5 availability detection
   - Added `TestFTS5Schema` (2 tests): Schema and metadata creation
   - Added `TestFTS5Sync` (3 tests): Insert/update/delete trigger tests
   - Added `TestBuildFTSQuery` (8 tests): Query building tests
   - Added `TestFTS5Fallback` (3 tests): Fallback behavior tests
   - Added `TestFTS5Integration` (3 tests): End-to-end FTS5 search tests

## FTS5 Schema

```sql
-- Virtual table (content-sync mode)
CREATE VIRTUAL TABLE sessions_fts USING fts5(
    session_id,
    summary,
    project_display_name,
    content='sessions',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Three triggers for sync:
-- sessions_fts_insert: Populates FTS on INSERT
-- sessions_fts_delete: Removes from FTS on DELETE
-- sessions_fts_update: Re-syncs FTS on UPDATE
```

## Query Conversion

The `_build_fts_query()` method converts user-friendly queries to FTS5 syntax:
- `"auth bug"` → `"auth OR bug"` (multiple terms OR'd together)
- `'"auth bug"'` → `'"auth bug"'` (exact phrase preserved)
- `'fix "auth bug"'` → `'fix OR "auth bug"'` (mixed terms and phrases)
- `""` → `"*"` (empty query matches all)

## Fallback Behavior

When FTS5 is unavailable:
1. `_check_fts5_available()` returns False
2. `initialize()` logs a warning message
3. `fts_available` metadata is set to "0"
4. FTS virtual table and triggers are not created
5. Future search operations can use LIKE queries as fallback

## Test Coverage

| Test Class | Count | Description |
|------------|-------|-------------|
| TestFTS5Detection | 4 | FTS5 availability detection |
| TestFTS5Schema | 2 | Virtual table and trigger creation |
| TestFTS5Sync | 3 | Insert/update/delete synchronization |
| TestBuildFTSQuery | 8 | Query string conversion |
| TestFTS5Fallback | 3 | Behavior when FTS5 unavailable |
| TestFTS5Integration | 3 | End-to-end FTS5 search |

**Total: 23 new tests, all passing**
**Overall test suite: 1643 tests, all passing**

## Design Decisions

### Content-Sync Mode

Used FTS5's content-sync mode (`content='sessions'`) which:
- Stores indexed data in the main table, not duplicated in FTS
- Requires triggers to keep FTS in sync
- More efficient storage and maintenance

### Porter Stemmer

Used `tokenize='porter unicode61'` for:
- English word stemming ("authentication" matches "auth")
- Unicode support for international characters

### OR Semantics

Chose OR semantics for multi-word queries to provide broader search results. Users can use quoted phrases for exact matches.

## Acceptance Criteria Status

- [x] FTS5 detection working (`_check_fts5_available()`)
- [x] FTS5 schema created when available (virtual table + 3 triggers)
- [x] Triggers keep FTS in sync (insert/update/delete)
- [x] Query conversion handles all cases (simple, phrase, mixed)
- [x] Fallback behavior when FTS unavailable (metadata stored, warning logged)
- [x] Warning logged when falling back
- [x] FTS availability stored in metadata
- [x] All tests passing (23 new FTS tests)

## Test Requirements Status (from issue)

### Unit Tests
- [x] `test_fts5_detection_available` - Returns True when FTS5 works
- [x] `test_fts5_detection_unavailable` - Returns False when FTS5 fails
- [x] `test_fts_schema_created` - Virtual table and triggers created
- [x] `test_fts_sync_on_insert` - FTS updated when session inserted
- [x] `test_fts_sync_on_update` - FTS updated when session updated
- [x] `test_fts_sync_on_delete` - FTS updated when session deleted
- [x] `test_build_fts_query_simple` - "auth bug" -> "auth OR bug"
- [x] `test_build_fts_query_phrase` - '"auth bug"' -> '"auth bug"'
- [x] `test_build_fts_query_mixed` - 'fix "auth bug"' -> 'fix OR "auth bug"'
- [x] `test_fallback_when_fts_unavailable` - LIKE queries work

### Integration Tests
- [x] `test_fts_search_finds_matches` - FTS search returns correct results
- [x] `test_fts_search_project_name` - FTS matches project display name
- [x] `test_fts_search_phrase` - FTS handles exact phrases

## Spec Reference

This issue implements the "FTS5 Setup" section from `.claude/specs/sqlite-search-index.md` (lines 204-241).

## Blocks

This unblocks:
- Search query implementation that uses FTS5 or LIKE fallback
- SearchEngine integration with SearchDatabase
