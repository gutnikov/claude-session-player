"""End-to-end tests for the Session Watcher Service.

These tests verify the complete flow from file changes through to SSE events,
including reconnection scenarios, file deletion handling, service restart,
and concurrent session management.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from claude_session_player.events import ClearAll, ProcessingContext
from claude_session_player.watcher.config import ConfigManager
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.state import SessionState

from datetime import datetime, timezone


# --- Mock SSE Response ---


@dataclass
class MockStreamResponse:
    """Mock streaming response for SSE testing."""

    written: list[bytes] = field(default_factory=list)
    prepared: bool = False
    closed: bool = False

    async def prepare(self, request: object) -> None:
        """Prepare the response."""
        self.prepared = True

    async def write(self, data: bytes) -> None:
        """Write data to response."""
        if self.closed:
            raise OSError("Connection closed")
        self.written.append(data)

    async def write_eof(self) -> None:
        """Signal end of stream."""
        self.closed = True

    def get_events(self) -> list[dict]:
        """Parse SSE events from written data."""
        events = []
        text = b"".join(self.written).decode("utf-8")

        # Split by double newlines (SSE message separator)
        messages = text.split("\n\n")

        for msg in messages:
            if not msg.strip():
                continue
            if msg.startswith(":"):
                # Keep-alive comment
                continue

            event: dict = {}
            for line in msg.strip().split("\n"):
                if line.startswith("id:"):
                    event["id"] = line[3:].strip()
                elif line.startswith("event:"):
                    event["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    event["data"] = json.loads(line[5:].strip())

            if event:
                events.append(event)

        return events


# --- Fixtures ---


@pytest.fixture
def temp_config_path(tmp_path: Path) -> Path:
    """Create a temporary config file path."""
    return tmp_path / "config.yaml"


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def session_file(tmp_path: Path) -> Path:
    """Create a temporary session file."""
    session_path = tmp_path / "session.jsonl"
    session_path.write_text("")
    return session_path


@pytest.fixture
async def watcher_service(
    temp_config_path: Path,
    temp_state_dir: Path,
) -> WatcherService:
    """Create and start a WatcherService instance for testing."""
    service = WatcherService(
        config_path=temp_config_path,
        state_dir=temp_state_dir,
        host="127.0.0.1",
        port=0,  # Let OS assign port
    )
    return service


# --- E2E Tests: Start → Watch → Append → SSE Events ---


class TestWatchAndReceiveEvents:
    """E2E tests for watching files and receiving SSE events."""

    async def test_watch_append_receive_sse_events(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test complete flow: start → watch → append → receive SSE events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("e2e-test", session_file)

            # Connect SSE client
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("e2e-test", response)

            # Append a user message line to the file
            user_line = {"type": "user", "message": {"content": "Hello"}}

            # Simulate the file change being processed
            await watcher_service._on_file_change("e2e-test", [user_line])

            # Parse received SSE events
            events = response.get_events()

            # Should have received an add_block event
            assert len(events) >= 1
            assert events[0]["event"] == "add_block"
            assert events[0]["data"]["type"] == "user"

        finally:
            await watcher_service.stop()

    async def test_watch_multiple_lines_multiple_events(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that multiple lines produce multiple events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("multi-line-test", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("multi-line-test", response)

            # Simulate multiple lines
            lines = [
                {"type": "user", "message": {"content": "First message"}},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "Response"}]}},
            ]
            await watcher_service._on_file_change("multi-line-test", lines)

            events = response.get_events()

            # Should have at least 2 add_block events
            add_events = [e for e in events if e.get("event") == "add_block"]
            assert len(add_events) >= 2

        finally:
            await watcher_service.stop()

    async def test_tool_use_and_result_flow(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test tool call followed by tool result produces add then update events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("tool-flow-test", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("tool-flow-test", response)

            # Tool use
            tool_use_line = {
                "type": "assistant",
                "message": {
                    "content": [{
                        "type": "tool_use",
                        "id": "tu_123",
                        "name": "Read",
                        "input": {"file_path": "/test.py"}
                    }]
                }
            }
            await watcher_service._on_file_change("tool-flow-test", [tool_use_line])

            # Tool result
            tool_result_line = {
                "type": "user",
                "message": {
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": "tu_123",
                        "content": "file contents here"
                    }]
                }
            }
            await watcher_service._on_file_change("tool-flow-test", [tool_result_line])

            events = response.get_events()

            # Should have add_block for tool call, then update_block for result
            event_types = [e.get("event") for e in events]
            assert "add_block" in event_types
            assert "update_block" in event_types

        finally:
            await watcher_service.stop()


# --- E2E Tests: SSE Reconnect with Last-Event-ID ---


class TestSSEReconnectReplay:
    """E2E tests for SSE reconnection and event replay."""

    async def test_reconnect_receives_missed_events(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that reconnecting with Last-Event-ID replays missed events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("reconnect-test", session_file)

            # First connection - receive some events
            response1 = MockStreamResponse()
            await watcher_service.sse_manager.connect("reconnect-test", response1)

            # Add some events
            lines = [
                {"type": "user", "message": {"content": "First"}},
                {"type": "user", "message": {"content": "Second"}},
            ]
            await watcher_service._on_file_change("reconnect-test", lines)

            events1 = response1.get_events()
            assert len(events1) >= 2

            # Get the first event ID
            first_event_id = events1[0]["id"]

            # Disconnect
            await watcher_service.sse_manager.disconnect(
                watcher_service.sse_manager._connections["reconnect-test"][0]
            )

            # Add more events while disconnected
            await watcher_service._on_file_change(
                "reconnect-test",
                [{"type": "user", "message": {"content": "Third"}}]
            )

            # Reconnect with Last-Event-ID pointing to first event
            response2 = MockStreamResponse()
            await watcher_service.sse_manager.connect(
                "reconnect-test", response2, last_event_id=first_event_id
            )

            events2 = response2.get_events()

            # Should have replayed events after the first one
            assert len(events2) >= 2

        finally:
            await watcher_service.stop()

    async def test_reconnect_unknown_id_replays_all_buffered(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that unknown Last-Event-ID replays all buffered events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("unknown-id-test", session_file)

            # Add some events
            lines = [
                {"type": "user", "message": {"content": "First"}},
                {"type": "user", "message": {"content": "Second"}},
            ]
            await watcher_service._on_file_change("unknown-id-test", lines)

            # Connect with unknown Last-Event-ID
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect(
                "unknown-id-test", response, last_event_id="evt_nonexistent"
            )

            events = response.get_events()

            # Should have received all buffered events
            assert len(events) >= 2

        finally:
            await watcher_service.stop()

    async def test_reconnect_no_id_replays_all_buffered(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that reconnecting without Last-Event-ID replays all buffered."""
        try:
            await watcher_service.start()
            await watcher_service.watch("no-id-test", session_file)

            # Add some events
            await watcher_service._on_file_change(
                "no-id-test",
                [{"type": "user", "message": {"content": "Hello"}}]
            )

            # New connection without Last-Event-ID
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("no-id-test", response)

            events = response.get_events()

            # Should have received buffered events
            assert len(events) >= 1

        finally:
            await watcher_service.stop()


