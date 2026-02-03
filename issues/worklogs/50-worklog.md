# Issue #50: Add state file manager for session processing state

## Summary

Implemented `StateManager` class that persists `SessionState` (file position + `ProcessingContext`) per session. This enables the Session Watcher Service to resume processing from where it left off after restarts.

## Changes Made

### New Files

1. **`claude_session_player/watcher/state.py`**
   - `SessionState` dataclass with:
     - `file_position: int` - byte offset in the session file
     - `line_number: int` - for debugging/diagnostics
     - `processing_context: ProcessingContext` - tool mappings and current request
     - `last_modified: datetime` - timestamp of last update
     - `to_dict()` / `from_dict()` serialization methods
   - `StateManager` class with:
     - `__init__(state_dir: Path)` - initialize with state directory
     - `load(session_id: str) -> SessionState | None` - load state from file
     - `save(session_id: str, state: SessionState) -> None` - save state to file
     - `delete(session_id: str) -> None` - remove state file
     - `exists(session_id: str) -> bool` - check if state file exists
   - `_sanitize_session_id()` helper for filesystem-safe filenames

2. **`tests/watcher/test_state.py`**
   - 40 comprehensive tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `SessionState` and `StateManager`

## Design Decisions

### State File Format

JSON format matching the spec:
```json
{
    "file_position": 12345,
    "line_number": 42,
    "processing_context": {
        "tool_use_id_to_block_id": {"tu_123": "block_456"},
        "current_request_id": "req_789"
    },
    "last_modified": "2024-01-15T10:30:00+00:00"
}
```

### Atomic Writes

Used `tempfile.mkstemp()` + `os.replace()` pattern:
- Temp file created in same directory as state file (ensures same filesystem)
- `os.replace()` is atomic on POSIX systems
- Temp file cleaned up on failure

### Session ID Sanitization

`_sanitize_session_id()` replaces filesystem-unsafe characters:
- Windows forbidden: `< > : " / \ | ? *`
- Control characters: `\x00-\x1f`
- Collapses multiple underscores
- Strips leading/trailing underscores and dots

### Corrupt State Handling

`load()` returns `None` for:
- Missing state file
- Invalid JSON
- Missing required fields
- Invalid datetime format

This allows the caller to reset to a fresh state gracefully.

### ISO 8601 Datetime

Uses Python's `datetime.isoformat()` and `datetime.fromisoformat()` for:
- Human-readable format
- Timezone preservation
- No external dependencies

## Test Coverage

40 tests organized by class:
- `TestSessionState`: 5 tests (creation, serialization, round-trip)
- `TestSanitizeSessionId`: 8 tests (various sanitization cases)
- `TestStateManagerSave`: 5 tests (create, directory creation, overwrite, sanitize)
- `TestStateManagerLoad`: 6 tests (success, missing, corrupt JSON, invalid fields)
- `TestStateManagerDelete`: 3 tests (success, nonexistent, sanitized ID)
- `TestStateManagerExists`: 3 tests (exists, missing, no directory)
- `TestSaveLoadRoundTrip`: 2 tests (all fields, large context)
- `TestDatetimeSerialization`: 2 tests (UTC, naive)
- `TestAtomicWrite`: 3 tests (no temp files, cleanup on error, property)
- `TestProcessingContextNestedSerialization`: 3 tests (empty, None, string)

## Test Results

- **Before:** 502 tests total
- **After:** 542 tests total (40 new)
- All tests pass

## Acceptance Criteria Status

- [x] Can save/load/delete session state
- [x] State includes file position and ProcessingContext
- [x] Atomic writes prevent corruption
- [x] Corrupt state files handled gracefully (returns None)
- [x] State directory auto-created
- [x] Session IDs sanitized for filenames

## Testing DoD Status

- [x] Test `save()` creates state file with correct JSON
- [x] Test `load()` returns correct SessionState
- [x] Test `delete()` removes state file
- [x] Test `exists()` returns correct boolean
- [x] Test save/load round-trip preserves all fields
- [x] Test missing state file returns None
- [x] Test corrupt JSON returns None (not exception)
- [x] Test state directory created if missing
- [x] Test datetime serialization/deserialization
- [x] Test ProcessingContext nested serialization
- [x] All tests use temp directories

## Dependencies

Uses #48 (serialization methods on ProcessingContext) - already implemented in `events.py`.
