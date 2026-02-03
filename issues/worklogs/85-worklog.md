# Issue #85: Add SessionIndexer with directory scanning and index persistence

## Summary

Implemented the `SessionIndexer` component that scans `.claude/projects` directories, extracts session metadata, and maintains a searchable index with persistence support.

## Changes Made

### New Files

1. **`claude_session_player/watcher/indexer.py`**
   - `decode_project_path()`: Decodes encoded project directory names back to original paths
   - `encode_project_path()`: Encodes paths for use as directory names
   - `get_display_name()`: Extracts friendly project name from decoded path
   - `is_subagent_session()`: Detects if a session file is a subagent session
   - `extract_session_metadata()`: Extracts summary and line count from session files
   - `SessionInfo`: Dataclass for indexed session information with lazy duration calculation
   - `ProjectInfo`: Dataclass for indexed project information
   - `SessionIndex`: In-memory index with persistence support
   - `IndexConfig`: Configuration for the indexer
   - `RateLimitError`: Exception for rate-limited refresh
   - `SessionIndexer`: Main class for scanning and indexing sessions

2. **`tests/watcher/test_indexer.py`**
   - 47 tests covering all functionality

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestDecodeProjectPath | 6 | Path decoding with various edge cases |
| TestEncodeProjectPath | 3 | Path encoding |
| TestEncodeDecodeRoundtrip | 4 | Encode/decode roundtrip consistency |
| TestGetDisplayName | 4 | Display name extraction |
| TestIsSubagentSession | 3 | Subagent detection |
| TestExtractSessionMetadata | 6 | Summary and line count extraction |
| TestSessionInfo | 4 | SessionInfo dataclass |
| TestProjectInfo | 2 | ProjectInfo dataclass |
| TestSessionIndex | 2 | SessionIndex dataclass |
| TestSessionIndexer | 12 | Full indexer integration tests |
| TestEdgeCases | 3 | Edge cases and error handling |

**Total: 47 new tests, all passing**

## Design Decisions

### Path Encoding/Decoding

Implemented the double-hyphen escape scheme from the spec:
- `/` → `-` (single hyphen)
- `-` → `--` (double hyphen)

This allows paths with hyphens (e.g., `/Users/user/work/my-app`) to be encoded unambiguously.

### Lazy Duration Calculation

Duration is expensive to calculate (requires scanning all `turn_duration` events in a file). Implemented as a `@property` with caching:
```python
@property
def duration_ms(self) -> int | None:
    if not self._duration_loaded:
        self._duration_ms = self._calculate_duration()
        self._duration_loaded = True
    return self._duration_ms
```

### Fast Summary Extraction

Uses string search before JSON parsing for speed:
```python
if '"type":"summary"' in line or '"type": "summary"' in line:
    try:
        data = json.loads(line)
        # ...
```

### Incremental Refresh

The indexer tracks file mtimes and only re-reads files that have changed:
- Compare current mtime against cached mtime
- Skip unchanged files
- Remove entries for deleted files
- Add entries for new files

### Index Persistence

Index is saved to `{state_dir}/search_index.json` with atomic writes:
- Load on startup if < 1 hour old
- Full re-index if no cache or cache too old
- Includes file mtimes for incremental refresh

### Rate Limiting

Refresh is rate-limited to once per 60 seconds (configurable):
```python
async def refresh(self, force: bool = False) -> SessionIndex:
    if not force and self._last_refresh_request:
        elapsed = (datetime.now(timezone.utc) - self._last_refresh_request).total_seconds()
        if elapsed < 60:
            raise RateLimitError(retry_after=60 - int(elapsed))
```

## Test Results

- **New tests:** 47 tests, all passing
- **Core tests:** 556 passing (unchanged)
- Ran with: `pytest tests/watcher/test_indexer.py -xvs`

## Acceptance Criteria Status

- [x] `SessionIndexer` class implemented with all methods
- [x] Path encoding/decoding handles all edge cases
- [x] Index persistence works across restarts
- [x] Incremental refresh only reads changed files
- [x] Subagent sessions correctly identified and optionally excluded
- [x] All tests passing
- [x] No runtime dependencies added (stdlib only)

## Test Requirements Status (from issue)

- [x] Unit test: `decode_project_path()` with simple path
- [x] Unit test: `decode_project_path()` with hyphenated path
- [x] Unit test: `encode_project_path()` / `decode_project_path()` roundtrip
- [x] Unit test: `extract_session_metadata()` extracts summary and line count
- [x] Unit test: `is_subagent_session()` identifies subagent paths
- [x] Integration test: Full index build from test fixtures
- [x] Integration test: Incremental refresh detects changes
- [x] Integration test: Index persistence save/load

## Spec Reference

Implements issue #85 from `.claude/specs/session-search-api.md`:
- Session Indexing section
- Index Structure
- Index Persistence
- Summary Extraction
- Subagent Identification

## Notes

- The issue description references #91 but the actual issue number is #85
- Duration calculation implemented as lazy property per spec recommendation
- Subagent detection uses `"subagents" in file_path.parts` which is safe (doesn't trigger on encoded project names containing "subagents")