# --- E2E Tests: File Deletion ---


class TestFileDeletedSessionEnded:
    """E2E tests for file deletion handling."""

    async def test_file_deleted_sends_session_ended(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that file deletion sends session_ended event."""
        try:
            await watcher_service.start()
            await watcher_service.watch("delete-e2e", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("delete-e2e", response)

            # Simulate file deletion callback
            await watcher_service._on_file_deleted("delete-e2e")

            events = response.get_events()

            # Should have received session_ended event
            session_ended_events = [e for e in events if e.get("event") == "session_ended"]
            assert len(session_ended_events) == 1
            assert session_ended_events[0]["data"]["reason"] == "file_deleted"

        finally:
            if watcher_service.is_running:
                await watcher_service.stop()

    async def test_file_deleted_cleans_up_session(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that file deletion cleans up all session resources."""
        try:
            await watcher_service.start()
            await watcher_service.watch("cleanup-e2e", session_file)

            # Verify session exists
            assert watcher_service.config_manager.get("cleanup-e2e") is not None

            # Trigger state save
            await watcher_service._on_file_change(
                "cleanup-e2e",
                [{"type": "user", "message": {"content": "test"}}]
            )

            # Delete
            await watcher_service._on_file_deleted("cleanup-e2e")

            # Verify cleanup
            assert watcher_service.config_manager.get("cleanup-e2e") is None
            assert not watcher_service.state_manager.exists("cleanup-e2e")

        finally:
            if watcher_service.is_running:
                await watcher_service.stop()


# --- E2E Tests: Service Restart ---


class TestServiceRestartResumption:
    """E2E tests for service restart and state resumption."""

    async def test_service_restart_resumes_from_saved_position(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test that restarting service resumes from saved file position."""
        session_file = tmp_path / "restart-session.jsonl"
        session_file.write_text("")

        # First service instance
        service1 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        await service1.start()
        await service1.watch("restart-e2e", session_file)

        # Process some lines
        lines = [
            {"type": "user", "message": {"content": "Line 1"}},
            {"type": "user", "message": {"content": "Line 2"}},
        ]
        await service1._on_file_change("restart-e2e", lines)

        # Get state before stop
        state_before = service1.state_manager.load("restart-e2e")
        assert state_before is not None
        line_count_before = state_before.line_number

        await service1.stop()

        # Second service instance (simulating restart)
        service2 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        await service2.start()

        # Session should be loaded
        assert "restart-e2e" in service2.file_watcher.watched_sessions

        # State should be preserved
        state_after = service2.state_manager.load("restart-e2e")
        assert state_after is not None
        assert state_after.line_number == line_count_before

        await service2.stop()

    async def test_service_restart_preserves_tool_mappings(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test that tool_use_id mappings are preserved across restart."""
        session_file = tmp_path / "tool-map-session.jsonl"
        session_file.write_text("")

        service1 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        await service1.start()
        await service1.watch("tool-map-e2e", session_file)

        # Process tool_use
        tool_use_line = {
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": "persist_tu_001",
                    "name": "Bash",
                    "input": {"command": "ls"}
                }]
            }
        }
        await service1._on_file_change("tool-map-e2e", [tool_use_line])

        # Verify context has the mapping
        state = service1.state_manager.load("tool-map-e2e")
        assert state is not None
        assert "persist_tu_001" in state.processing_context.tool_use_id_to_block_id

        await service1.stop()

        # Restart
        service2 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        await service2.start()

        # State should preserve the mapping
        state2 = service2.state_manager.load("tool-map-e2e")
        assert state2 is not None
        assert "persist_tu_001" in state2.processing_context.tool_use_id_to_block_id

        await service2.stop()


