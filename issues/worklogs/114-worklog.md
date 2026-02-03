# Issue #114: Add aggregation queries and statistics to SearchDatabase

## Summary

Implemented `get_projects()` and `get_stats()` aggregation methods in `SearchDatabase` for project listings and index statistics.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/search_db.py`**
   - Added `get_projects()` method with optional date filters (`since`, `until`)
   - Added `get_stats()` method with all required statistics fields
   - Both methods properly exclude subagent sessions from counts

2. **`tests/watcher/test_search_db.py`**
   - Added `TestGetProjects` class (8 tests):
     - `test_get_projects_empty` - Returns empty list for empty DB
     - `test_get_projects_single` - One project with counts
     - `test_get_projects_multiple` - Multiple projects sorted by date
     - `test_get_projects_aggregation` - Counts and totals correct
     - `test_get_projects_excludes_subagents` - Subagent sessions not counted
     - `test_get_projects_since_filter` - Date filter works (since)
     - `test_get_projects_until_filter` - Date filter works (until)
     - `test_get_projects_both_filters` - Both date filters work together
   - Added `TestGetStats` class (4 tests):
     - `test_get_stats_empty` - Returns zeros for empty DB
     - `test_get_stats_populated` - Returns correct counts
     - `test_get_stats_includes_metadata` - FTS status and timestamps
     - `test_get_stats_only_subagents` - Handles subagent-only database

## Implementation Details

### get_projects()

```python
async def get_projects(
    self,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
```

Returns list of projects with aggregated statistics:
- `project_encoded`: str
- `project_display_name`: str
- `project_path`: str
- `session_count`: int (excludes subagents)
- `latest_modified_at`: str (ISO format)
- `total_size_bytes`: int

SQL query groups by `project_encoded` and excludes `is_subagent = 1` sessions.

### get_stats()

```python
async def get_stats(self) -> dict:
```

Returns index statistics:
- `total_sessions`: int (excludes subagents)
- `total_projects`: int (all distinct projects)
- `total_size_bytes`: int (all sessions including subagents)
- `fts_available`: bool
- `last_full_index`: str | None
- `last_incremental_index`: str | None

## Test Coverage

| Test Class | Count | Description |
|------------|-------|-------------|
| TestGetProjects | 8 | Project listing aggregation |
| TestGetStats | 4 | Index statistics |

**Total: 12 new tests, all passing**
**Overall test suite: 1694 tests, all passing**

## Acceptance Criteria Status

- [x] `get_projects()` implemented with date filters
- [x] `get_stats()` implemented with all fields
- [x] Subagent sessions excluded appropriately
- [x] Edge cases handled (empty DB, null values)
- [x] All tests passing (12 new tests)

## Test Requirements Status (from issue)

### Unit Tests - get_projects
- [x] `test_get_projects_empty` - Returns empty list for empty DB
- [x] `test_get_projects_single` - One project with counts
- [x] `test_get_projects_multiple` - Multiple projects sorted by date
- [x] `test_get_projects_aggregation` - Counts and totals correct
- [x] `test_get_projects_excludes_subagents` - Subagent sessions not counted
- [x] `test_get_projects_since_filter` - Date filter works
- [x] `test_get_projects_until_filter` - Date filter works

### Unit Tests - get_stats
- [x] `test_get_stats_empty` - Returns zeros for empty DB
- [x] `test_get_stats_populated` - Returns correct counts
- [x] `test_get_stats_includes_metadata` - FTS status and timestamps

## Spec Reference

This issue implements the "Aggregation Queries" section from `.claude/specs/sqlite-search-index.md` (lines 759-821).

## Blocks

This unblocks:
- REST API endpoints (`/projects`, `/stats`)
- Session search UI with project filtering
