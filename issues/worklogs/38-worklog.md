# Issue #38: Define Consumer Protocol & Event Emitter

## Summary

Implemented the foundational async Consumer protocol and EventEmitter class that enables multiple consumers to process events concurrently in real-time.

## Changes Made

### New Files

1. **`claude_session_player/protocol.py`**
   - Defines the `Consumer` protocol with `@runtime_checkable` decorator
   - `on_event(event: Event) -> None` - async method for processing events
   - `render_block(block: Block) -> str` - method for formatting blocks

2. **`claude_session_player/emitter.py`**
   - `EventEmitter` class for dispatching events to multiple consumers
   - `subscribe(consumer)` - add a consumer to receive events
   - `unsubscribe(consumer)` - remove a consumer
   - `emit(event)` - dispatch event to all consumers via `asyncio.create_task()`
   - Fire-and-forget semantics - emit returns immediately
   - Error isolation - failing consumers don't affect others
   - Structured logging for event dispatch

3. **`tests/test_protocol.py`**
   - Tests for Consumer protocol compliance
   - Tests for mock consumer implementation
   - Tests for sync-style consumer (async method without internal awaits)
   - 13 test cases

4. **`tests/test_emitter.py`**
   - Tests for subscribe/unsubscribe functionality
   - Tests for emit with multiple consumers
   - Tests for fire-and-forget behavior
   - Tests for concurrent processing
   - Tests for error handling (failing consumers)
   - Tests for logging
   - 21 test cases

## Technical Details

### Consumer Protocol

```python
@runtime_checkable
class Consumer(Protocol):
    async def on_event(self, event: Event) -> None: ...
    def render_block(self, block: Block) -> str: ...
```

- Uses `typing.Protocol` with `@runtime_checkable` for duck typing
- Async-only interface (sync consumers simply don't await internally)
- Each consumer implements its own rendering logic

### EventEmitter

```python
class EventEmitter:
    def subscribe(self, consumer: Consumer) -> None
    def unsubscribe(self, consumer: Consumer) -> None
    async def emit(self, event: Event) -> None
```

- Events dispatched via `asyncio.create_task()` (fire-and-forget)
- Multiple consumers can subscribe to a single emitter
- Consumers process events concurrently and independently
- Consumer failures are logged but don't affect other consumers
- Structured logging with event_type, consumer_type context

## Test Coverage

All 329 tests pass:
- 13 new tests in `test_protocol.py`
- 21 new tests in `test_emitter.py`
- All existing tests continue to pass

## Acceptance Criteria Status

- [x] `Consumer` protocol defined with `on_event()` and `render_block()` methods
- [x] `EventEmitter` class implemented with subscribe/emit functionality
- [x] Events dispatched via `asyncio.create_task()`
- [x] Unit tests for emitter with multiple mock consumers
- [x] No external dependencies (stdlib only)
