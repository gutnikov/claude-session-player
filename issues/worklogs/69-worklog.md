# Issue #69: Update ConfigManager for destinations and bot credentials

## Summary

Updated `ConfigManager` to support the new config schema with bot credentials and per-session messaging destinations. The implementation provides full backward compatibility with the old config format through automatic migration.

## Changes Made

### Modified Files

1. **`claude_session_player/watcher/config.py`**
   - Added `TelegramDestination` dataclass with `chat_id` field
   - Added `SlackDestination` dataclass with `channel` field
   - Added `SessionDestinations` dataclass to hold lists of destinations
   - Added `BotConfig` dataclass for telegram/slack bot tokens
   - Updated `SessionConfig` to include `destinations` field with default empty
   - Added `to_new_dict()` and `from_new_dict()` methods to `SessionConfig`
   - Added `_is_old_format()` helper function for format detection
   - Added `_migrate_old_format()` helper function for migration
   - Updated `ConfigManager.load()` to handle both old and new formats
   - Updated `ConfigManager.save()` to always write new format
   - Added `ConfigManager.get_bot_config()` to return cached bot config
   - Added `ConfigManager.set_bot_config()` to update bot config in memory
   - Added `ConfigManager.get_destinations()` to get session destinations
   - Added `ConfigManager.add_destination()` for adding destinations (idempotent)
   - Added `ConfigManager.remove_destination()` for removing destinations

2. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `BotConfig`, `SessionDestinations`, `TelegramDestination`, `SlackDestination`
   - Updated `__all__` list

3. **`tests/watcher/test_config.py`**
   - Added 58 new tests for new dataclasses and ConfigManager methods
   - Tests cover: TelegramDestination, SlackDestination, SessionDestinations, BotConfig
   - Tests cover: old format loading, new format loading, migration behavior
   - Tests cover: add_destination, remove_destination, get_destinations
   - Tests cover: idempotent add, validation of empty chat_id/channel

## Design Decisions

### Config Format Migration

The migration happens transparently in memory during `load()`:
- Old format is detected by checking if `sessions` is a list vs dict
- Old sessions are converted with empty destinations
- The file is NOT automatically rewritten - only `save()` writes new format
- This allows for safe testing and gradual migration

### Bot Config Caching

Bot configuration is cached in the `ConfigManager` instance after `load()`:
- `get_bot_config()` returns the cached config
- `set_bot_config()` updates the in-memory config
- The config is persisted to file when `save()` is called

### Idempotent Destination Operations

- `add_destination()` checks for duplicate chat_id/channel before adding
- Adding the same destination twice returns `True` without creating duplicates
- `remove_destination()` returns `False` if destination not found (no error)

### Validation

- Telegram `chat_id` must be non-empty string
- Slack `channel` must be non-empty string
- When creating session via `add_destination()`, path validation follows existing rules

## Config Format Examples

### Old Format (still supported for reading)
```yaml
sessions:
  - id: "session-001"
    path: "/path/to/file.jsonl"
```

### New Format (always written)
```yaml
bots:
  telegram:
    token: "BOT_TOKEN"
  slack:
    token: "xoxb-..."
sessions:
  session-001:
    path: "/path/to/file.jsonl"
    destinations:
      telegram:
        - chat_id: "123456789"
      slack:
        - channel: "C0123456789"
```

## Test Coverage

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestTelegramDestination | 4 | dataclass methods |
| TestSlackDestination | 4 | dataclass methods |
| TestSessionDestinations | 6 | dataclass methods |
| TestBotConfig | 9 | dataclass methods |
| TestSessionConfig | 9 | existing + new format methods |
| TestConfigManagerOldFormat | 3 | old format loading/migration |
| TestConfigManagerSaveFormat | 2 | new format saving |
| TestConfigManagerBotConfig | 4 | bot config methods |
| TestConfigManagerGetDestinations | 3 | get_destinations() |
| TestConfigManagerAddDestination | 11 | add_destination() |
| TestConfigManagerRemoveDestination | 5 | remove_destination() |
| TestConfigMigrationRoundtrip | 2 | full migration flow |

## Test Results

- **Before:** 826 tests
- **After:** 884 tests (58 new)
- All tests pass

## Acceptance Criteria Status

- [x] New dataclasses defined in `config.py`
- [x] `load()` handles both old and new config formats
- [x] Old format auto-migrated on load (in memory, not written back until `save()`)
- [x] `save()` writes new format
- [x] `add_destination()` and `remove_destination()` methods work correctly
- [x] `get_bot_config()` returns bot credentials
- [x] Unit tests cover:
  - [x] Loading old format config
  - [x] Loading new format config
  - [x] Adding/removing telegram destinations
  - [x] Adding/removing slack destinations
  - [x] Idempotent add (no duplicates)
  - [x] Empty destinations by default
- [x] Existing tests still pass

## Spec Reference

Implements issue #69 from `.claude/specs/messaging-integration.md`:
- Updated config schema for bot credentials
- Per-session destination lists
- Backward compatibility with existing config files
