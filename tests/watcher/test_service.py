"""Tests for the WatcherService class."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    ProcessingContext,
    UpdateBlock,
)
from claude_session_player.watcher.config import ConfigManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.state import SessionState, StateManager


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
    """Create a temporary session file with content."""
    session_path = tmp_path / "session.jsonl"
    session_path.write_text('{"type":"user","message":{"content":"hello"}}\n')
    return session_path


@pytest.fixture
def empty_session_file(tmp_path: Path) -> Path:
    """Create an empty temporary session file."""
    session_path = tmp_path / "empty_session.jsonl"
    session_path.write_text("")
    return session_path


@pytest.fixture
def watcher_service(
    temp_config_path: Path,
    temp_state_dir: Path,
) -> WatcherService:
    """Create a WatcherService instance for testing."""
    return WatcherService(
        config_path=temp_config_path,
        state_dir=temp_state_dir,
        host="127.0.0.1",
        port=8888,  # Use non-standard port for tests
    )


# --- Tests for WatcherService creation ---


class TestWatcherServiceCreation:
    """Tests for WatcherService initialization."""

    def test_creates_with_paths(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherService can be created with config and state paths."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.config_path == temp_config_path
        assert service.state_dir == temp_state_dir

    def test_creates_default_components(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherService creates default components if not injected."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.config_manager is not None
        assert service.state_manager is not None
        assert service.file_watcher is not None
        assert service.event_buffer is not None
        assert service.sse_manager is not None
        assert service.api is not None

    def test_accepts_injected_components(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherService accepts injected components for testing."""
        config_manager = ConfigManager(temp_config_path)
        state_manager = StateManager(temp_state_dir)
        event_buffer = EventBufferManager()
        sse_manager = SSEManager(event_buffer=event_buffer)

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            config_manager=config_manager,
            state_manager=state_manager,
            event_buffer=event_buffer,
            sse_manager=sse_manager,
        )

        assert service.config_manager is config_manager
        assert service.state_manager is state_manager
        assert service.event_buffer is event_buffer
        assert service.sse_manager is sse_manager

    def test_default_host_and_port(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherService has default host and port."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.host == "127.0.0.1"
        assert service.port == 8080

    def test_custom_host_and_port(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherService accepts custom host and port."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            host="0.0.0.0",
            port=9090,
        )

        assert service.host == "0.0.0.0"
        assert service.port == 9090

    def test_is_running_initially_false(self, watcher_service: WatcherService) -> None:
        """Service is not running initially."""
        assert watcher_service.is_running is False


# --- Tests for startup ---


class TestWatcherServiceStartup:
    """Tests for WatcherService startup."""

    async def test_start_sets_running(self, watcher_service: WatcherService) -> None:
        """Starting the service sets is_running to True."""
        try:
            await watcher_service.start()
            assert watcher_service.is_running is True
        finally:
            await watcher_service.stop()

    async def test_start_twice_is_noop(self, watcher_service: WatcherService) -> None:
        """Starting an already running service is a no-op."""
        try:
            await watcher_service.start()
            await watcher_service.start()  # Should not raise
            assert watcher_service.is_running is True
        finally:
            await watcher_service.stop()

    async def test_start_loads_existing_config(
        self, temp_config_path: Path, temp_state_dir: Path, session_file: Path
    ) -> None:
        """Startup loads sessions from existing config."""
        # Pre-populate config
        config_manager = ConfigManager(temp_config_path)
        config_manager.add("existing-session", session_file)

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8889,
        )

        try:
            await service.start()

            # Session should be in file watcher
            assert "existing-session" in service.file_watcher.watched_sessions
        finally:
            await service.stop()

    async def test_start_resumes_from_saved_state(
        self, temp_config_path: Path, temp_state_dir: Path, session_file: Path
    ) -> None:
        """Startup resumes sessions from saved state."""
        # Pre-populate config and state
        config_manager = ConfigManager(temp_config_path)
        config_manager.add("stateful-session", session_file)

        state_manager = StateManager(temp_state_dir)
        state = SessionState(
            file_position=25,
            line_number=1,
            processing_context=ProcessingContext(),
            last_modified=datetime.now(timezone.utc),
        )
        state_manager.save("stateful-session", state)

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8890,
        )

        try:
            await service.start()

            # File watcher should start at saved position
            position = service.file_watcher.get_position("stateful-session")
            assert position == 25
        finally:
            await service.stop()

    async def test_start_removes_missing_files(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Startup removes sessions whose files no longer exist."""
        # Create config pointing to nonexistent file
        config_manager = ConfigManager(temp_config_path)
        # Manually add a session with nonexistent path
        from claude_session_player.watcher.config import SessionConfig

        sessions = [SessionConfig(session_id="missing-file", path=Path("/nonexistent/path.jsonl"))]
        config_manager.save(sessions)

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8891,
        )

        try:
            await service.start()

            # Session should be removed from config
            assert config_manager.get("missing-file") is None
        finally:
            await service.stop()


# --- Tests for shutdown ---


class TestWatcherServiceShutdown:
    """Tests for WatcherService shutdown."""

    async def test_stop_clears_running(self, watcher_service: WatcherService) -> None:
        """Stopping the service clears is_running."""
        await watcher_service.start()
        assert watcher_service.is_running is True

        await watcher_service.stop()
        assert watcher_service.is_running is False

    async def test_stop_twice_is_noop(self, watcher_service: WatcherService) -> None:
        """Stopping an already stopped service is a no-op."""
        await watcher_service.start()
        await watcher_service.stop()
        await watcher_service.stop()  # Should not raise
        assert watcher_service.is_running is False

    async def test_shutdown_saves_state(
        self, temp_config_path: Path, temp_state_dir: Path, session_file: Path
    ) -> None:
        """Shutdown saves state for all sessions."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8892,
        )

        try:
            await service.start()

            # Watch a session
            await service.watch("save-test", session_file)

            # Stop (should save state)
            await service.stop()

            # Verify state was saved
            state = service.state_manager.load("save-test")
            assert state is not None
            assert state.file_position >= 0
        finally:
            if service.is_running:
                await service.stop()

    async def test_shutdown_closes_sse_connections(
        self, temp_config_path: Path, temp_state_dir: Path, session_file: Path
    ) -> None:
        """Shutdown sends session_ended to SSE subscribers."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8893,
        )

        try:
            await service.start()
            await service.watch("sse-test", session_file)

            # Simulate SSE connection
            response = MockStreamResponse()
            await service.sse_manager.connect("sse-test", response)

            # Stop should send session_ended
            await service.stop()

            # Check that session_ended was sent
            written = b"".join(response.written).decode("utf-8")
            assert "session_ended" in written
            assert "shutdown" in written
        finally:
            if service.is_running:
                await service.stop()


# --- Tests for watch() method ---


class TestWatcherServiceWatch:
    """Tests for WatcherService.watch() method."""

    async def test_watch_adds_to_config(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """watch() adds session to config."""
        try:
            await watcher_service.start()
            await watcher_service.watch("watch-test", session_file)

            config = watcher_service.config_manager.get("watch-test")
            assert config is not None
            assert config.session_id == "watch-test"
        finally:
            await watcher_service.stop()

    async def test_watch_adds_to_file_watcher(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """watch() adds file to file watcher."""
        try:
            await watcher_service.start()
            await watcher_service.watch("fw-test", session_file)

            assert "fw-test" in watcher_service.file_watcher.watched_sessions
        finally:
            await watcher_service.stop()

    async def test_watch_validates_absolute_path(
        self, watcher_service: WatcherService
    ) -> None:
        """watch() rejects relative paths."""
        try:
            await watcher_service.start()

            with pytest.raises(ValueError, match="absolute"):
                await watcher_service.watch("rel-test", Path("relative/path.jsonl"))
        finally:
            await watcher_service.stop()

    async def test_watch_validates_file_exists(
        self, watcher_service: WatcherService
    ) -> None:
        """watch() rejects nonexistent files."""
        try:
            await watcher_service.start()

            with pytest.raises(FileNotFoundError):
                await watcher_service.watch("missing-test", Path("/nonexistent/file.jsonl"))
        finally:
            await watcher_service.stop()

    async def test_watch_rejects_duplicate(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """watch() rejects duplicate session IDs."""
        try:
            await watcher_service.start()
            await watcher_service.watch("dup-test", session_file)

            with pytest.raises(ValueError, match="already exists"):
                await watcher_service.watch("dup-test", session_file)
        finally:
            await watcher_service.stop()


# --- Tests for unwatch() method ---


class TestWatcherServiceUnwatch:
    """Tests for WatcherService.unwatch() method."""

    async def test_unwatch_removes_from_config(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """unwatch() removes session from config."""
        try:
            await watcher_service.start()
            await watcher_service.watch("unwatch-test", session_file)
            await watcher_service.unwatch("unwatch-test")

            assert watcher_service.config_manager.get("unwatch-test") is None
        finally:
            await watcher_service.stop()

    async def test_unwatch_removes_from_file_watcher(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """unwatch() removes file from file watcher."""
        try:
            await watcher_service.start()
            await watcher_service.watch("fw-unwatch", session_file)
            await watcher_service.unwatch("fw-unwatch")

            assert "fw-unwatch" not in watcher_service.file_watcher.watched_sessions
        finally:
            await watcher_service.stop()

    async def test_unwatch_removes_event_buffer(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """unwatch() removes event buffer."""
        try:
            await watcher_service.start()
            await watcher_service.watch("buffer-unwatch", session_file)

            # Add an event
            event = AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="test"),
                )
            )
            watcher_service.event_buffer.add_event("buffer-unwatch", event)

            await watcher_service.unwatch("buffer-unwatch")

            # New buffer should be empty
            buffer = watcher_service.event_buffer.get_buffer("buffer-unwatch")
            assert len(buffer) == 0
        finally:
            await watcher_service.stop()

    async def test_unwatch_deletes_state(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """unwatch() deletes state file."""
        try:
            await watcher_service.start()
            await watcher_service.watch("state-unwatch", session_file)

            # Trigger state save by processing a file change
            await watcher_service._on_file_change("state-unwatch", [{"type": "user"}])

            assert watcher_service.state_manager.exists("state-unwatch")

            await watcher_service.unwatch("state-unwatch")

            assert not watcher_service.state_manager.exists("state-unwatch")
        finally:
            await watcher_service.stop()

    async def test_unwatch_sends_session_ended(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """unwatch() sends session_ended to SSE subscribers."""
        try:
            await watcher_service.start()
            await watcher_service.watch("sse-unwatch", session_file)

            # Connect SSE client
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("sse-unwatch", response)

            await watcher_service.unwatch("sse-unwatch")

            written = b"".join(response.written).decode("utf-8")
            assert "session_ended" in written
            assert "unwatched" in written
        finally:
            await watcher_service.stop()

    async def test_unwatch_raises_for_unknown(
        self, watcher_service: WatcherService
    ) -> None:
        """unwatch() raises KeyError for unknown session."""
        try:
            await watcher_service.start()

            with pytest.raises(KeyError, match="not found"):
                await watcher_service.unwatch("nonexistent")
        finally:
            await watcher_service.stop()


# --- Tests for file change handling ---


class TestWatcherServiceFileChange:
    """Tests for file change event handling."""

    async def test_file_change_triggers_event_flow(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File changes trigger the event processing flow."""
        try:
            await watcher_service.start()
            await watcher_service.watch("change-test", session_file)

            # Simulate file change with a user message
            lines = [{"type": "user", "message": {"content": "hello"}}]
            await watcher_service._on_file_change("change-test", lines)

            # Check that events were added to buffer
            events = watcher_service.event_buffer.get_events_since("change-test", None)
            assert len(events) > 0
        finally:
            await watcher_service.stop()

    async def test_file_change_saves_state(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File changes save updated state."""
        try:
            await watcher_service.start()
            await watcher_service.watch("state-change", session_file)

            # Simulate file change
            lines = [{"type": "user", "message": {"content": "hello"}}]
            await watcher_service._on_file_change("state-change", lines)

            # Check state was saved
            state = watcher_service.state_manager.load("state-change")
            assert state is not None
            assert state.line_number > 0
        finally:
            await watcher_service.stop()

    async def test_file_change_broadcasts_events(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File changes broadcast events to SSE subscribers."""
        try:
            await watcher_service.start()
            await watcher_service.watch("broadcast-test", session_file)

            # Connect SSE client
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("broadcast-test", response)

            # Simulate file change with assistant message
            lines = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}]
            await watcher_service._on_file_change("broadcast-test", lines)

            # Check event was broadcast
            written = b"".join(response.written).decode("utf-8")
            assert "add_block" in written
        finally:
            await watcher_service.stop()

    async def test_empty_lines_ignored(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """Empty lines list is ignored."""
        try:
            await watcher_service.start()
            await watcher_service.watch("empty-test", session_file)

            # Simulate empty file change
            await watcher_service._on_file_change("empty-test", [])

            # No events should be added
            events = watcher_service.event_buffer.get_events_since("empty-test", None)
            assert len(events) == 0
        finally:
            await watcher_service.stop()


# --- Tests for file deletion handling ---


class TestWatcherServiceFileDeletion:
    """Tests for file deletion handling."""

    async def test_file_deleted_removes_from_config(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File deletion removes session from config."""
        try:
            await watcher_service.start()
            await watcher_service.watch("delete-config", session_file)

            await watcher_service._on_file_deleted("delete-config")

            assert watcher_service.config_manager.get("delete-config") is None
        finally:
            await watcher_service.stop()

    async def test_file_deleted_sends_session_ended(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File deletion sends session_ended to SSE subscribers."""
        try:
            await watcher_service.start()
            await watcher_service.watch("delete-sse", session_file)

            # Connect SSE client
            response = MockStreamResponse()
            await watcher_service.sse_manager.connect("delete-sse", response)

            await watcher_service._on_file_deleted("delete-sse")

            written = b"".join(response.written).decode("utf-8")
            assert "session_ended" in written
            assert "file_deleted" in written
        finally:
            await watcher_service.stop()

    async def test_file_deleted_removes_buffer(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File deletion removes event buffer."""
        try:
            await watcher_service.start()
            await watcher_service.watch("delete-buffer", session_file)

            # Add an event
            event = AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="test"),
                )
            )
            watcher_service.event_buffer.add_event("delete-buffer", event)

            await watcher_service._on_file_deleted("delete-buffer")

            # New buffer should be empty
            buffer = watcher_service.event_buffer.get_buffer("delete-buffer")
            assert len(buffer) == 0
        finally:
            await watcher_service.stop()

    async def test_file_deleted_removes_state(
        self, watcher_service: WatcherService, session_file: Path
    ) -> None:
        """File deletion removes state file."""
        try:
            await watcher_service.start()
            await watcher_service.watch("delete-state", session_file)

            # Trigger state save
            await watcher_service._on_file_change("delete-state", [{"type": "user"}])
            assert watcher_service.state_manager.exists("delete-state")

            await watcher_service._on_file_deleted("delete-state")

            assert not watcher_service.state_manager.exists("delete-state")
        finally:
            await watcher_service.stop()


# --- Tests for corrupt state handling ---


class TestCorruptStateHandling:
    """Tests for handling corrupt state files."""

    async def test_corrupt_state_uses_fresh_context(
        self, temp_config_path: Path, temp_state_dir: Path, session_file: Path
    ) -> None:
        """Corrupt state file results in fresh context."""
        # Pre-populate config
        config_manager = ConfigManager(temp_config_path)
        config_manager.add("corrupt-session", session_file)

        # Write corrupt state file
        state_file = temp_state_dir / "corrupt-session.json"
        state_file.write_text("not valid json {{{")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8894,
        )

        try:
            await service.start()

            # Session should still be watched (starting from end of file)
            assert "corrupt-session" in service.file_watcher.watched_sessions
        finally:
            await service.stop()


# --- Integration tests ---


class TestWatcherServiceIntegration:
    """Integration tests for full service lifecycle."""

    async def test_full_lifecycle(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Test full service lifecycle: start → watch → unwatch → stop."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user","message":{"content":"hello"}}\n')

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8895,
        )

        # Start
        await service.start()
        assert service.is_running

        # Watch
        await service.watch("lifecycle-test", session_file)
        assert "lifecycle-test" in service.file_watcher.watched_sessions

        # Unwatch
        await service.unwatch("lifecycle-test")
        assert "lifecycle-test" not in service.file_watcher.watched_sessions

        # Stop
        await service.stop()
        assert not service.is_running

    async def test_restart_resumes_state(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Service restart resumes from saved state."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}\n{"type":"user"}\n')

        # First service instance
        service1 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8896,
        )

        await service1.start()
        await service1.watch("restart-test", session_file)

        # Simulate processing some lines
        await service1._on_file_change("restart-test", [{"type": "user"}])

        await service1.stop()

        # Second service instance
        service2 = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8897,
        )

        await service2.start()

        # Session should be loaded from config
        assert "restart-test" in service2.file_watcher.watched_sessions

        # State should be preserved
        state = service2.state_manager.load("restart-test")
        assert state is not None
        assert state.line_number >= 1

        await service2.stop()

    async def test_multiple_sessions(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Service handles multiple sessions correctly."""
        file1 = tmp_path / "session1.jsonl"
        file2 = tmp_path / "session2.jsonl"
        file1.write_text('{"type":"user"}\n')
        file2.write_text('{"type":"user"}\n')

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=8898,
        )

        try:
            await service.start()

            await service.watch("session-1", file1)
            await service.watch("session-2", file2)

            assert len(service.config_manager.list_all()) == 2
            assert "session-1" in service.file_watcher.watched_sessions
            assert "session-2" in service.file_watcher.watched_sessions

            # Unwatch one
            await service.unwatch("session-1")

            assert len(service.config_manager.list_all()) == 1
            assert "session-1" not in service.file_watcher.watched_sessions
            assert "session-2" in service.file_watcher.watched_sessions
        finally:
            await service.stop()


# --- Tests for CLI entry point ---


class TestCLIMain:
    """Tests for CLI module functions."""

    def test_parse_args_defaults(self) -> None:
        """Default arguments are set correctly."""
        from claude_session_player.watcher.__main__ import parse_args

        args = parse_args([])

        assert args.host == "127.0.0.1"
        assert args.port == 8080
        assert args.config == Path("config.yaml")
        assert args.state_dir == Path("state")
        assert args.log_level == "INFO"

    def test_parse_args_custom_values(self) -> None:
        """Custom arguments are parsed correctly."""
        from claude_session_player.watcher.__main__ import parse_args

        args = parse_args([
            "--host", "0.0.0.0",
            "--port", "9090",
            "--config", "/etc/watcher/config.yaml",
            "--state-dir", "/var/lib/watcher/state",
            "--log-level", "DEBUG",
        ])

        assert args.host == "0.0.0.0"
        assert args.port == 9090
        assert args.config == Path("/etc/watcher/config.yaml")
        assert args.state_dir == Path("/var/lib/watcher/state")
        assert args.log_level == "DEBUG"

    def test_setup_logging_runs_without_error(self) -> None:
        """setup_logging runs without error for all log levels."""
        from claude_session_player.watcher.__main__ import setup_logging

        # Test all valid log levels run without error
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            setup_logging(level)  # Should not raise
