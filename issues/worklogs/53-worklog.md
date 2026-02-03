# Issue #53: Add per-session event buffer with replay support

## Summary

Implemented `EventBuffer` and `EventBufferManager` classes that provide per-session ring buffers for storing the last N events with replay support for SSE reconnection.

## Changes Made

### New Files

1. **`claude_session_player/watcher/event_buffer.py`**
   - `EventBuffer` class with:
     - `__init__(max_size: int = 20)` - configurable buffer size
     - `add(event: Event) -> str` - add event and return its ID
     - `get_since(event_id: str | None) -> list[tuple[str, Event]]` - get events after ID
     - `clear() -> None` - clear all events and reset counter
     - `__len__() -> int` - get current buffer size
   - `EventBufferManager` class with:
     - `__init__(max_size_per_session: int = 20)` - configurable per-session size
     - `get_buffer(session_id: str) -> EventBuffer` - get or create buffer
     - `remove_buffer(session_id: str) -> None` - remove session buffer
     - `add_event(session_id: str, event: Event) -> str` - add event to session
     - `get_events_since(session_id: str, last_id: str | None) -> list[tuple[str, Event]]` - get events for replay

2. **`tests/watcher/test_event_buffer.py`**
   - 44 comprehensive tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `EventBuffer` and `EventBufferManager`

## Design Decisions

### Event ID Format

Used sequential IDs with zero-padding: `evt_001`, `evt_002`, etc.

This format:
- Is human-readable
- Maintains lexicographic ordering for easy comparison
- Avoids UUID overhead
- Resets on `clear()` for cleaner IDs

### Ring Buffer Implementation

Used `collections.deque(maxlen=N)` for O(1) append and automatic eviction:
- No manual size checking needed
- Oldest events automatically evicted when full
- Memory-efficient fixed-size buffer

### Replay Semantics

`get_since(event_id)` behavior:
- `None` → returns all buffered events (new connection)
- Unknown/evicted ID → returns all buffered events (client missed too much)
- Valid ID → returns events after that ID (partial replay)

This matches the SSE `Last-Event-ID` reconnection semantics where missing events trigger a full buffer replay.

### Thread Safety

The implementation is single-threaded async-safe. No locks are used since:
- asyncio runs in a single thread
- Python's GIL protects basic data structure operations
- No long-running operations that could yield between reads/writes

## Test Coverage

44 tests organized by class:

- **TestEventBufferCreation** (3 tests): Default/custom max_size, empty on creation
- **TestEventBufferAdd** (4 tests): Returns ID, sequential IDs, increments length
- **TestEventBufferEviction** (3 tests): Evicts oldest, continuous eviction, counter continues
- **TestEventBufferGetSince** (7 tests): None returns all, valid ID returns subset, unknown/evicted returns all
- **TestEventBufferClear** (2 tests): Empties buffer, resets ID counter
- **TestEventBufferEventTypes** (4 tests): Stores AddBlock, UpdateBlock, ClearAll, mixed types
- **TestEventBufferManagerCreation** (2 tests): Default/custom max_size
- **TestEventBufferManagerGetBuffer** (4 tests): Creates buffer, returns same, separate per session
- **TestEventBufferManagerRemoveBuffer** (3 tests): Removes existing, noop for nonexistent
- **TestEventBufferManagerAddEvent** (3 tests): Returns ID, creates buffer if needed
- **TestEventBufferManagerGetEventsSince** (4 tests): Returns events, after ID, empty for nonexistent
- **TestEventBufferManagerIntegration** (2 tests): Full workflow, eviction per session
- **TestEventIdFormat** (3 tests): Format, ordering, padding

## Test Results

- **Before:** 613 tests total
- **After:** 657 tests total (44 new)
- All tests pass (excluding 2 unrelated Slack tests that fail due to missing optional dependency)

## Acceptance Criteria Status

- [x] Buffer stores last 20 events per session
- [x] Oldest events evicted when buffer full
- [x] `get_since()` returns events after given ID
- [x] Unknown/missing ID returns full buffer contents
- [x] Separate buffer per session
- [x] Clean removal of session buffer

## Testing DoD Status

- [x] Test add events up to max_size
- [x] Test eviction when exceeding max_size (oldest removed)
- [x] Test `get_since()` with valid ID returns subset
- [x] Test `get_since(None)` returns all events
- [x] Test `get_since()` with unknown ID returns all events
- [x] Test `get_since()` with evicted ID returns all events
- [x] Test `clear()` empties buffer
- [x] Test `EventBufferManager` creates buffer per session
- [x] Test `remove_buffer()` cleans up session
- [x] Test event IDs are sequential/ordered

## Spec Reference

Implements § Event Buffer from `.claude/specs/session-watcher-service.md`.
