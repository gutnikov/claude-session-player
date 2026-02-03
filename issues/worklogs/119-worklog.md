# Issue #119: Add database configuration to config.yaml

## Summary

Implemented `DatabaseConfig` and `BackupConfig` dataclasses to support SQLite database configuration in `config.yaml`. This adds configuration options for state directory, WAL checkpoint interval, vacuum on startup, and backup settings.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/config.py`**
   - Added `BackupConfig` dataclass with fields:
     - `enabled`: whether backups are enabled (default: False)
     - `path`: backup directory path (default: `~/.claude-session-player/backups`)
     - `keep_count`: number of backups to retain (default: 3)
     - `get_backup_dir()` method to expand path
   - Added `DatabaseConfig` dataclass with fields:
     - `state_dir`: state directory containing search.db (default: `~/.claude-session-player/state`)
     - `checkpoint_interval`: WAL checkpoint interval in seconds (default: 300, 0 = auto)
     - `vacuum_on_startup`: whether to vacuum on startup (default: False)
     - `backup`: nested `BackupConfig`
     - `get_state_dir()` and `get_backup_dir()` methods for path expansion
   - Updated `migrate_config()` to add default database config if missing
   - Updated `apply_env_overrides()` to support:
     - `CLAUDE_STATE_DIR`: override state directory
     - `CLAUDE_DB_CHECKPOINT_INTERVAL`: override checkpoint interval
   - Updated `ConfigManager`:
     - Added `_database_config` private field
     - Updated `load()` to load database config
     - Updated `save()` to include database config in output
     - Added `get_database_config()` and `set_database_config()` methods

2. **`claude_session_player/watcher/__init__.py`**
   - Added imports for `BackupConfig` and `DatabaseConfig`
   - Added to `__all__` exports

3. **`tests/watcher/test_config.py`**
   - Added 33 new tests organized into 7 test classes:
     - `TestBackupConfig` (8 tests): dataclass creation, defaults, serialization, path expansion
     - `TestDatabaseConfig` (10 tests): dataclass creation, nested backup, serialization, path expansion
     - `TestMigrateConfigDatabase` (2 tests): migration adds defaults, preserves existing
     - `TestApplyEnvOverridesDatabase` (4 tests): env var overrides for state_dir and checkpoint_interval
     - `TestConfigManagerDatabaseConfig` (4 tests): getter/setter, persistence
     - `TestConfigManagerDatabaseMigration` (4 tests): migration during load, env override integration
     - `TestConfigDatabaseFullRoundtrip` (1 test): full config file round-trip

## Design Decisions

### Nested BackupConfig

Used a nested `BackupConfig` dataclass rather than flat fields to:
- Mirror the YAML structure exactly
- Allow for future expansion of backup-specific settings
- Keep backup configuration cohesive

### Default Values

Defaults match the spec exactly:
- State directory: `~/.claude-session-player/state`
- Checkpoint interval: 300 seconds (5 minutes)
- Vacuum on startup: False
- Backup enabled: False
- Backup path: `~/.claude-session-player/backups`
- Backup keep count: 3

### Environment Variables

Added two database-specific environment variables:
- `CLAUDE_STATE_DIR`: Overrides the state directory (useful for testing or running multiple instances)
- `CLAUDE_DB_CHECKPOINT_INTERVAL`: Overrides checkpoint interval (useful for performance tuning)

These follow the existing naming convention established by `CLAUDE_INDEX_PATHS` and `CLAUDE_INDEX_REFRESH_INTERVAL`.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestBackupConfig | 8 | Creation, defaults, to_dict, from_dict, roundtrip, path expansion |
| TestDatabaseConfig | 10 | Creation, nested backup, to_dict, from_dict, roundtrip, path expansion |
| TestMigrateConfigDatabase | 2 | Adds defaults, preserves existing |
| TestApplyEnvOverridesDatabase | 4 | state_dir, checkpoint_interval, invalid values, creates section |
| TestConfigManagerDatabaseConfig | 4 | Defaults, from file, setter, persistence |
| TestConfigManagerDatabaseMigration | 4 | Adds defaults, env override, all sections, save includes database |
| TestConfigDatabaseFullRoundtrip | 1 | Full config round-trip with database |

**Total: 33 new tests, all passing**
**Overall config tests: 167 tests, all passing**

## Config YAML Structure

```yaml
# config.yaml

database:
  # State directory containing search.db
  state_dir: "~/.claude-session-player/state"

  # WAL checkpoint interval in seconds (0 = auto)
  checkpoint_interval: 300

  # Run vacuum on startup to reclaim space
  vacuum_on_startup: false

  # Backup settings
  backup:
    enabled: false
    path: "~/.claude-session-player/backups"
    keep_count: 3  # Number of backups to retain
```

## Acceptance Criteria Status

- [x] `BackupConfig` dataclass implemented
- [x] `DatabaseConfig` dataclass implemented
- [x] `ConfigManager` loads database config
- [x] `get_database_config()` method added
- [x] Environment variable overrides work
- [x] Config migration adds defaults for old configs
- [x] All tests passing

## Test Requirements Status (from issue)

### Unit Tests
- [x] `test_database_config_defaults` - Default values correct
- [x] `test_database_config_from_dict` - Parses config correctly
- [x] `test_database_config_to_dict` - Serializes correctly
- [x] `test_database_config_path_expansion` - ~ expanded
- [x] `test_database_config_env_override` - Env vars work
- [x] `test_config_migration_adds_database` - Migration works
- [x] `test_config_load_with_database` - Full config loads

## Spec Reference

This issue implements the "Configuration" section from `.claude/specs/sqlite-search-index.md` (lines 1227-1256).

## Blocks

This unblocks:
- WatcherService integration (can use database config)
- CLI commands (can access database settings)
