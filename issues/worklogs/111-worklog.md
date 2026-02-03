# Issue #111: Implement SearchDatabase core class with schema and connection management

## Summary

Implemented the `SearchDatabase` class - the core SQLite interface for the search index. This includes schema creation, connection management, and all CRUD operations needed for session indexing.

## Changes Made

### New Files

1. **`claude_session_player/watcher/search_db.py`**
   - `IndexedSession` dataclass with 14 fields matching the schema:
     - `session_id`, `project_encoded`, `project_display_name`, `project_path`
     - `summary`, `file_path`
     - `file_created_at`, `file_modified_at`, `indexed_at`
     - `size_bytes`, `line_count`, `duration_ms`
     - `has_subagents`, `is_subagent`
   - `to_row()` method for converting to SQLite row tuple
   - `from_row()` class method for creating from SQLite row
   - `SearchDatabase` class with:
     - Lifecycle methods: `initialize()`, `close()`
     - Connection management: `_get_connection()`
     - CRUD: `upsert_session()`, `upsert_sessions_batch()`, `delete_session()`, `get_session()`, `get_session_by_path()`
     - Metadata: `_set_metadata()`, `_get_metadata()`
     - File tracking: `get_file_mtime()`, `set_file_mtime()`, `get_all_indexed_paths()`
     - Maintenance: `clear_all()`, `verify_integrity()`

2. **`tests/watcher/test_search_db.py`**
   - 38 unit tests organized into 8 test classes:
     - `TestIndexedSession` (5 tests): Dataclass creation, to_row behavior
     - `TestSearchDatabaseInitialization` (4 tests): Table creation, idempotency, state_dir creation
     - `TestSearchDatabaseCRUD` (10 tests): Insert, update, delete, get operations
     - `TestIndexedSessionRoundtrip` (3 tests): Data preservation through DB operations
     - `TestSearchDatabaseMetadata` (3 tests): Metadata get/set operations
     - `TestSearchDatabaseFileMtime` (5 tests): File mtime tracking operations
     - `TestSearchDatabaseMaintenance` (2 tests): clear_all and verify_integrity
     - `TestSearchDatabaseConnection` (2 tests): Connection reuse
     - `TestSearchDatabaseEdgeCases` (4 tests): Special chars, unicode, long summaries, timezones

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added imports for `IndexedSession`, `SearchDatabase`
   - Added to `__all__` exports

## Schema Details

The database schema includes:

```sql
-- Sessions table with all metadata fields
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    project_encoded TEXT NOT NULL,
    project_display_name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    summary TEXT,
    file_path TEXT NOT NULL UNIQUE,
    file_created_at TEXT NOT NULL,
    file_modified_at TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    duration_ms INTEGER,
    has_subagents INTEGER NOT NULL DEFAULT 0,
    is_subagent INTEGER NOT NULL DEFAULT 0
);

-- Indexes for common queries
CREATE INDEX idx_sessions_project ON sessions(project_encoded);
CREATE INDEX idx_sessions_project_name ON sessions(project_display_name COLLATE NOCASE);
CREATE INDEX idx_sessions_modified ON sessions(file_modified_at DESC);
CREATE INDEX idx_sessions_project_modified ON sessions(project_encoded, file_modified_at DESC);

-- Metadata table
CREATE TABLE index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- File mtime tracking for incremental updates
CREATE TABLE file_mtimes (
    file_path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);
```

## Connection Settings

The following SQLite pragmas are set on connection:
- `PRAGMA journal_mode = WAL` - Write-ahead logging for concurrency
- `PRAGMA busy_timeout = 5000` - 5 second timeout on lock contention
- `PRAGMA synchronous = NORMAL` - Balance durability/performance
- `PRAGMA foreign_keys = ON` - Enforce referential integrity

## Design Decisions

### Simplified Implementation

The implementation focuses on the core functionality specified in the issue:
- No FTS5 support yet (will be added in a future issue)
- No search/query methods (will use SearchEngine from existing code)
- No backup methods (can be added later if needed)

### Boolean Storage

SQLite doesn't have a native boolean type, so `has_subagents` and `is_subagent` are stored as integers (0/1) and converted in `to_row()`/`from_row()`.

### Datetime Storage

All datetime values are stored as ISO 8601 strings to preserve timezone information and enable proper sorting.

### UPSERT Pattern

Both single and batch upsert use `ON CONFLICT DO UPDATE` to handle both insert and update cases atomically.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestIndexedSession | 5 | Dataclass creation, to_row |
| TestSearchDatabaseInitialization | 4 | Initialize, idempotent, state_dir |
| TestSearchDatabaseCRUD | 10 | All CRUD operations |
| TestIndexedSessionRoundtrip | 3 | Data preservation |
| TestSearchDatabaseMetadata | 3 | Metadata operations |
| TestSearchDatabaseFileMtime | 5 | File mtime tracking |
| TestSearchDatabaseMaintenance | 2 | clear_all, verify_integrity |
| TestSearchDatabaseConnection | 2 | Connection reuse |
| TestSearchDatabaseEdgeCases | 4 | Edge cases |

**Total: 38 new tests, all passing**
**Overall test suite: 1620 tests, all passing**

## Acceptance Criteria Status

- [x] `SearchDatabase` class implemented
- [x] `IndexedSession` dataclass implemented
- [x] All CRUD operations working
- [x] Connection management with proper pragmas
- [x] Schema created on initialize
- [x] All unit tests passing (38 tests)
- [x] No lint errors
- [x] Docstrings for public methods

## Test Requirements Status (from issue)

- [x] `test_initialize_creates_tables` - Schema created correctly
- [x] `test_initialize_idempotent` - Safe to call multiple times
- [x] `test_upsert_session_insert` - New session inserted
- [x] `test_upsert_session_update` - Existing session updated
- [x] `test_upsert_sessions_batch` - Batch insert works
- [x] `test_delete_session` - Session deleted
- [x] `test_delete_session_not_found` - Returns False for missing
- [x] `test_get_session` - Retrieves by ID
- [x] `test_get_session_by_path` - Retrieves by file path
- [x] `test_get_session_not_found` - Returns None for missing
- [x] `test_metadata_get_set` - Metadata operations work
- [x] `test_file_mtime_tracking` - Mtime operations work
- [x] `test_clear_all` - Removes all data
- [x] `test_verify_integrity` - Returns True for valid DB
- [x] `test_indexed_session_roundtrip` - to_row/from_row preserve data

## Spec Reference

This issue implements the "Component Design" section from `.claude/specs/sqlite-search-index.md`:
- SearchDatabase class (lines 246-453)
- IndexedSession dataclass (lines 271-326)
- CORE_SCHEMA constant (lines 901-939)

## Blocks

This unblocks:
- FTS5 support (future issue)
- Search queries (SearchEngine integration)
- SessionIndexer SQLite integration
