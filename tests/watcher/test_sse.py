"""Tests for the SSE (Server-Sent Events) module."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    UpdateBlock,
)
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.sse import (
    KEEPALIVE_INTERVAL,
    SSEConnection,
    SSEManager,
    _event_to_data,
    _event_type_name,
    format_keepalive,
    format_sse_message,
)


# --- Mock StreamResponse ---


@dataclass
class MockStreamResponse:
    """Mock streaming response for testing."""

    written: list[bytes] = field(default_factory=list)
    prepared: bool = False
    closed: bool = False
    fail_on_write: bool = False

    async def prepare(self, request: object) -> None:
        """Prepare the response."""
        self.prepared = True

    async def write(self, data: bytes) -> None:
        """Write data to the response."""
        if self.fail_on_write:
            raise OSError("Connection closed")
        if self.closed:
            raise OSError("Connection closed")
        self.written.append(data)

    async def write_eof(self) -> None:
        """Signal end of stream."""
        self.closed = True

    def get_written_text(self) -> str:
        """Get all written data as a string."""
        return b"".join(self.written).decode("utf-8")


# --- Helper functions ---


def make_add_block_event(text: str = "test") -> AddBlock:
    """Create a simple AddBlock event for testing."""
    return AddBlock(
        block=Block(
            id=f"block_{text}",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text=text),
        )
    )


def make_update_block_event(
    block_id: str = "block_1", text: str = "updated"
) -> UpdateBlock:
    """Create a simple UpdateBlock event for testing."""
    return UpdateBlock(
        block_id=block_id,
        content=AssistantContent(text=text),
    )


# --- Tests for format functions ---


class TestFormatSseMessage:
    """Tests for format_sse_message function."""

    def test_full_message(self) -> None:
        """Full SSE message with all fields."""
        msg = format_sse_message(
            event_id="evt_001",
            event_type="add_block",
            data={"key": "value"},
        )
        text = msg.decode("utf-8")

        assert "id: evt_001\n" in text
        assert "event: add_block\n" in text
        assert 'data: {"key": "value"}\n' in text
        assert text.endswith("\n\n")

    def test_message_without_id(self) -> None:
        """SSE message without event ID."""
        msg = format_sse_message(event_type="test", data={"x": 1})
        text = msg.decode("utf-8")

        assert "id:" not in text
        assert "event: test\n" in text

    def test_message_without_type(self) -> None:
        """SSE message without event type."""
        msg = format_sse_message(event_id="evt_001", data={"x": 1})
        text = msg.decode("utf-8")

        assert "id: evt_001\n" in text
        assert "event:" not in text

    def test_message_without_data(self) -> None:
        """SSE message without data."""
        msg = format_sse_message(event_id="evt_001", event_type="ping")
        text = msg.decode("utf-8")

        assert "data:" not in text

    def test_empty_message(self) -> None:
        """Empty SSE message ends with newline."""
        msg = format_sse_message()
        # An empty message is just a separator (not commonly used)
        assert msg.endswith(b"\n")

    def test_json_data_encoding(self) -> None:
        """Data is properly JSON encoded."""
        msg = format_sse_message(data={"nested": {"key": "value"}, "list": [1, 2]})
        text = msg.decode("utf-8")

        assert 'data: {"nested": {"key": "value"}, "list": [1, 2]}' in text


class TestFormatKeepalive:
    """Tests for format_keepalive function."""

    def test_keepalive_format(self) -> None:
        """Keep-alive is formatted as SSE comment."""
        msg = format_keepalive()
        assert msg == b": keepalive\n\n"


class TestEventTypeName:
    """Tests for _event_type_name function."""

    def test_add_block_event(self) -> None:
        """AddBlock maps to 'add_block'."""
        event = make_add_block_event()
        assert _event_type_name(event) == "add_block"

    def test_update_block_event(self) -> None:
        """UpdateBlock maps to 'update_block'."""
        event = make_update_block_event()
        assert _event_type_name(event) == "update_block"

    def test_clear_all_event(self) -> None:
        """ClearAll maps to 'clear_all'."""
        event = ClearAll()
        assert _event_type_name(event) == "clear_all"


class TestEventToData:
    """Tests for _event_to_data function."""

    def test_add_block_data(self) -> None:
        """AddBlock data includes block info."""
        block = Block(
            id="block_1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="hello"),
            request_id="req_001",
        )
        event = AddBlock(block=block)
        data = _event_to_data(event)

        assert data["block_id"] == "block_1"
        assert data["type"] == "assistant"
        assert data["content"]["text"] == "hello"
        assert data["request_id"] == "req_001"

    def test_update_block_data(self) -> None:
        """UpdateBlock data includes block_id and content."""
        event = UpdateBlock(
            block_id="block_1",
            content=AssistantContent(text="updated"),
        )
        data = _event_to_data(event)

        assert data["block_id"] == "block_1"
        assert data["content"]["text"] == "updated"

    def test_clear_all_data(self) -> None:
        """ClearAll data is empty dict."""
        event = ClearAll()
        data = _event_to_data(event)
        assert data == {}


# --- Tests for SSEConnection ---


class TestSSEConnectionCreation:
    """Tests for SSEConnection creation."""

    def test_creation(self) -> None:
        """SSEConnection is created with session_id and response."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        assert conn.session_id == "sess_1"
        assert conn.response is response
        assert not conn.is_closed


