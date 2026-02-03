# Issue #95: Update ConfigManager with index/search config and migration

## Summary

Extended `ConfigManager` to support the new index and search configuration sections with automatic migration from older config formats and environment variable overrides.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/config.py`**
   - Added `IndexConfig` dataclass with fields:
     - `paths`: list of index directories (default: `["~/.claude/projects"]`)
     - `refresh_interval`: refresh interval in seconds (default: 300)
     - `max_sessions_per_project`: max sessions per project (default: 100)
     - `include_subagents`: whether to include subagent sessions (default: False)
     - `persist`: whether to persist index to disk (default: True)
     - `expand_paths()` method to expand ~ and resolve paths
   - Added `SearchConfig` dataclass with fields:
     - `default_limit`: default results per page (default: 5)
     - `max_limit`: maximum results per page (default: 10)
     - `default_sort`: default sort order (default: "recent")
     - `state_ttl_seconds`: search state TTL (default: 300)
   - Added `migrate_config()` function for automatic migration:
     - Adds default index config if missing
     - Adds default search config if missing
     - Adds telegram mode field if missing
   - Added `apply_env_overrides()` function for environment variables:
     - `CLAUDE_INDEX_PATHS`: comma-separated index paths
     - `CLAUDE_INDEX_REFRESH_INTERVAL`: refresh interval override
     - `TELEGRAM_WEBHOOK_URL`: webhook URL override
   - Added `expand_paths()` utility function
   - Updated `ConfigManager`:
     - Added `_index_config` and `_search_config` private fields
     - Updated `load()` to:
       - Apply config migration
       - Apply environment overrides
       - Load index and search configs
     - Updated `save()` to include index and search sections
     - Added `get_index_config()` and `set_index_config()`
     - Added `get_search_config()` and `set_search_config()`

2. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `IndexConfig`, `SearchConfig`
   - Added exports for `migrate_config`, `apply_env_overrides`, `expand_paths`
   - Updated `__all__` list

3. **`tests/watcher/test_config.py`**
   - Added 46 new tests covering:
     - `TestIndexConfig`: 8 tests for dataclass functionality
     - `TestSearchConfig`: 7 tests for dataclass functionality
     - `TestMigrateConfig`: 7 tests for migration logic
     - `TestApplyEnvOverrides`: 7 tests for environment overrides
     - `TestExpandPaths`: 4 tests for path expansion
     - `TestConfigManagerIndexConfig`: 4 tests for index config methods
     - `TestConfigManagerSearchConfig`: 4 tests for search config methods
     - `TestConfigManagerMigration`: 4 tests for migration integration
     - `TestConfigFullRoundtrip`: 1 integration test

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestIndexConfig | 8 | Dataclass creation, defaults, to_dict, from_dict, expand_paths |
| TestSearchConfig | 7 | Dataclass creation, defaults, to_dict, from_dict |
| TestMigrateConfig | 7 | Migration of index, search, telegram mode |
| TestApplyEnvOverrides | 7 | Environment variable overrides |
| TestExpandPaths | 4 | Path expansion (~, relative paths) |
| TestConfigManagerIndexConfig | 4 | Index config getter/setter/persistence |
| TestConfigManagerSearchConfig | 4 | Search config getter/setter/persistence |
| TestConfigManagerMigration | 4 | ConfigManager migration integration |
| TestConfigFullRoundtrip | 1 | Full config file round-trip |

**Total: 46 new tests, all passing**
**Overall config tests: 134 tests, all passing**

## Design Decisions

### Config Migration Strategy

Migration is applied during `load()` in memory only - the file is not automatically rewritten. This ensures:
- Existing configs continue to work without modification
- Migration happens transparently on load
- Users can opt-in to new format by calling `save()`

### Environment Variable Priority

Environment variables override file config values. The order of application:
1. Load raw YAML
2. Apply old format migration (list → dict)
3. Apply config migration (add defaults)
4. Apply environment overrides

### IndexConfig.expand_paths()

The `expand_paths()` method is provided on the dataclass itself rather than as a standalone function. This allows for future extension if needed (e.g., validation) while keeping related functionality together.

### Default Values

Defaults match the spec exactly:
- Index paths: `["~/.claude/projects"]`
- Refresh interval: 300 seconds (5 minutes)
- Max sessions per project: 100
- Include subagents: False
- Persist: True
- Default limit: 5
- Max limit: 10
- Default sort: "recent"
- State TTL: 300 seconds

## Acceptance Criteria Status

- [x] New config sections supported (index, search)
- [x] Dataclasses for type-safe access (IndexConfig, SearchConfig)
- [x] Migration from old format automatic
- [x] Environment overrides working
- [x] Path expansion working (~)
- [x] Default values applied correctly
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Load config with all sections
- [x] Unit test: Migrate config without index section
- [x] Unit test: Migrate config without search section
- [x] Unit test: Environment variable overrides
- [x] Unit test: Path expansion (~)
- [x] Unit test: Default values applied correctly
- [x] Integration test: Load real config file (full roundtrip test)

## Spec Reference

Implements issue #95 from `.claude/specs/session-search-api.md`:
- Configuration section (lines 1157-1254)

## Notes

- BotConfig already had `telegram_mode`, `telegram_webhook_url`, and `slack_signing_secret` fields from issue #93, so no changes needed there
- Pre-existing test failures in some watcher tests are due to missing optional dependencies (slack_sdk, aiogram) and are unrelated to this change
- The validation for webhook_url when mode=webhook is handled at the TelegramBotConfig level in telegram_bot.py (from issue #93)
