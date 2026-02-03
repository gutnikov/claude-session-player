# Issue #49: Add config.yaml manager for watched sessions

## Summary

Implemented `ConfigManager` class for CRUD operations on watched session files via `config.yaml`. This is a foundational component for the Session Watcher Service.

## Changes Made

### New Files

1. **`claude_session_player/watcher/__init__.py`**
   - Module exports for `ConfigManager` and `SessionConfig`

2. **`claude_session_player/watcher/config.py`**
   - `SessionConfig` dataclass with `to_dict()`/`from_dict()` serialization
   - `ConfigManager` class with:
     - `load()` - load sessions from YAML file
     - `save(sessions)` - persist sessions with atomic write
     - `add(session_id, path)` - add new session with validation
     - `remove(session_id)` - remove session by ID
     - `get(session_id)` - get session or None
     - `list_all()` - list all sessions

3. **`tests/watcher/__init__.py`**
   - Test module initialization

4. **`tests/watcher/test_config.py`**
   - 30 comprehensive tests covering all functionality

### Modified Files

1. **`pyproject.toml`**
   - Added `watcher = ["pyyaml>=6.0"]` optional dependency

## Design Decisions

### Atomic Writes
Used `tempfile.mkstemp()` + `os.replace()` pattern for atomic writes:
- Temp file created in same directory as config (ensures same filesystem)
- `os.replace()` is atomic on POSIX systems
- Temp file cleaned up on failure

### Validation on Add
`add()` validates:
- Path is absolute (prevents ambiguity)
- Path exists (prevents watching non-existent files)
- Session ID is unique (prevents duplicates)

### Error Types
- `ValueError`: Invalid input (non-absolute path, duplicate ID)
- `FileNotFoundError`: Session file doesn't exist
- `KeyError`: Session not found on remove

### Optional Dependency
Added `pyyaml` as optional dependency under `[watcher]` group:
- Follows existing pattern (slack, telegram optional deps)
- Install with: `pip install claude-session-player[watcher]`

## Test Coverage

30 tests organized by class:
- `TestSessionConfig`: 4 tests (creation, serialization)
- `TestConfigManagerLoad`: 4 tests (missing file, empty file, valid data)
- `TestConfigManagerSave`: 4 tests (create, nested dirs, overwrite, empty)
- `TestConfigManagerAdd`: 5 tests (success, multiple, duplicate, validation)
- `TestConfigManagerRemove`: 3 tests (success, specific only, not found)
- `TestConfigManagerGet`: 3 tests (found, not found, multiple)
- `TestConfigManagerListAll`: 2 tests (empty, populated)
- `TestLoadSaveRoundTrip`: 2 tests (data preservation, special chars)
- `TestAtomicWrite`: 3 tests (no temp files, cleanup on error, property)

## Test Results

- **Before:** 472 tests total
- **After:** 502 tests total (30 new)
- All tests pass

## Acceptance Criteria Status

- [x] Can add/remove/list sessions
- [x] Config persists to YAML file
- [x] Atomic writes prevent corruption
- [x] Handles missing config file gracefully
- [x] Rejects duplicate session IDs
- [x] Validates file paths exist on add

## Testing DoD Status

- [x] Test `add()` creates entry in config
- [x] Test `remove()` deletes entry
- [x] Test `get()` returns correct session or None
- [x] Test `list_all()` returns all sessions
- [x] Test load/save round-trip preserves data
- [x] Test missing config file creates empty config
- [x] Test duplicate session_id raises error
- [x] Test atomic write (simulate crash mid-write)
- [x] Test path validation rejects non-existent files
- [x] All tests use temp directories (no real filesystem pollution)