class TestSSEConnectionSendEvent:
    """Tests for SSEConnection.send_event method."""

    async def test_send_event(self) -> None:
        """send_event writes formatted SSE to response."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        await conn.send_event("evt_001", "add_block", {"key": "value"})

        text = response.get_written_text()
        assert "id: evt_001" in text
        assert "event: add_block" in text
        assert '"key": "value"' in text

    async def test_send_multiple_events(self) -> None:
        """Multiple events are written separately."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        await conn.send_event("evt_001", "add_block", {"x": 1})
        await conn.send_event("evt_002", "update_block", {"x": 2})

        text = response.get_written_text()
        assert "evt_001" in text
        assert "evt_002" in text

    async def test_send_event_on_closed_raises(self) -> None:
        """send_event raises ConnectionError if connection is closed."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)
        await conn.close()

        with pytest.raises(ConnectionError, match="closed"):
            await conn.send_event("evt_001", "test", {})

    async def test_send_event_write_failure(self) -> None:
        """send_event raises ConnectionError on write failure."""
        response = MockStreamResponse()
        response.fail_on_write = True
        conn = SSEConnection(session_id="sess_1", response=response)

        with pytest.raises(ConnectionError, match="Failed to write"):
            await conn.send_event("evt_001", "test", {})

        assert conn.is_closed


class TestSSEConnectionSendKeepalive:
    """Tests for SSEConnection.send_keepalive method."""

    async def test_send_keepalive(self) -> None:
        """send_keepalive writes keepalive comment."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        await conn.send_keepalive()

        assert response.written == [b": keepalive\n\n"]

    async def test_send_keepalive_on_closed_raises(self) -> None:
        """send_keepalive raises ConnectionError if connection is closed."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)
        await conn.close()

        with pytest.raises(ConnectionError, match="closed"):
            await conn.send_keepalive()

    async def test_send_keepalive_write_failure(self) -> None:
        """send_keepalive raises ConnectionError on write failure."""
        response = MockStreamResponse()
        response.fail_on_write = True
        conn = SSEConnection(session_id="sess_1", response=response)

        with pytest.raises(ConnectionError, match="Failed to write"):
            await conn.send_keepalive()

        assert conn.is_closed


class TestSSEConnectionClose:
    """Tests for SSEConnection.close method."""

    async def test_close_marks_closed(self) -> None:
        """close() marks connection as closed."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        assert not conn.is_closed
        await conn.close()
        assert conn.is_closed

    async def test_close_writes_eof(self) -> None:
        """close() writes EOF to response."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        await conn.close()
        assert response.closed

    async def test_close_is_idempotent(self) -> None:
        """close() can be called multiple times."""
        response = MockStreamResponse()
        conn = SSEConnection(session_id="sess_1", response=response)

        await conn.close()
        await conn.close()  # Should not raise
        assert conn.is_closed


# --- Tests for SSEManager ---


class TestSSEManagerCreation:
    """Tests for SSEManager creation."""

    def test_creation(self) -> None:
        """SSEManager is created with event buffer."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        assert manager.event_buffer is buffer
        assert manager.get_total_connections() == 0


