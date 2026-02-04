# Issue #120: Integrate SQLite search index into WatcherService

## Summary

Integrated the `SQLiteSessionIndexer` into `WatcherService`, adding initialization, periodic refresh, checkpoint tasks, backup tasks, and graceful shutdown handling. The health check endpoint was also updated to include SQLite index statistics.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/service.py`**
   - Added import for `SQLiteSessionIndexer` from indexer module
   - Added `sqlite_indexer` field to WatcherService dataclass
   - Added `_checkpoint_task`, `_backup_task`, and `_start_time` fields
   - Updated `__post_init__()` to create `SQLiteSessionIndexer` using database config
   - Updated `start()` method to:
     - Initialize SQLite indexer and database
     - Check if index needs building (total_sessions == 0)
     - Optionally vacuum on startup
     - Start checkpoint task if configured (checkpoint_interval > 0)
     - Start backup task if enabled
   - Updated `stop()` method to:
     - Cancel checkpoint and backup tasks
     - Perform final checkpoint before close
     - Close SQLite indexer connection
   - Updated `_periodic_refresh()` to call `incremental_update()` on SQLite indexer
   - Added `_periodic_checkpoint()` for WAL checkpointing
   - Added `_periodic_backup()` and `_create_backup()` for automated backups
   - Added `_handle_index_error()` for corruption recovery

2. **`claude_session_player/watcher/api.py`**
   - Added TYPE_CHECKING import for `SQLiteSessionIndexer`
   - Added `sqlite_indexer` field to WatcherAPI dataclass
   - Updated `handle_health()` to include SQLite index stats:
     - Prefers SQLite indexer stats when available
     - Falls back to legacy indexer
     - Adds `index` section with sessions, projects, fts_enabled, last_refresh

### New Files

1. **`tests/watcher/test_service_sqlite_indexer.py`**
   - 22 comprehensive tests organized into 10 test classes:
     - `TestSQLiteIndexerInitialization` (3 tests): Service creates indexer
     - `TestServiceBuildIndex` (2 tests): Build on first start, skip when populated
     - `TestPeriodicRefresh` (2 tests): Task started/cancelled
     - `TestPeriodicCheckpoint` (3 tests): Started when configured, disabled, cancelled
     - `TestPeriodicBackup` (2 tests): Started when enabled, disabled by default
     - `TestBackupCreation` (2 tests): Creates file, rotates old backups
     - `TestGracefulShutdown` (2 tests): Final checkpoint, indexer closed
     - `TestHealthCheckWithIndex` (1 test): Health includes SQLite stats
     - `TestErrorRecovery` (2 tests): Recovers from corruption, logs non-corruption
     - `TestVacuumOnStartup` (2 tests): Runs when configured, skipped otherwise
     - `TestServiceSurvivesIndexError` (1 test): Service starts despite errors

## Design Decisions

### Dual Indexer Approach

Kept both the legacy `SessionIndexer` and new `SQLiteSessionIndexer` to maintain backward compatibility. The SQLite indexer is preferred for persistent search, while the legacy indexer is maintained for any code that depends on it.

### Background Task Management

All background tasks (refresh, checkpoint, backup) follow the same pattern:
- Created in `start()` with `asyncio.create_task()`
- Cancelled in `stop()` with proper cleanup
- Run in infinite loops with `asyncio.sleep()` intervals
- Catch `asyncio.CancelledError` to break cleanly

### Error Recovery

The `_handle_index_error()` method detects corruption errors by checking for "corrupt" in the error message and attempts automatic recovery via the database's `_recover_database()` method followed by a full index rebuild.

### Health Check Enhancement

The health check now includes a detailed `index` section with:
- `sessions`: Total indexed sessions
- `projects`: Total indexed projects
- `fts_enabled`: Whether FTS5 is available
- `last_refresh`: ISO timestamp of last incremental update

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestSQLiteIndexerInitialization | 3 | Indexer creation, database config, both indexers |
| TestServiceBuildIndex | 2 | Build on empty, skip when populated |
| TestPeriodicRefresh | 2 | Task started, task cancelled |
| TestPeriodicCheckpoint | 3 | Started when configured, disabled, cancelled |
| TestPeriodicBackup | 2 | Started when enabled, disabled by default |
| TestBackupCreation | 2 | File created, old backups rotated |
| TestGracefulShutdown | 2 | Final checkpoint, indexer closed |
| TestHealthCheckWithIndex | 1 | Health includes SQLite stats |
| TestErrorRecovery | 2 | Corruption recovery, non-corruption logged |
| TestVacuumOnStartup | 2 | Runs when configured, skipped otherwise |
| TestServiceSurvivesIndexError | 1 | Service starts despite errors |

**Total: 22 new tests, all passing**

## Acceptance Criteria Status

- [x] Add indexer initialization in `__init__()`
- [x] Add indexer startup logic in `start()`
- [x] Implement `_periodic_refresh()` background task
- [x] Implement `_periodic_checkpoint()` background task
- [x] Implement `_periodic_backup()` and `_create_backup()`
- [x] Add graceful shutdown for all tasks
- [x] Update health check endpoint
- [x] Add error recovery for index issues
- [x] Expose `SearchEngine` for API/bot handlers (via existing mechanism)

## Test Requirements Status (from issue)

### Unit Tests
- [x] `test_service_initializes_indexer` - Indexer created
- [x] `test_service_builds_index_on_first_start` - Empty index triggers build
- [x] `test_service_skips_build_when_populated` - Existing index not rebuilt
- [x] `test_service_starts_refresh_task` - Background task started
- [x] `test_service_stops_refresh_task` - Task cancelled on stop
- [x] `test_service_checkpoint_runs` - Checkpoint task works
- [x] `test_service_backup_creates_file` - Backup file created
- [x] `test_service_backup_rotates` - Old backups deleted
- [x] `test_health_includes_index_stats` - Health endpoint updated

### Integration Tests
- [x] `test_service_full_lifecycle` - Start -> run -> stop
- [x] `test_service_survives_index_error` - Errors don't crash service

## Spec Reference

This issue implements the "Integration" section from `.claude/specs/sqlite-search-index.md`.

## Blocks

This completes the SQLite search index integration, enabling:
- Full system testing
- Production deployment with persistent search index
