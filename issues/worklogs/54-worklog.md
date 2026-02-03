# Issue #54: Add SSE endpoint for streaming session events

## Summary

Implemented `SSEConnection` and `SSEManager` classes that provide Server-Sent Events (SSE) support for streaming session events to subscribers with replay support via `Last-Event-ID`.

## Changes Made

### New Files

1. **`claude_session_player/watcher/sse.py`**
   - `StreamResponse` Protocol - defines the interface for HTTP streaming responses
   - `format_sse_message()` - formats SSE messages with id, event, data fields
   - `format_keepalive()` - formats SSE keep-alive comments
   - `_event_type_name()` - maps internal events to SSE event type names
   - `_event_to_data()` - converts events to JSON-serializable dicts
   - `SSEConnection` class with:
     - `__init__(session_id: str, response: StreamResponse)`
     - `send_event(event_id: str, event_type: str, data: dict) -> None`
     - `send_keepalive() -> None`
     - `close() -> None`
     - `is_closed` property
   - `SSEManager` class with:
     - `__init__(event_buffer: EventBufferManager)`
     - `connect(session_id: str, response: StreamResponse, last_event_id: str | None) -> SSEConnection`
     - `disconnect(connection: SSEConnection) -> None`
     - `broadcast(session_id: str, event_id: str, event: Event) -> None`
     - `close_session(session_id: str, reason: str) -> None`
     - `get_connection_count(session_id: str) -> int`
     - `get_total_connections() -> int`

2. **`tests/watcher/test_sse.py`**
   - 57 comprehensive tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/__init__.py`**
   - Added exports for `SSEConnection` and `SSEManager`

## Design Decisions

### StreamResponse Protocol

Used a Protocol instead of importing `aiohttp.web.StreamResponse` directly to:
- Keep the module decoupled from specific HTTP frameworks
- Allow use with any framework that provides a compatible streaming response
- Avoid adding runtime dependencies

### Connection Storage

Used lists instead of sets for storing connections per session:
- Dataclasses with mutable fields aren't hashable by default
- Using `id(connection)` as key for keepalive tasks to avoid hashability issues
- Lists provide O(n) removal but connections are typically few per session

### Event Type Mapping

| Internal Event | SSE event type |
|---------------|----------------|
| `AddBlock` | `add_block` |
| `UpdateBlock` | `update_block` |
| `ClearAll` | `clear_all` |
| (session ended) | `session_ended` |

### SSE Format

Standard SSE format with all fields on separate lines:
```
id: evt_001
event: add_block
data: {"block_id":"b1","type":"ASSISTANT","content":{...}}

```

- Event data is single-line JSON for SSE compliance
- Keep-alive uses SSE comment format: `: keepalive\n\n`
- Messages terminated with double newline

### Replay Behavior

When a client connects with `Last-Event-ID`:
- If ID is found in buffer: replay events after that ID
- If ID is unknown/evicted: replay all buffered events (client missed too much)
- If no ID provided: replay all buffered events (new connection)

### Keep-Alive

- Interval: 15 seconds (as per spec)
- Uses asyncio task per connection
- Task is cancelled on disconnect
- Sends SSE comment to prevent connection timeout

## Test Coverage

57 tests organized by functionality:

- **TestFormatSseMessage** (6 tests): SSE message formatting
- **TestFormatKeepalive** (1 test): Keep-alive comment format
- **TestEventTypeName** (3 tests): Event type mapping
- **TestEventToData** (3 tests): Event to dict conversion
- **TestSSEConnectionCreation** (1 test): Connection initialization
- **TestSSEConnectionSendEvent** (4 tests): Sending events
- **TestSSEConnectionSendKeepalive** (3 tests): Keep-alive sending
- **TestSSEConnectionClose** (3 tests): Connection closure
- **TestSSEManagerCreation** (1 test): Manager initialization
- **TestSSEManagerConnect** (3 tests): Connection registration
- **TestSSEManagerConnectReplay** (4 tests): Event replay on connect
- **TestSSEManagerDisconnect** (4 tests): Connection cleanup
- **TestSSEManagerBroadcast** (5 tests): Broadcasting to subscribers
- **TestSSEManagerCloseSession** (4 tests): Session closure
- **TestSSEManagerConnectionCounts** (2 tests): Connection counting
- **TestSSEManagerKeepalive** (2 tests): Keep-alive task management
- **TestSSEFormatCompliance** (4 tests): SSE format compliance
- **TestSSEIntegration** (3 tests): Full workflow tests
- **TestKeepaliveInterval** (1 test): Interval constant verification

## Test Results

- **Before:** 657 tests total
- **After:** 714 tests total (57 new)
- All tests pass (excluding 2 unrelated Slack tests that fail due to missing optional dependency)

## Acceptance Criteria Status

- [x] Clients receive events as they occur
- [x] Multiple clients can subscribe to same session
- [x] `Last-Event-ID` replays missed events from buffer
- [x] `session_ended` event sent on file deletion/unwatch
- [x] Keep-alive prevents connection timeout
- [x] Clean disconnect handling
- [x] Proper SSE format (id, event, data fields)

## Testing DoD Status

- [x] Test SSE connection established
- [x] Test event broadcast to single client
- [x] Test event broadcast to multiple clients
- [x] Test `Last-Event-ID` triggers replay
- [x] Test unknown `Last-Event-ID` replays all buffered
- [x] Test client disconnect cleanup
- [x] Test `session_ended` event format
- [x] Test keep-alive sent periodically
- [x] Test SSE format compliance (newlines, field names)
- [x] Integration test with real HTTP client (mocked response)

## Spec Reference

Implements § SSE Endpoint from `.claude/specs/session-watcher-service.md`.

## Notes

- No external dependencies added - uses Protocol for HTTP response interface
- HTTP framework integration (aiohttp/starlette) will be added in a future issue
- The `session_ended` event uses `"session_ended"` as its event_id since it's not from the buffer
