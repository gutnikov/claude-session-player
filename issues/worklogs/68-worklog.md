# Issue #68: Add messaging dependencies (aiogram, slack-sdk)

## Summary

Added optional `messaging` dependency group with `aiogram>=3.0` and `slack-sdk>=3.0` for Slack & Telegram integration with the session watcher service. Created `deps.py` utility module with availability checks for graceful handling of missing dependencies.

## Changes Made

### New Files

1. **`claude_session_player/watcher/deps.py`**
   - `check_telegram_available()`: Returns `True` if aiogram is installed, `False` otherwise
   - `check_slack_available()`: Returns `True` if slack-sdk is installed, `False` otherwise

2. **`tests/watcher/test_deps.py`**
   - 10 tests covering availability checks and module imports
   - `TestCheckTelegramAvailable`: Tests for aiogram availability check
   - `TestCheckSlackAvailable`: Tests for slack-sdk availability check
   - `TestDepsModuleImports`: Tests for importing from watcher package
   - `TestDepsIntegration`: Integration tests verifying both dependencies available in dev

### Modified Files

1. **`pyproject.toml`**
   - Added `messaging` optional dependency group with `aiogram>=3.0` and `slack-sdk>=3.0`
   - Updated `dev` dependencies to include messaging libraries for testing
   - Preserved existing `slack` and `telegram` groups for backwards compatibility

2. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `check_telegram_available` and `check_slack_available`
   - Added functions to `__all__` list

3. **`uv.lock`**
   - Regenerated with new dependencies (aiogram, slack-sdk, pydantic, etc.)

## Design Decisions

### Preserved Existing Optional Groups

The original `pyproject.toml` had `slack` and `telegram` optional groups used by existing `TelegramConsumer` and `SlackConsumer` modules. Rather than removing these, I preserved them alongside the new `messaging` group to maintain backwards compatibility.

### Simple Availability Checks

The `deps.py` module uses simple try/except import blocks rather than complex version checking. This follows the project's "stdlib only" philosophy for runtime code - the optional dependencies are only used when explicitly needed.

### Dev Dependencies Include Messaging

Added both `aiogram` and `slack-sdk` to dev dependencies so tests can verify the availability checks return `True` when dependencies are installed. This also ensures CI can run all tests.

## Test Coverage

10 new tests in `tests/watcher/test_deps.py`:

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestCheckTelegramAvailable | 3 | aiogram availability check |
| TestCheckSlackAvailable | 2 | slack-sdk availability check |
| TestDepsModuleImports | 2 | Package imports and __all__ |
| TestDepsIntegration | 3 | Both deps available in dev env |

## Test Results

- **Before:** 816 tests
- **After:** 826 tests (10 new)
- All tests pass

## Acceptance Criteria Status

- [x] `pyproject.toml` updated with `messaging` optional dependency group
- [x] Dev dependencies include messaging libraries
- [x] `deps.py` utility module created with availability checks
- [x] `uv lock` regenerated lock file
- [x] Imports work: `from claude_session_player.watcher.deps import check_telegram_available`
- [x] Tests pass with messaging dependencies installed

## Spec Reference

Implements issue #68 from `.claude/specs/messaging-integration.md`:
- Optional dependency group for messaging platforms
- Dependency availability checks for graceful handling
