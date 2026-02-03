# Issue #118: Add CLI commands for index management

## Summary

Implemented CLI commands for managing the search index: `rebuild`, `update`, `stats`, `verify`, `vacuum`, `backup`, and `search`. These commands allow users to manage the SQLite search index without using the REST API.

## Changes Made

### Modified Files

1. **`claude_session_player/cli.py`**
   - Rewrote from simple single-file replay to subcommand-based CLI using argparse
   - Added `index` command group with 7 subcommands
   - Maintained backward compatibility with legacy `claude-session-player <file>` usage
   - Added helper functions for formatting: `_format_size()`, `_format_duration()`, `_format_datetime()`, `_get_db_size()`
   - Implemented async command handlers: `_rebuild()`, `_update()`, `_stats()`, `_verify()`, `_vacuum()`, `_backup()`, `_search()`
   - Uses lazy imports to avoid loading watcher dependencies for simple replay mode

2. **`tests/test_integration.py`**
   - Updated `test_cli_missing_argument_shows_usage` to expect exit code 0 (standard help behavior) instead of 1

### New Files

1. **`tests/test_cli_index.py`**
   - 45 comprehensive tests organized into 12 test classes:
     - `TestFormatSize` (4 tests) - Size formatting
     - `TestFormatDuration` (4 tests) - Duration formatting
     - `TestFormatDatetime` (4 tests) - Datetime formatting
     - `TestGetDbSize` (2 tests) - Database size helper
     - `TestCreateParser` (11 tests) - Argument parsing
     - `TestRebuildCommand` (3 tests) - Rebuild command
     - `TestUpdateCommand` (1 test) - Update command
     - `TestStatsCommand` (1 test) - Stats command
     - `TestVerifyCommand` (2 tests) - Verify command
     - `TestVacuumCommand` (1 test) - Vacuum command
     - `TestBackupCommand` (1 test) - Backup command
     - `TestSearchCommand` (3 tests) - Search command
     - `TestHandleIndexCommand` (1 test) - Error handling
     - `TestCLIHelp` (2 tests) - Help output
     - `TestCLIIntegration` (3 tests) - Subprocess integration
     - `TestMainFunction` (2 tests) - Main entry point

## Design Decisions

### argparse over click

The issue spec suggested using click, but since the project has NO runtime dependencies (stdlib only), I used argparse instead. This maintains the project's zero-dependency policy.

### Backward Compatibility

The CLI maintains backward compatibility with the original `claude-session-player <file>` usage pattern by detecting when a single non-command argument is passed and treating it as a file path.

### Exit Code for Help

Changed behavior to exit with code 0 when showing help (no arguments), which is standard CLI behavior (git, docker, kubectl all do this). Updated the existing test to reflect this change.

### Lazy Imports

The watcher/search_db imports are done inside the command handlers to avoid loading heavy dependencies when just running `claude-session-player <file>` for replay.

### Output Formatting

- Stats output includes: sessions, projects, total size, FTS5 availability, timestamps, database size
- Search output includes: project name, summary, date, size, duration, relevance score
- Uses unicode characters for visual appeal (📅, 📄, ⏱)

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestFormatSize | 4 | B, KB, MB, GB formatting |
| TestFormatDuration | 4 | None, seconds, minutes, hours |
| TestFormatDatetime | 4 | None, empty, valid ISO, invalid |
| TestGetDbSize | 2 | Existing file, missing file |
| TestCreateParser | 11 | All commands and options |
| TestRebuildCommand | 3 | Empty, with sessions, error handling |
| TestUpdateCommand | 1 | Empty index |
| TestStatsCommand | 1 | Shows correct info |
| TestVerifyCommand | 2 | Valid DB, corrupt DB |
| TestVacuumCommand | 1 | Completes successfully |
| TestBackupCommand | 1 | Creates valid file |
| TestSearchCommand | 3 | Results, no results, project filter |
| TestHandleIndexCommand | 1 | Missing subcommand |
| TestCLIHelp | 2 | Main help, index help |
| TestCLIIntegration | 3 | Invalid path, legacy mode, explicit replay |
| TestMainFunction | 2 | No args, help flag |

**Total: 45 new tests, all passing**
**Overall test suite: 1558 tests passing (excluding optional dependency tests)**

## CLI Usage

```bash
# Full rebuild
claude-session-player index rebuild [--paths PATH...] [--state-dir DIR]

# Incremental update
claude-session-player index update [--paths PATH...] [--state-dir DIR]

# Show statistics
claude-session-player index stats [--state-dir DIR]

# Verify integrity
claude-session-player index verify [--state-dir DIR]

# Reclaim space
claude-session-player index vacuum [--state-dir DIR]

# Create backup
claude-session-player index backup -o PATH [--state-dir DIR]

# Search (debug)
claude-session-player index search QUERY [-p PROJECT] [-l LIMIT] [--state-dir DIR]

# Legacy replay (still works)
claude-session-player <session.jsonl>
claude-session-player replay <session.jsonl>
```

## Acceptance Criteria Status

- [x] Add `index` command group to CLI
- [x] Implement `index rebuild` command
- [x] Implement `index update` command
- [x] Implement `index stats` command
- [x] Implement `index verify` command
- [x] Implement `index vacuum` command
- [x] Implement `index backup` command
- [x] Implement `index search` command (debug tool)
- [x] Add progress indicators for long operations (print statements)
- [x] Add error handling with user-friendly messages
- [x] Update `--help` documentation

## Test Requirements Status (from issue)

### Integration Tests
- [x] `test_cli_rebuild` - Rebuild command works
- [x] `test_cli_update` - Update command works
- [x] `test_cli_stats` - Stats command shows correct info
- [x] `test_cli_verify_valid` - Verify returns success
- [x] `test_cli_verify_corrupt` - Verify detects issues
- [x] `test_cli_vacuum` - Vacuum command works
- [x] `test_cli_backup` - Backup creates valid file
- [x] `test_cli_search` - Search returns results

### CLI Tests
- [x] `test_cli_help` - Help text displays correctly
- [x] `test_cli_invalid_path` - Error for non-existent path
- [x] `test_cli_missing_db` - Handles missing database (via stats on empty)

## Spec Reference

This issue implements the "CLI Commands" section from `.claude/specs/sqlite-search-index.md` (lines 1260-1283).

## Blocks

This completes the CLI layer for the search index functionality, enabling:
- Documentation updates
- User-facing documentation
