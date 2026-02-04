# Issue #122: Update documentation for SQLite search index

## Summary

Updated README.md and CLAUDE.md with comprehensive documentation for the SQLite search index feature.

## Changes Made

### README.md

1. **Quick Start section**: Added "Search Sessions via API" example showing basic curl command

2. **Database Configuration section**: New section documenting config.yaml database settings:
   - state_dir: Directory for search.db
   - checkpoint_interval: WAL checkpoint timing
   - vacuum_on_startup: Space reclamation option
   - backup settings: enabled, path, keep_count

3. **Index Management section**: New section documenting CLI commands:
   - `index rebuild` - Full index rebuild
   - `index update` - Incremental update
   - `index stats` - Show statistics
   - `index verify` - Check integrity
   - `index vacuum` - Reclaim disk space
   - `index backup` - Create backup
   - `index search` - Test search (debugging)

4. **Troubleshooting section**: New section covering common issues:
   - Search returns no results
   - Database corruption recovery
   - FTS5 not available fallback

### CLAUDE.md

1. **Specifications section**: New section near top listing design documents:
   - sqlite-search-index.md
   - session-search-api.md
   - messaging-integration.md
   - event-driven-renderer.md
   - claude-session-player.md

2. **Search Database section**: New architecture section covering:
   - SearchDatabase class purpose
   - Database schema overview (sessions, sessions_fts, index_metadata, file_mtimes)
   - Search ranking weights (summary: 2.0, exact phrase: +1.0, project: 1.0, recency: 0-1.0)

3. **File Locations updates**:
   - Added `search_db.py` to Search Module
   - Added new Database Files section for runtime files (search.db, search.db-wal, search.db-shm)
   - Added SQLite test files (test_search_db.py, test_search_db_fts.py, test_search_db_ranking.py, test_search_db_maintenance.py, test_search_db_integration.py)

4. **Search Components**: Added SearchDatabase to the components list

5. **Common Tasks**: Added "Working with the Search Database" section with Python examples:
   - Database initialization
   - Basic search with filters
   - Ranked search with scoring
   - Statistics retrieval
   - Proper cleanup

6. **Configuration section**: Extended config.yaml example with:
   - index configuration (paths, refresh_interval, include_subagents)
   - database configuration (state_dir, checkpoint_interval, vacuum_on_startup, backup)

## Files Modified

1. `/Users/agutnikov/work/claude-session-player/README.md`
2. `/Users/agutnikov/work/claude-session-player/CLAUDE.md`

## Verification

- Documentation aligns with actual implementation in `search_db.py`
- Config structure matches sqlite-search-index.md spec
- Test file references match existing test files
- Code examples use actual API from SearchDatabase class

## Acceptance Criteria

- [x] README.md updated with Database Configuration section
- [x] README.md updated with Index Management CLI section
- [x] README.md updated with Troubleshooting section
- [x] CLAUDE.md updated with Specifications section
- [x] CLAUDE.md updated with Search Database architecture section
- [x] CLAUDE.md updated with Database Files in File Locations
- [x] CLAUDE.md updated with SQLite test files
- [x] CLAUDE.md updated with Working with the Search Database common task
- [x] Configuration example extended with database settings
