# Issue #86: Add SearchEngine with query parsing and ranking algorithm

## Summary

Implemented the `SearchEngine` component that parses search queries, filters sessions, and ranks results by relevance. This is the core search logic used by both REST API and bot commands.

## Changes Made

### New Files

1. **`claude_session_player/watcher/search.py`**
   - `parse_time_range()`: Parses time range strings like '7d', '2w', '1m'
   - `parse_iso_date()`: Parses ISO date strings
   - `parse_query()`: Parses raw query strings into SearchParams
   - `calculate_score()`: Calculates relevance score for ranking
   - `SearchFilters`: Dataclass for project/date filters
   - `SearchParams`: Dataclass for parsed search parameters
   - `SearchResults`: Dataclass for paginated search results
   - `SearchEngine`: Main class for querying indexed sessions

2. **`tests/watcher/test_search.py`**
   - 44 tests covering all functionality

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestParseTimeRange | 5 | Time range parsing (d/w/m) |
| TestParseIsoDate | 4 | ISO date parsing |
| TestParseQuery | 12 | Query parsing (terms, phrases, options) |
| TestCalculateScore | 5 | Ranking algorithm tests |
| TestSearchEngine | 12 | Integration tests with populated index |
| TestSearchFilters | 2 | Project filter edge cases |
| TestSearchParamsDefaults | 3 | Default values |

**Total: 44 new tests, all passing**

## Design Decisions

### Query Parsing

Uses `shlex.split()` for robust handling of quoted strings:
- `"auth bug"` → single term `["auth bug"]`
- `auth bug` → multiple terms `["auth", "bug"]`
- Falls back to simple split if shlex fails (unbalanced quotes)

### Option Parsing

Supports both long and short flags per spec:
- `--project` / `-p`: Project filter (substring match)
- `--last` / `-l`: Time range (7d, 2w, 1m)
- `--since` / `-s`: ISO date (start)
- `--until` / `-u`: ISO date (end)
- `--sort`: Sort mode (recent, oldest, size, duration)

### Ranking Algorithm

Implemented exactly per spec:

```python
def calculate_score(session, query, terms, now):
    score = 0.0

    # Summary matches (2.0 per term)
    if session.summary:
        summary_lower = session.summary.lower()
        for term in terms:
            if term.lower() in summary_lower:
                score += 2.0
        # Exact phrase bonus (1.0)
        if query and query.lower() in summary_lower:
            score += 1.0

    # Project name matches (1.0 per term)
    project_lower = session.project_display_name.lower()
    for term in terms:
        if term.lower() in project_lower:
            score += 1.0

    # Recency boost (0.0-1.0, decays over 30 days)
    days_old = (now - session.modified_at).days
    recency_boost = max(0.0, 1.0 - (days_old / 30))
    score += recency_boost

    return score
```

### Filtering

- Project filter: case-insensitive substring match on display name
- Date filters: compare against `modified_at`
- Term filter: OR logic (any term matches), minimum 2 chars per term
- Session ID: exact match supported

### Sort Modes

- `recent`: Sort by score (descending), then modified_at (descending)
- `oldest`: Sort by modified_at (ascending)
- `size`: Sort by size_bytes (descending)
- `duration`: Sort by duration_ms (descending), nulls last

## Test Results

- **New tests:** 44 tests, all passing
- **Indexer tests:** 47 tests, all passing
- **Core tests:** 474 passing (2 fail due to missing slack_sdk dependency)
- Ran with: `python3 -m pytest tests/watcher/test_search.py -xvs`

## Acceptance Criteria Status

- [x] `SearchEngine` class implemented
- [x] Query parsing handles all option formats
- [x] Ranking algorithm matches spec exactly
- [x] Pagination (offset/limit) works correctly
- [x] All sort modes work
- [x] Empty query returns all sessions sorted by recency
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Parse simple query `"auth bug"`
- [x] Unit test: Parse quoted phrase `'"auth bug"'`
- [x] Unit test: Parse with project filter `"auth -p trello"`
- [x] Unit test: Parse with time filter `"-l 7d"`
- [x] Unit test: Parse combined filters
- [x] Unit test: Ranking prioritizes summary matches over project matches
- [x] Unit test: Recency boost calculation
- [x] Unit test: Sort by recent/oldest/size
- [x] Integration test: Search against populated index

## Spec Reference

Implements issue #86 from `.claude/specs/session-search-api.md`:
- Search Syntax section
- Ranking Algorithm section
- Query Format and Options

## Notes

- No external runtime dependencies (stdlib only)
- Uses `shlex` for robust quoted string handling
- All case-insensitive comparisons use `.lower()`
- Search terms under 2 characters are filtered out per spec
