# Issue #51: Add file watcher with incremental JSONL reading

## Summary

Added comprehensive tests for the `FileWatcher` and `IncrementalReader` classes that were already implemented in `claude_session_player/watcher/file_watcher.py`. The implementation provides cross-platform file watching using `watchfiles` library with incremental reading of new JSONL lines.

## Discovery

Upon investigation, the implementation was already present in `file_watcher.py`:
- `IncrementalReader` class for reading new lines from JSONL files
- `FileWatcher` class for watching multiple files using `watchfiles`
- `WatchedFile` helper dataclass

What was missing: comprehensive test coverage for these classes.

## Changes Made

### New Files

1. **`tests/watcher/test_file_watcher.py`**
   - 43 comprehensive tests covering all functionality
   - Test classes organized by component:
     - `TestIncrementalReaderCreation` (2 tests)
     - `TestIncrementalReaderReadNewLines` (12 tests)
     - `TestIncrementalReaderSeekToLastNLines` (6 tests)
     - `TestWatchedFile` (1 test)
     - `TestFileWatcherCreation` (2 tests)
     - `TestFileWatcherAddRemove` (6 tests)
     - `TestFileWatcherStartStop` (4 tests)
     - `TestFileWatcherProcessInitial` (3 tests)
     - `TestFileWatcherFileChanges` (5 tests)
     - `TestFileWatcherIntegration` (2 tests)
     - `TestFileWatcherErrorHandling` (2 tests)

2. **`issues/worklogs/51-worklog.md`** (this file)

### Existing Files (already implemented)

1. **`claude_session_player/watcher/file_watcher.py`**
   - `IncrementalReader` dataclass with:
     - `read_new_lines() -> tuple[list[dict], int]`
     - `seek_to_last_n_lines(n: int) -> int`
   - `WatchedFile` helper dataclass
   - `FileWatcher` dataclass with:
     - `add(session_id, path, start_position)`
     - `remove(session_id)`
     - `get_position(session_id)`
     - `start()` / `stop()` async methods
     - `process_initial(session_id, last_n_lines)`
     - `is_running` and `watched_sessions` properties

2. **`claude_session_player/watcher/__init__.py`**
   - Already exports `FileWatcher` and `IncrementalReader`

3. **`pyproject.toml`**
   - Already has `watchfiles>=0.21` in `[watcher]` optional dependency

## Implementation Details

### IncrementalReader

Tracks position in JSONL file and reads only new content:
- Handles partial lines at EOF (incomplete JSON not consumed)
- Handles file truncation (position > file size: resets to 0)
- Skips empty lines and malformed JSON with warnings
- Uses byte-level seeking for accurate position tracking

### FileWatcher

Uses `watchfiles.awatch()` for cross-platform file monitoring:
- Watches parent directories to detect file creation/deletion
- Groups changes by session for efficient batch processing
- Non-blocking `start()` creates background task
- Clean shutdown via `stop()` and asyncio.Event
- `process_initial()` processes last N lines for context on new watch

## Test Coverage

Tests cover all acceptance criteria from the issue:

- [x] Test adding file to watch
- [x] Test detecting new lines appended
- [x] Test incremental reading (only new content)
- [x] Test partial line handling (incomplete JSON at EOF)
- [x] Test `seek_to_last_n_lines()` accuracy
- [x] Test file deletion detection
- [x] Test file truncation handling (reset position)
- [x] Test multiple concurrent file watches
- [x] Test malformed JSON lines skipped with warning
- [x] Test start/stop lifecycle
- [x] Integration test with real file writes

## Test Results

- **Before:** 542 tests total
- **After:** 585 tests total (43 new)
- All tests pass

## Acceptance Criteria Status

- [x] Detects new lines appended to watched files
- [x] Only reads new content (from position to EOF)
- [x] Handles partial lines at EOF correctly
- [x] Initial watch processes last 3 lines (via `process_initial()`)
- [x] Detects and reports file deletion
- [x] Handles file truncation gracefully
- [x] Multiple files watched concurrently
- [x] Clean shutdown stops all watches

## Dependencies

- `watchfiles>=0.21` - Already in pyproject.toml under `[watcher]` optional dependency
