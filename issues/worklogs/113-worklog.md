# Issue #113: Implement search and ranking queries in SearchDatabase

## Summary

Implemented the search query methods in `SearchDatabase`, including filtering, pagination, and the spec-compliant ranking algorithm.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/search_db.py`**
   - Added `SearchFilters` dataclass with fields:
     - `query: str | None` - Text search query
     - `project: str | None` - Project name filter (substring)
     - `since: datetime | None` - Modified after date
     - `until: datetime | None` - Modified before date
     - `include_subagents: bool = False` - Include subagent sessions
   - Added `SearchResult` dataclass with fields:
     - `session: IndexedSession` - The matched session
     - `score: float` - Relevance score
   - Implemented `search()` method with:
     - WHERE clause building for all filters
     - FTS5 query path for text search
     - LIKE fallback path when FTS5 unavailable
     - All sort options: recent, oldest, size, duration, name
     - Pagination with offset/limit
     - Returns total count for pagination
   - Implemented `search_ranked()` method with:
     - Python-based ranking algorithm
     - Fetches 3x candidates for better ranking
     - Returns SearchResult objects with scores
   - Implemented `_calculate_score()` matching spec exactly:
     - Summary match: 2.0 per term
     - Exact phrase bonus: +1.0
     - Project name match: 1.0 per term
     - Recency boost: max 1.0 for today, decays over 30 days

2. **`claude_session_player/watcher/__init__.py`**
   - Added imports for `SearchFilters`, `SearchResult`
   - Added to `__all__` exports

3. **`tests/watcher/test_search_db.py`**
   - Added `SearchFilters` import
   - Added `SearchResult` import
   - Added `TestSearchFilters` (2 tests): Dataclass creation
   - Added `TestSearchResult` (2 tests): Dataclass creation
   - Added `TestSearchBasic` (12 tests): Basic search operations
   - Added `TestSearchSorting` (6 tests): Sort option tests
   - Added `TestSearchRanking` (10 tests): Ranking algorithm tests
   - Added `TestSearchEdgeCases` (6 tests): Edge case handling
   - Added `TestSearchIntegration` (2 tests): Integration tests

## Search Filters

```python
@dataclass
class SearchFilters:
    query: str | None = None          # Text search
    project: str | None = None        # Project name filter (substring)
    since: datetime | None = None     # Modified after
    until: datetime | None = None     # Modified before
    include_subagents: bool = False   # Include subagent sessions
```

## Sort Options

| Sort | SQL |
|------|-----|
| `recent` | `file_modified_at DESC` |
| `oldest` | `file_modified_at ASC` |
| `size` | `size_bytes DESC` |
| `duration` | `COALESCE(duration_ms, 0) DESC` |
| `name` | `project_display_name ASC, file_modified_at DESC` |

## Ranking Algorithm

Per spec, the scoring formula:
- Summary matches: 2.0 points per matching term
- Exact phrase bonus: +1.0 if full query appears in summary
- Project name matches: 1.0 points per matching term
- Recency boost: `max(0.0, 1.0 - (days_old / 30))`

Tiebreaker: Sessions with equal scores sorted by modification date (newest first).

## Test Coverage

| Test Class | Count | Description |
|------------|-------|-------------|
| TestSearchFilters | 2 | Dataclass defaults and fields |
| TestSearchResult | 2 | Dataclass creation |
| TestSearchBasic | 12 | No filters, query, project, date, combined, pagination |
| TestSearchSorting | 6 | All sort options + null duration |
| TestSearchRanking | 10 | All ranking factors + tiebreaker |
| TestSearchEdgeCases | 6 | Empty DB, no matches, null summary, case insensitive |
| TestSearchIntegration | 2 | Real session scenarios |

**Total: 40 new tests, all passing**
**Overall test suite: 1682 tests, all passing**

## Design Decisions

### FTS5 vs LIKE Behavior

FTS5 uses word tokenization with the porter stemmer. This means:
- "authentication" as a search term matches the word "authentication"
- "auth" as a search term does NOT match "authentication" (no partial matching)

The LIKE fallback does substring matching, so "auth" would match "authentication".

Tests were written to account for this behavioral difference between FTS5 and LIKE modes.

### Ranking Implementation

The `search_ranked()` method fetches 3x the requested results (plus offset) to have sufficient candidates for ranking. After scoring, results are sorted by:
1. Score descending
2. Modification date descending (tiebreaker)

This ensures relevant results appear first while maintaining chronological ordering among equally-scored results.

### Duration Sort with NULL

Used `COALESCE(duration_ms, 0) DESC` to handle sessions without duration. Sessions with NULL duration sort last.

## Acceptance Criteria Status

- [x] `SearchFilters` dataclass implemented
- [x] `SearchResult` dataclass implemented
- [x] `search()` method working with all filters
- [x] `search_ranked()` method working with spec algorithm
- [x] All sort options working
- [x] Pagination working correctly
- [x] Total count accurate
- [x] FTS and LIKE paths both work
- [x] All tests passing (40 new tests)

## Test Requirements Status (from issue)

### Unit Tests - Basic Search
- [x] `test_search_no_filters` - Returns all sessions
- [x] `test_search_by_query_fts` - FTS search works
- [x] `test_search_by_query_like` - LIKE fallback works
- [x] `test_search_by_project` - Project filter works
- [x] `test_search_by_since` - Date filter works
- [x] `test_search_by_until` - Date filter works
- [x] `test_search_combined_filters` - Multiple filters work
- [x] `test_search_excludes_subagents` - Default excludes subagents
- [x] `test_search_includes_subagents` - Flag includes subagents
- [x] `test_search_pagination` - Offset/limit work
- [x] `test_search_returns_total` - Total count accurate

### Unit Tests - Sorting
- [x] `test_search_sort_recent` - Most recent first
- [x] `test_search_sort_oldest` - Oldest first
- [x] `test_search_sort_size` - Largest first
- [x] `test_search_sort_duration` - Longest first
- [x] `test_search_sort_name` - Alphabetical by project

### Unit Tests - Ranking
- [x] `test_ranking_summary_match` - Summary match adds 2.0
- [x] `test_ranking_exact_phrase` - Exact phrase adds 1.0 bonus
- [x] `test_ranking_project_match` - Project match adds 1.0
- [x] `test_ranking_recency_boost` - Today adds 1.0
- [x] `test_ranking_recency_decay` - 30 days old adds 0.0
- [x] `test_ranking_combined` - All factors combine correctly
- [x] `test_ranking_order` - Higher scores first
- [x] `test_ranking_tiebreaker` - Same score sorted by date

### Integration Tests
- [x] `test_search_real_sessions` - Search against populated DB
- [x] `test_ranking_real_sessions` - Ranking produces expected order

## Spec References

- `.claude/specs/sqlite-search-index.md` - "Search Operations" section (lines 567-757)
- `.claude/specs/session-search-api.md` - "Ranking Algorithm" section (lines 339-374)

## Blocks

This unblocks:
- Aggregation queries (get_projects, get_stats)
- SessionIndexer integration with SearchDatabase
- Search API endpoint implementation