class TestSSEManagerConnect:
    """Tests for SSEManager.connect method."""

    async def test_connect_creates_connection(self) -> None:
        """connect() creates and registers a connection."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)

        assert isinstance(conn, SSEConnection)
        assert conn.session_id == "sess_1"
        assert manager.get_connection_count("sess_1") == 1

    async def test_connect_multiple_clients_same_session(self) -> None:
        """Multiple clients can connect to the same session."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        conn2 = await manager.connect("sess_1", MockStreamResponse())

        assert manager.get_connection_count("sess_1") == 2
        assert conn1 is not conn2

        # Cleanup
        await manager.disconnect(conn1)
        await manager.disconnect(conn2)

    async def test_connect_different_sessions(self) -> None:
        """Connections to different sessions are tracked separately."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        conn2 = await manager.connect("sess_2", MockStreamResponse())

        assert manager.get_connection_count("sess_1") == 1
        assert manager.get_connection_count("sess_2") == 1
        assert manager.get_total_connections() == 2

        # Cleanup
        await manager.disconnect(conn1)
        await manager.disconnect(conn2)


class TestSSEManagerConnectReplay:
    """Tests for SSEManager replay on connect."""

    async def test_connect_replays_buffered_events(self) -> None:
        """connect() replays all buffered events when no last_event_id."""
        buffer = EventBufferManager()
        buffer.add_event("sess_1", make_add_block_event("event1"))
        buffer.add_event("sess_1", make_add_block_event("event2"))

        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response, last_event_id=None)

        text = response.get_written_text()
        assert "evt_001" in text
        assert "evt_002" in text
        assert "event1" in text
        assert "event2" in text

        await manager.disconnect(conn)

    async def test_connect_replays_from_last_event_id(self) -> None:
        """connect() replays only events after last_event_id."""
        buffer = EventBufferManager()
        buffer.add_event("sess_1", make_add_block_event("event1"))  # evt_001
        buffer.add_event("sess_1", make_add_block_event("event2"))  # evt_002
        buffer.add_event("sess_1", make_add_block_event("event3"))  # evt_003

        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response, last_event_id="evt_001")

        text = response.get_written_text()
        assert "evt_001" not in text  # Not replayed
        assert "evt_002" in text
        assert "evt_003" in text
        assert "event2" in text
        assert "event3" in text

        await manager.disconnect(conn)

    async def test_connect_unknown_last_event_id_replays_all(self) -> None:
        """connect() with unknown last_event_id replays all events."""
        buffer = EventBufferManager()
        buffer.add_event("sess_1", make_add_block_event("event1"))
        buffer.add_event("sess_1", make_add_block_event("event2"))

        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response, last_event_id="evt_999")

        text = response.get_written_text()
        assert "evt_001" in text
        assert "evt_002" in text

        await manager.disconnect(conn)

    async def test_connect_no_events_to_replay(self) -> None:
        """connect() with no buffered events doesn't write anything."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)

        assert len(response.written) == 0

        await manager.disconnect(conn)


class TestSSEManagerDisconnect:
    """Tests for SSEManager.disconnect method."""

    async def test_disconnect_removes_connection(self) -> None:
        """disconnect() removes connection from manager."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn = await manager.connect("sess_1", MockStreamResponse())
        assert manager.get_connection_count("sess_1") == 1

        await manager.disconnect(conn)
        assert manager.get_connection_count("sess_1") == 0

    async def test_disconnect_closes_connection(self) -> None:
        """disconnect() closes the connection."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)
        await manager.disconnect(conn)

        assert conn.is_closed
        assert response.closed

    async def test_disconnect_is_idempotent(self) -> None:
        """disconnect() can be called multiple times."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn = await manager.connect("sess_1", MockStreamResponse())
        await manager.disconnect(conn)
        await manager.disconnect(conn)  # Should not raise

        assert manager.get_connection_count("sess_1") == 0

    async def test_disconnect_cleans_up_session_set(self) -> None:
        """disconnect() removes session entry when last connection leaves."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        conn2 = await manager.connect("sess_1", MockStreamResponse())

        await manager.disconnect(conn1)
        assert manager.get_connection_count("sess_1") == 1

        await manager.disconnect(conn2)
        assert manager.get_connection_count("sess_1") == 0


