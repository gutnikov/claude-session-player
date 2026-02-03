# Issue #56: Add WatcherService class integrating all components

## Summary

Implemented `WatcherService` class that orchestrates all watcher components (ConfigManager, StateManager, FileWatcher, transformer, EventBufferManager, SSEManager, WatcherAPI) with proper lifecycle management and event flow coordination. Also added CLI entry point with signal handling.

## Changes Made

### New Files

1. **`claude_session_player/watcher/service.py`**
   - `WatcherService` dataclass with:
     - `__init__(config_path, state_dir, host, port)` - initialization with optional dependency injection
     - `start()` - async startup sequence
     - `stop()` - async graceful shutdown
     - `watch(session_id, path)` - add session to watch
     - `unwatch(session_id)` - remove session from watch
     - `_load_and_resume_sessions()` - load config and resume from saved state
     - `_save_all_states()` - persist state for all sessions
     - `_on_file_change(session_id, lines)` - handle file change events
     - `_on_file_deleted(session_id)` - handle file deletion events
     - `is_running` property for lifecycle state

2. **`claude_session_player/watcher/__main__.py`**
   - `parse_args()` - command line argument parsing
   - `setup_logging()` - logging configuration
   - `run_service()` - async service runner
   - `main()` - CLI entry point
   - Signal handling for SIGINT/SIGTERM
   - Command-line args: `--host`, `--port`, `--config`, `--state-dir`, `--log-level`

3. **`tests/watcher/test_service.py`**
   - 41 comprehensive tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added export for `WatcherService`

## Design Decisions

### Dependency Injection

Components can be injected for testing, or auto-created:

```python
service = WatcherService(
    config_path=Path("config.yaml"),
    state_dir=Path("state"),
    # Optional: inject components for testing
    config_manager=mock_config_manager,
)
```

### Event Flow

```
FileWatcher detects change
    ↓
_on_file_change(session_id, lines)
    ↓
StateManager.load(session_id) → context
    ↓
transform(lines, context) → events, new_context
    ↓
StateManager.save(session_id, new_state)
    ↓
for event in events:
    EventBufferManager.add_event(session_id, event)
    SSEManager.broadcast(session_id, event_id, event)
```

### Startup Sequence

1. Load config.yaml
2. For each session in config:
   - Load state (or create fresh if missing/corrupt)
   - Validate file exists (remove from config if not)
   - Add to FileWatcher with saved position
3. Start FileWatcher
4. Start HTTP server

### Shutdown Sequence

1. Stop HTTP server
2. Stop FileWatcher
3. Save all session states
4. Send `session_ended` to all SSE clients
5. Close all SSE connections

### Signal Handling

CLI uses Python's `signal` module for clean shutdown:
- SIGINT (Ctrl+C) → triggers shutdown
- SIGTERM (kill signal) → triggers shutdown

## Test Coverage

41 tests organized by functionality:

- **TestWatcherServiceCreation** (6 tests): Initialization and dependency injection
- **TestWatcherServiceStartup** (5 tests): Startup sequence and state resumption
- **TestWatcherServiceShutdown** (4 tests): Graceful shutdown and state saving
- **TestWatcherServiceWatch** (5 tests): watch() method validation and behavior
- **TestWatcherServiceUnwatch** (6 tests): unwatch() cleanup across components
- **TestWatcherServiceFileChange** (4 tests): Event flow on file changes
- **TestWatcherServiceFileDeletion** (4 tests): Handling of deleted files
- **TestCorruptStateHandling** (1 test): Graceful recovery from corrupt state
- **TestWatcherServiceIntegration** (3 tests): Full lifecycle and restart scenarios
- **TestCLIMain** (3 tests): CLI argument parsing and logging setup

## Test Results

- **Before:** 751 tests total
- **After:** 792 tests total (41 new)
- All tests pass

## Acceptance Criteria Status

- [x] Service starts and loads existing config
- [x] Service processes file changes end-to-end
- [x] Watch/unwatch coordinate all components
- [x] Graceful shutdown saves state
- [x] CLI entry point works
- [x] Signal handling for clean shutdown

## Testing DoD Status

- [x] Test service startup loads config
- [x] Test service startup resumes from saved state
- [x] Test file change triggers event flow
- [x] Test watch() adds to all components
- [x] Test unwatch() removes from all components + emits event
- [x] Test shutdown saves state
- [x] Test shutdown closes SSE connections
- [x] Test corrupt state file handled (fresh context)
- [x] Test missing file on startup removed from config
- [x] Integration test: full lifecycle

## Dependencies

All dependencies from issues #48-#55 are utilized:
- #48 (serialization) - via ProcessingContext.to_dict/from_dict
- #49 (ConfigManager) - session configuration
- #50 (StateManager) - state persistence
- #51 (FileWatcher) - file change detection
- #52 (transformer) - line-to-event processing
- #53 (EventBuffer) - event buffering
- #54 (SSE) - event broadcasting
- #55 (API) - HTTP endpoints

## Usage

### Running the service

```bash
# Start with defaults
python -m claude_session_player.watcher

# Custom configuration
python -m claude_session_player.watcher \
    --host 0.0.0.0 \
    --port 9000 \
    --config /etc/watcher/config.yaml \
    --state-dir /var/lib/watcher/state \
    --log-level DEBUG
```

### API Endpoints

- `POST /watch` - Add session to watch
- `DELETE /unwatch/{session_id}` - Remove session
- `GET /sessions` - List all sessions
- `GET /sessions/{session_id}/events` - SSE stream
- `GET /health` - Health check