# --- E2E Tests: Multiple Concurrent Sessions ---


class TestMultipleConcurrentSessions:
    """E2E tests for multiple sessions watched concurrently."""

    async def test_multiple_sessions_independent_events(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test that multiple sessions receive their own events independently."""
        file1 = tmp_path / "session1.jsonl"
        file2 = tmp_path / "session2.jsonl"
        file1.write_text("")
        file2.write_text("")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        try:
            await service.start()
            await service.watch("multi-1", file1)
            await service.watch("multi-2", file2)

            # Connect SSE clients for both
            response1 = MockStreamResponse()
            response2 = MockStreamResponse()
            await service.sse_manager.connect("multi-1", response1)
            await service.sse_manager.connect("multi-2", response2)

            # Send event to session 1 only
            await service._on_file_change(
                "multi-1",
                [{"type": "user", "message": {"content": "Session 1"}}]
            )

            events1 = response1.get_events()
            events2 = response2.get_events()

            # Session 1 should have the event
            assert len(events1) >= 1

            # Session 2 should not have any new events (may have replay)
            session2_user_events = [
                e for e in events2
                if e.get("event") == "add_block" and e.get("data", {}).get("type") == "user"
            ]
            assert len(session2_user_events) == 0

        finally:
            await service.stop()

    async def test_unwatch_one_session_others_continue(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test that unwatching one session doesn't affect others."""
        file1 = tmp_path / "persist1.jsonl"
        file2 = tmp_path / "persist2.jsonl"
        file1.write_text("")
        file2.write_text("")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        try:
            await service.start()
            await service.watch("persist-1", file1)
            await service.watch("persist-2", file2)

            # Unwatch session 1
            await service.unwatch("persist-1")

            # Session 2 should still work
            assert "persist-2" in service.file_watcher.watched_sessions
            assert service.config_manager.get("persist-2") is not None

            # Can still receive events for session 2
            response = MockStreamResponse()
            await service.sse_manager.connect("persist-2", response)

            await service._on_file_change(
                "persist-2",
                [{"type": "user", "message": {"content": "Still working"}}]
            )

            events = response.get_events()
            assert len(events) >= 1

        finally:
            await service.stop()

    async def test_multiple_clients_same_session(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that multiple SSE clients receive the same events."""
        try:
            await watcher_service.start()
            await watcher_service.watch("multi-client", session_file)

            # Connect two clients
            response1 = MockStreamResponse()
            response2 = MockStreamResponse()
            await watcher_service.sse_manager.connect("multi-client", response1)
            await watcher_service.sse_manager.connect("multi-client", response2)

            # Send event
            await watcher_service._on_file_change(
                "multi-client",
                [{"type": "user", "message": {"content": "Broadcast"}}]
            )

            events1 = response1.get_events()
            events2 = response2.get_events()

            # Both should receive the event
            assert len(events1) >= 1
            assert len(events2) >= 1
            assert events1[-1]["event"] == events2[-1]["event"]

        finally:
            await watcher_service.stop()


# --- E2E Tests: Context Compaction (ClearAll) ---


class TestContextCompactionClearAll:
    """E2E tests for context compaction flowing through."""

    async def test_compact_boundary_produces_clear_all_event(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that compact_boundary produces clear_all SSE event."""
        try:
            await watcher_service.start()
            await watcher_service.watch("compact-e2e", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("compact-e2e", response)

            # Add some content first
            await watcher_service._on_file_change(
                "compact-e2e",
                [{"type": "user", "message": {"content": "Before compaction"}}]
            )

            # Trigger compaction
            compact_line = {"type": "system", "subtype": "compact_boundary"}
            await watcher_service._on_file_change("compact-e2e", [compact_line])

            events = response.get_events()

            # Should have a clear_all event
            clear_events = [e for e in events if e.get("event") == "clear_all"]
            assert len(clear_events) == 1

        finally:
            await watcher_service.stop()

    async def test_compact_boundary_resets_context(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that compact_boundary resets the processing context."""
        try:
            await watcher_service.start()
            await watcher_service.watch("context-reset", session_file)

            # Add tool_use to populate context
            tool_use_line = {
                "type": "assistant",
                "message": {
                    "content": [{
                        "type": "tool_use",
                        "id": "clear_tu_001",
                        "name": "Read",
                        "input": {"file_path": "/test.py"}
                    }]
                }
            }
            await watcher_service._on_file_change("context-reset", [tool_use_line])

            # Verify context has mapping
            state1 = watcher_service.state_manager.load("context-reset")
            assert state1 is not None
            assert "clear_tu_001" in state1.processing_context.tool_use_id_to_block_id

            # Compact
            compact_line = {"type": "system", "subtype": "compact_boundary"}
            await watcher_service._on_file_change("context-reset", [compact_line])

            # Context should be cleared
            state2 = watcher_service.state_manager.load("context-reset")
            assert state2 is not None
            assert len(state2.processing_context.tool_use_id_to_block_id) == 0

        finally:
            await watcher_service.stop()

    async def test_post_compaction_events_still_work(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that events after compaction are still processed correctly."""
        try:
            await watcher_service.start()
            await watcher_service.watch("post-compact", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("post-compact", response)

            # Compact
            compact_line = {"type": "system", "subtype": "compact_boundary"}
            await watcher_service._on_file_change("post-compact", [compact_line])

            # Add content after compaction
            await watcher_service._on_file_change(
                "post-compact",
                [{"type": "user", "message": {"content": "After compaction"}}]
            )

            events = response.get_events()

            # Should have clear_all followed by add_block
            event_types = [e.get("event") for e in events]
            assert "clear_all" in event_types
            assert "add_block" in event_types

            # add_block should come after clear_all
            clear_idx = event_types.index("clear_all")
            add_idx = event_types.index("add_block")
            assert add_idx > clear_idx

        finally:
            await watcher_service.stop()


# --- E2E Tests: Progress Updates ---


class TestProgressUpdates:
    """E2E tests for progress message handling."""

    async def test_bash_progress_updates_tool_call(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that bash_progress updates the corresponding tool call."""
        try:
            await watcher_service.start()
            await watcher_service.watch("progress-e2e", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("progress-e2e", response)

            # Tool use
            tool_use_line = {
                "type": "assistant",
                "message": {
                    "content": [{
                        "type": "tool_use",
                        "id": "prog_tu_001",
                        "name": "Bash",
                        "input": {"command": "npm install"}
                    }]
                }
            }
            await watcher_service._on_file_change("progress-e2e", [tool_use_line])

            # Progress update
            progress_line = {
                "type": "progress",
                "parentToolUseID": "prog_tu_001",
                "data": {
                    "type": "bash_progress",
                    "progress": "Installing packages..."
                }
            }
            await watcher_service._on_file_change("progress-e2e", [progress_line])

            events = response.get_events()

            # Should have add_block then update_block
            event_types = [e.get("event") for e in events]
            assert "add_block" in event_types
            assert "update_block" in event_types

        finally:
            await watcher_service.stop()


# --- E2E Tests: Event Buffer Limits ---


class TestEventBufferLimits:
    """E2E tests for event buffer size limits."""

    async def test_buffer_evicts_old_events(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that buffer evicts old events when full."""
        try:
            await watcher_service.start()
            await watcher_service.watch("eviction-e2e", session_file)

            # Add more than 20 events (buffer default size)
            for i in range(25):
                await watcher_service._on_file_change(
                    "eviction-e2e",
                    [{"type": "user", "message": {"content": f"Message {i}"}}]
                )

            # New client should only get last ~20 events
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("eviction-e2e", response)

            events = response.get_events()

            # Should have around 20 events (buffer size)
            assert len(events) <= 20

        finally:
            await watcher_service.stop()


# --- E2E Tests: Error Recovery ---


class TestErrorRecovery:
    """E2E tests for error recovery scenarios."""

    async def test_malformed_line_skipped_gracefully(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that malformed lines are skipped without breaking the stream."""
        try:
            await watcher_service.start()
            await watcher_service.watch("malformed-e2e", session_file)

            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("malformed-e2e", response)

            # Mix of valid and invalid lines
            lines = [
                {"type": "user", "message": {"content": "Valid 1"}},
                {},  # Empty/malformed
                {"type": "user", "message": {"content": "Valid 2"}},
            ]
            await watcher_service._on_file_change("malformed-e2e", lines)

            events = response.get_events()

            # Should have events for valid lines
            add_events = [e for e in events if e.get("event") == "add_block"]
            assert len(add_events) >= 2

        finally:
            await watcher_service.stop()

    async def test_client_disconnect_handled_gracefully(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Test that client disconnect doesn't break event processing."""
        try:
            await watcher_service.start()
            await watcher_service.watch("disconnect-e2e", session_file)

            # Connect and disconnect
            response1 = MockStreamResponse()
            conn = await watcher_service.sse_manager.connect("disconnect-e2e", response1)
            await watcher_service.sse_manager.disconnect(conn)

            # Processing should still work
            await watcher_service._on_file_change(
                "disconnect-e2e",
                [{"type": "user", "message": {"content": "After disconnect"}}]
            )

            # New client should receive buffered event
            response2 = MockStreamResponse()
            await watcher_service.sse_manager.connect("disconnect-e2e", response2)

            events = response2.get_events()
            assert len(events) >= 1

        finally:
            await watcher_service.stop()
