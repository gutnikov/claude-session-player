# Issue #117: Integrate SearchDatabase with SessionIndexer

## Summary

Implemented `SQLiteSessionIndexer` - a new indexer class that uses `SearchDatabase` (SQLite) instead of JSON for persistent storage. This provides efficient incremental updates via mtime tracking and full-text search capabilities through FTS5.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/indexer.py`**
   - Added imports for `AsyncIterator` from `collections.abc` and TYPE_CHECKING imports
   - Added `SQLiteSessionIndexer` class (new, 350+ lines):
     - `__init__()` - accepts `paths`, `state_dir`, and `config` parameters; creates `SearchDatabase` instance
     - `initialize()` / `close()` - lifecycle management
     - `build_full_index()` - full rebuild with batching (100 sessions/batch) and mtime storage
     - `incremental_update()` - detects new/modified/deleted files based on mtime tracking
     - `_scan_directory()` - async generator that yields `IndexedSession` objects
     - `_index_session_file()` - extracts metadata from session files using existing `extract_session_metadata()`
     - `_should_skip()` - filters hidden files and .tmp files
     - `get_session()` - retrieve session by ID
     - Search delegation methods: `search()`, `search_ranked()`, `get_projects()`, `get_stats()`

2. **`claude_session_player/watcher/__init__.py`**
   - Added import for `SQLiteSessionIndexer` from indexer module
   - Added `SQLiteSessionIndexer` to `__all__` exports

### New Files

1. **`tests/watcher/test_sqlite_indexer.py`**
   - 30 comprehensive tests organized into 8 test classes:
     - `TestSQLiteSessionIndexerInitialization` (3 tests)
     - `TestBuildFullIndex` (6 tests)
     - `TestIncrementalUpdate` (4 tests)
     - `TestSearchDelegation` (4 tests)
     - `TestSubagentHandling` (3 tests)
     - `TestIntegration` (5 tests)
     - `TestEdgeCases` (5 tests)

## Design Decisions

### Separate Class

Created `SQLiteSessionIndexer` as a new class rather than modifying the existing `SessionIndexer`. This:
- Maintains backward compatibility with existing code using `SessionIndexer`
- Allows gradual migration to SQLite-backed indexing
- Follows the spec's design of a clean separation

### Mtime Storage in build_full_index

The `build_full_index()` method now stores file mtimes during the initial build. This is essential for `incremental_update()` to correctly detect changes - without stored mtimes, incremental updates would treat all files as "new".

### Batched Operations

Sessions are inserted in batches of 100 to balance:
- Memory usage (not loading all sessions at once)
- Database performance (fewer commits)
- Progress visibility (logging after each batch)

### Lazy Imports

`SearchDatabase` and `IndexedSession` are imported lazily inside methods to avoid circular imports between the indexer and search_db modules.

### has_subagents Detection

The `has_subagents` flag is set after yielding each session by checking if a subagents directory exists. This is done by creating a new `IndexedSession` with the flag set, since dataclasses are immutable.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestSQLiteSessionIndexerInitialization | 3 | Initialize, idempotent, close/reinit |
| TestBuildFullIndex | 6 | Empty, sessions, hidden, temp, corrupt, clears |
| TestIncrementalUpdate | 4 | New, modified, deleted, unchanged |
| TestSearchDelegation | 4 | search, search_ranked, get_projects, get_stats |
| TestSubagentHandling | 3 | Excluded default, included config, has_subagents flag |
| TestIntegration | 5 | Full workflow, incremental after full, persistence, auto-init |
| TestEdgeCases | 5 | Missing dir, empty file, multiple paths, path decoding, timestamps |

**Total: 30 new tests, all passing**
**Overall test suite: 1739 tests, all passing**

## Acceptance Criteria Status

- [x] `SQLiteSessionIndexer.__init__()` accepts `state_dir`
- [x] `SearchDatabase` as internal component
- [x] `initialize()` and `close()` implemented
- [x] `build_full_index()` with batching
- [x] `incremental_update()` with mtime tracking
- [x] `_scan_directory()` async generator
- [x] `_index_session_file()` implemented
- [x] `_should_skip()` for filtering
- [x] Search method delegation
- [x] Module exports updated
- [x] All tests passing

## Test Requirements Status (from issue)

### Unit Tests
- [x] `test_initialize_creates_database` - DB initialized
- [x] `test_build_full_index_empty` - Handles empty directory
- [x] `test_build_full_index_sessions` - Indexes session files
- [x] `test_build_full_index_skips_hidden` - Ignores .files
- [x] `test_build_full_index_skips_temp` - Ignores .tmp files
- [x] `test_build_full_index_handles_corrupt` - Skips corrupt files
- [x] `test_incremental_detects_new` - New files added
- [x] `test_incremental_detects_modified` - Modified files updated
- [x] `test_incremental_detects_deleted` - Deleted files removed
- [x] `test_incremental_unchanged_skipped` - Unchanged files not re-read
- [x] `test_search_delegation` - Search calls DB
- [x] `test_subagents_excluded_default` - Subagents not indexed by default
- [x] `test_subagents_included_config` - Subagents indexed when configured

### Integration Tests
- [x] `test_full_workflow` - Initialize -> build -> search -> close
- [x] `test_incremental_after_full` - Incremental after full build
- [x] `test_persistence_across_restart` - Index survives restart

## Spec Reference

This issue implements the "Integration with SessionIndexer" section from `.claude/specs/sqlite-search-index.md` (lines 976-1158).

## Blocks

This unblocks:
- WatcherService integration
- REST API endpoints
- CLI commands for index management