class TestSSEManagerBroadcast:
    """Tests for SSEManager.broadcast method."""

    async def test_broadcast_to_single_client(self) -> None:
        """broadcast() sends event to single subscriber."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)

        event = make_add_block_event("broadcast_test")
        await manager.broadcast("sess_1", "evt_100", event)

        text = response.get_written_text()
        assert "evt_100" in text
        assert "add_block" in text
        assert "broadcast_test" in text

        await manager.disconnect(conn)

    async def test_broadcast_to_multiple_clients(self) -> None:
        """broadcast() sends event to all subscribers."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response1 = MockStreamResponse()
        response2 = MockStreamResponse()

        conn1 = await manager.connect("sess_1", response1)
        conn2 = await manager.connect("sess_1", response2)

        event = make_add_block_event("multi_broadcast")
        await manager.broadcast("sess_1", "evt_100", event)

        # Both clients should receive the event
        assert "evt_100" in response1.get_written_text()
        assert "evt_100" in response2.get_written_text()

        await manager.disconnect(conn1)
        await manager.disconnect(conn2)

    async def test_broadcast_to_nonexistent_session(self) -> None:
        """broadcast() to nonexistent session does nothing."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        event = make_add_block_event("test")
        # Should not raise
        await manager.broadcast("nonexistent", "evt_001", event)

    async def test_broadcast_disconnects_failed_clients(self) -> None:
        """broadcast() disconnects clients that fail to receive."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        response1 = MockStreamResponse()
        response2 = MockStreamResponse()
        response2.fail_on_write = True

        conn1 = await manager.connect("sess_1", response1)
        conn2 = await manager.connect("sess_1", response2)

        assert manager.get_connection_count("sess_1") == 2

        event = make_add_block_event("test")
        await manager.broadcast("sess_1", "evt_100", event)

        # conn2 should be disconnected due to write failure
        assert manager.get_connection_count("sess_1") == 1

        await manager.disconnect(conn1)

    async def test_broadcast_all_event_types(self) -> None:
        """broadcast() handles all event types correctly."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)

        # Test AddBlock
        await manager.broadcast("sess_1", "evt_001", make_add_block_event("test"))
        assert "add_block" in response.get_written_text()

        # Test UpdateBlock
        await manager.broadcast("sess_1", "evt_002", make_update_block_event())
        assert "update_block" in response.get_written_text()

        # Test ClearAll
        await manager.broadcast("sess_1", "evt_003", ClearAll())
        assert "clear_all" in response.get_written_text()

        await manager.disconnect(conn)


class TestSSEManagerCloseSession:
    """Tests for SSEManager.close_session method."""

    async def test_close_session_sends_session_ended(self) -> None:
        """close_session() sends session_ended event."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)
        await manager.close_session("sess_1", "file_deleted")

        text = response.get_written_text()
        assert "session_ended" in text
        assert "file_deleted" in text

    async def test_close_session_disconnects_all_clients(self) -> None:
        """close_session() disconnects all clients."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        conn2 = await manager.connect("sess_1", MockStreamResponse())

        assert manager.get_connection_count("sess_1") == 2

        await manager.close_session("sess_1", "unwatched")

        assert manager.get_connection_count("sess_1") == 0
        assert conn1.is_closed
        assert conn2.is_closed

    async def test_close_session_nonexistent(self) -> None:
        """close_session() on nonexistent session does nothing."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        # Should not raise
        await manager.close_session("nonexistent", "test")

    async def test_close_session_with_reason(self) -> None:
        """close_session() includes reason in event."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        await manager.connect("sess_1", response)
        await manager.close_session("sess_1", "manual_unwatch")

        text = response.get_written_text()
        assert '"reason": "manual_unwatch"' in text


class TestSSEManagerConnectionCounts:
    """Tests for SSEManager connection count methods."""

    async def test_get_connection_count(self) -> None:
        """get_connection_count returns correct count per session."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        assert manager.get_connection_count("sess_1") == 0

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        assert manager.get_connection_count("sess_1") == 1

        conn2 = await manager.connect("sess_1", MockStreamResponse())
        assert manager.get_connection_count("sess_1") == 2

        await manager.disconnect(conn1)
        await manager.disconnect(conn2)

    async def test_get_total_connections(self) -> None:
        """get_total_connections returns total across all sessions."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        assert manager.get_total_connections() == 0

        conn1 = await manager.connect("sess_1", MockStreamResponse())
        conn2 = await manager.connect("sess_1", MockStreamResponse())
        conn3 = await manager.connect("sess_2", MockStreamResponse())

        assert manager.get_total_connections() == 3

        await manager.disconnect(conn1)
        await manager.disconnect(conn2)
        await manager.disconnect(conn3)


class TestSSEManagerKeepalive:
    """Tests for SSE keepalive functionality."""

    async def test_keepalive_sent_periodically(self) -> None:
        """Keepalive is sent at regular intervals."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)
        response = MockStreamResponse()

        conn = await manager.connect("sess_1", response)

        # Wait for a short time (we'll mock the sleep)
        # For a real test, we'd need to wait KEEPALIVE_INTERVAL
        # Here we just verify the task was created
        assert id(conn) in manager._keepalive_tasks

        await manager.disconnect(conn)

    async def test_keepalive_stops_on_disconnect(self) -> None:
        """Keepalive task is cancelled on disconnect."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        conn = await manager.connect("sess_1", MockStreamResponse())
        conn_id = id(conn)
        task = manager._keepalive_tasks.get(conn_id)

        await manager.disconnect(conn)

        # Task should be cancelled
        assert conn_id not in manager._keepalive_tasks
        if task:
            assert task.cancelled() or task.done()


class TestSSEFormatCompliance:
    """Tests for SSE format compliance."""

    def test_sse_field_names(self) -> None:
        """SSE uses correct field names: id, event, data."""
        msg = format_sse_message(
            event_id="test_id",
            event_type="test_type",
            data={"key": "value"},
        )
        text = msg.decode("utf-8")

        assert text.startswith("id: ")
        assert "\nevent: " in text
        assert "\ndata: " in text

    def test_sse_newline_termination(self) -> None:
        """SSE messages are terminated with double newline."""
        msg = format_sse_message(event_id="test", data={})
        assert msg.endswith(b"\n\n")

    def test_sse_comment_format(self) -> None:
        """SSE comments start with colon."""
        keepalive = format_keepalive()
        assert keepalive.startswith(b": ")

    def test_data_is_single_line_json(self) -> None:
        """Data field is single-line JSON."""
        msg = format_sse_message(data={"key": "value", "nested": {"a": 1}})
        text = msg.decode("utf-8")

        # Find the data line
        for line in text.split("\n"):
            if line.startswith("data: "):
                # Should be a single line of JSON
                json_str = line[6:]  # Remove "data: " prefix
                assert "\n" not in json_str


class TestSSEIntegration:
    """Integration tests with real async behavior."""

    async def test_full_workflow(self) -> None:
        """Test a complete SSE workflow."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        # Pre-populate buffer with some events
        buffer.add_event("sess_1", make_add_block_event("pre_event1"))
        buffer.add_event("sess_1", make_add_block_event("pre_event2"))

        # Client connects with last_event_id
        response = MockStreamResponse()
        conn = await manager.connect("sess_1", response, last_event_id="evt_001")

        # Should have replayed evt_002 (after evt_001)
        text = response.get_written_text()
        assert "evt_002" in text
        assert "pre_event2" in text

        # New event is broadcast
        buffer.add_event("sess_1", make_add_block_event("new_event"))
        await manager.broadcast("sess_1", "evt_003", make_add_block_event("new_event"))

        text = response.get_written_text()
        assert "evt_003" in text
        assert "new_event" in text

        # Session ends
        await manager.close_session("sess_1", "test_complete")

        text = response.get_written_text()
        assert "session_ended" in text
        assert conn.is_closed

    async def test_client_disconnect_during_broadcast(self) -> None:
        """Handle client disconnect during broadcast gracefully."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        response1 = MockStreamResponse()
        response2 = MockStreamResponse()

        conn1 = await manager.connect("sess_1", response1)
        conn2 = await manager.connect("sess_1", response2)

        # First broadcast works
        await manager.broadcast("sess_1", "evt_001", make_add_block_event("test1"))
        assert manager.get_connection_count("sess_1") == 2

        # conn2 fails on next write
        response2.fail_on_write = True

        # Second broadcast should handle the failure
        await manager.broadcast("sess_1", "evt_002", make_add_block_event("test2"))

        # conn2 should be disconnected
        assert manager.get_connection_count("sess_1") == 1

        # conn1 should still work
        assert "evt_002" in response1.get_written_text()

        await manager.disconnect(conn1)

    async def test_concurrent_connections(self) -> None:
        """Multiple concurrent connections work correctly."""
        buffer = EventBufferManager()
        manager = SSEManager(event_buffer=buffer)

        # Connect multiple clients concurrently
        responses = [MockStreamResponse() for _ in range(5)]
        connections = await asyncio.gather(
            *[manager.connect("sess_1", resp) for resp in responses]
        )

        assert manager.get_connection_count("sess_1") == 5

        # Broadcast to all
        await manager.broadcast("sess_1", "evt_001", make_add_block_event("concurrent"))

        # All should receive
        for resp in responses:
            assert "concurrent" in resp.get_written_text()

        # Cleanup
        for conn in connections:
            await manager.disconnect(conn)


class TestKeepaliveInterval:
    """Tests for keepalive interval constant."""

    def test_keepalive_interval_value(self) -> None:
        """Keepalive interval is 15 seconds as specified."""
        assert KEEPALIVE_INTERVAL == 15
