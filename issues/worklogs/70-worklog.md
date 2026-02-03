# Issue #70: Add DestinationManager for attach/detach lifecycle

## Summary

Implemented `DestinationManager` class to manage the lifecycle of messaging destinations attached to sessions. The manager tracks which destinations are attached to which sessions, manages the keep-alive timer for file watching, and coordinates with `ConfigManager` for persistence.

## Changes Made

### New Files

1. **`claude_session_player/watcher/destinations.py`**
   - `AttachedDestination` dataclass with fields: `type`, `identifier`, `attached_at`
   - `DestinationManager` class implementing:
     - `attach()`: Attach destination to session (starts file watching on first attach)
     - `detach()`: Detach destination from session (starts keep-alive on last detach)
     - `get_destinations()`: Get all destinations for a session
     - `get_destinations_by_type()`: Get destinations filtered by type
     - `has_destinations()`: Check if session has any destinations
     - `restore_from_config()`: Restore state from persisted config on startup
     - `shutdown()`: Cancel all keep-alive tasks on shutdown

2. **`tests/watcher/test_destinations.py`**
   - 28 tests covering all DestinationManager functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `AttachedDestination` and `DestinationManager`
   - Updated `__all__` list

## Design Decisions

### Keep-Alive During Re-attach

When a destination detaches and starts a keep-alive timer, then a new destination attaches before the timer expires, the implementation:
- Cancels the keep-alive timer
- Does NOT call `on_session_start` again (session is already being watched)
- Adds the new destination to runtime state

This is implemented by tracking whether a keep-alive task was running when processing an attach request.

### Runtime State vs Persisted State

- Runtime state (`_destinations` dict): Holds `AttachedDestination` objects with `attached_at` timestamps
- Persisted state (via ConfigManager): Holds destination identifiers only (chat_id, channel)

On `restore_from_config()`, runtime state is populated with current timestamps since original `attached_at` values aren't persisted.

### Idempotent Operations

- `attach()`: Returns `False` if destination already attached (no duplicate)
- `detach()`: Returns `False` if destination not found (no error)

Both operations remain idempotent as specified.

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestAttachedDestination | 2 | dataclass creation |
| TestAttach | 8 | first attach, subsequent attach, idempotent, path from config, errors |
| TestDetach | 4 | removes destination, not found, removes from config, starts keep-alive |
| TestKeepAlive | 2 | expiry stops session, new attach cancels timer |
| TestRestoreFromConfig | 3 | starts sessions, populates state, skips empty |
| TestQueryMethods | 5 | get_destinations, get_destinations_by_type, has_destinations |
| TestShutdown | 1 | cancels keep-alive tasks |
| TestModuleImports | 3 | package imports and __all__ |

## Test Results

- **Before:** 884 tests
- **After:** 912 tests (28 new)
- All tests pass

## Acceptance Criteria Status

- [x] `DestinationManager` class implemented in `claude_session_player/watcher/destinations.py`
- [x] `attach()` handles first-attach file watching start
- [x] `attach()` is idempotent (duplicate attach returns False)
- [x] `detach()` starts keep-alive timer on last destination removal
- [x] Keep-alive timer (5 min default) delays file watching stop
- [x] `restore_from_config()` restores state on service startup
- [x] All state changes persisted to config
- [x] Unit tests cover:
  - [x] First attach starts session
  - [x] Subsequent attaches are idempotent
  - [x] Detach removes destination
  - [x] Last detach starts keep-alive
  - [x] Keep-alive expiry stops session
  - [x] New attach during keep-alive cancels timer
  - [x] Restore from config on startup
- [x] Integration with WatcherService (tested via mocks)

## Spec Reference

Implements issue #70 from `.claude/specs/messaging-integration.md`:
- DestinationManager component for attach/detach lifecycle
- Keep-alive timer for file watching continuation after last detach
- Coordination with ConfigManager for persistence
