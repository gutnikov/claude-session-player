"""Tests for the REST API module."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
)
from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import ConfigManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.state import StateManager


# --- Mock HTTP Request/Response ---


@dataclass
class MockRequest:
    """Mock aiohttp request for testing."""

    match_info: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    _json_data: dict | None = None
    _json_error: bool = False
    transport: Any = None

    async def json(self) -> dict:
        """Return JSON body."""
        if self._json_error:
            raise json.JSONDecodeError("Invalid JSON", "", 0)
        return self._json_data or {}


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

    def get_written_text(self) -> str:
        """Get all written data as string."""
        return b"".join(self.written).decode("utf-8")


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
    session_path.write_text('{"type":"user","message":{"content":"hello"}}\n')
    return session_path


@pytest.fixture
def empty_session_file(tmp_path: Path) -> Path:
    """Create an empty temporary session file."""
    session_path = tmp_path / "empty_session.jsonl"
    session_path.write_text("")
    return session_path


async def dummy_callback(session_id: str, lines: list[dict]) -> None:
    """Dummy callback for FileWatcher."""
    pass


async def dummy_deleted_callback(session_id: str) -> None:
    """Dummy callback for file deletion."""
    pass


@pytest.fixture
def watcher_api(
    temp_config_path: Path,
    temp_state_dir: Path,
) -> WatcherAPI:
    """Create a WatcherAPI instance with all dependencies."""
    config_manager = ConfigManager(temp_config_path)
    state_manager = StateManager(temp_state_dir)
    event_buffer = EventBufferManager()
    file_watcher = FileWatcher(
        on_lines_callback=dummy_callback,
        on_file_deleted_callback=dummy_deleted_callback,
    )
    sse_manager = SSEManager(event_buffer=event_buffer)

    return WatcherAPI(
        config_manager=config_manager,
        state_manager=state_manager,
        file_watcher=file_watcher,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
    )


# --- Tests for POST /watch ---


class TestHandleWatchSuccess:
    """Tests for POST /watch success cases."""

    async def test_watch_success(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """Successful POST /watch returns 201."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 201
        data = json.loads(response.body)
        assert data["session_id"] == "test-session"
        assert data["status"] == "watching"

    async def test_watch_adds_to_config(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /watch adds session to config."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )

        await watcher_api.handle_watch(request)

        config = watcher_api.config_manager.get("test-session")
        assert config is not None
        assert config.session_id == "test-session"
        assert config.path == session_file

    async def test_watch_adds_to_file_watcher(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /watch adds file to file watcher."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )

        await watcher_api.handle_watch(request)

        assert "test-session" in watcher_api.file_watcher.watched_sessions

    async def test_watch_multiple_sessions(
        self, watcher_api: WatcherAPI, tmp_path: Path
    ) -> None:
        """Can watch multiple sessions."""
        # Create two session files
        file1 = tmp_path / "session1.jsonl"
        file2 = tmp_path / "session2.jsonl"
        file1.write_text('{"type":"user"}\n')
        file2.write_text('{"type":"user"}\n')

        request1 = MockRequest(
            _json_data={"session_id": "session-1", "path": str(file1)}
        )
        request2 = MockRequest(
            _json_data={"session_id": "session-2", "path": str(file2)}
        )

        response1 = await watcher_api.handle_watch(request1)
        response2 = await watcher_api.handle_watch(request2)

        assert response1.status == 201
        assert response2.status == 201
        assert len(watcher_api.config_manager.list_all()) == 2


class TestHandleWatchMissingFields:
    """Tests for POST /watch with missing fields."""

    async def test_missing_session_id(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /watch without session_id returns 400."""
        request = MockRequest(
            _json_data={"path": str(session_file)}
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "session_id" in data["error"]

    async def test_missing_path(self, watcher_api: WatcherAPI) -> None:
        """POST /watch without path returns 400."""
        request = MockRequest(
            _json_data={"session_id": "test-session"}
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "path" in data["error"]

    async def test_empty_session_id(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /watch with empty session_id returns 400."""
        request = MockRequest(
            _json_data={"session_id": "", "path": str(session_file)}
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 400

    async def test_invalid_json(self, watcher_api: WatcherAPI) -> None:
        """POST /watch with invalid JSON returns 400."""
        request = MockRequest(_json_error=True)

        response = await watcher_api.handle_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "Invalid JSON" in data["error"]


class TestHandleWatchFileNotFound:
    """Tests for POST /watch with file not found."""

    async def test_file_not_found(self, watcher_api: WatcherAPI) -> None:
        """POST /watch with nonexistent file returns 404."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": "/nonexistent/path/session.jsonl",
            }
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert "not found" in data["error"].lower()


class TestHandleWatchDuplicateSession:
    """Tests for POST /watch with duplicate session."""

    async def test_duplicate_session(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /watch with existing session_id returns 409."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )

        # First watch succeeds
        response1 = await watcher_api.handle_watch(request)
        assert response1.status == 201

        # Second watch with same ID fails
        response2 = await watcher_api.handle_watch(request)
        assert response2.status == 409
        data = json.loads(response2.body)
        assert "already exists" in data["error"].lower()


class TestHandleWatchInvalidPath:
    """Tests for POST /watch with invalid path."""

    async def test_relative_path(self, watcher_api: WatcherAPI) -> None:
        """POST /watch with relative path returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": "relative/path/session.jsonl",
            }
        )

        response = await watcher_api.handle_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "absolute" in data["error"].lower()


# --- Tests for DELETE /unwatch/{session_id} ---


class TestHandleUnwatchSuccess:
    """Tests for DELETE /unwatch success cases."""

    async def test_unwatch_success(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """DELETE /unwatch returns 204 on success."""
        # First watch the session
        watch_request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )
        await watcher_api.handle_watch(watch_request)

        # Then unwatch
        unwatch_request = MockRequest(match_info={"session_id": "test-session"})
        response = await watcher_api.handle_unwatch(unwatch_request)

        assert response.status == 204

    async def test_unwatch_removes_from_config(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """DELETE /unwatch removes session from config."""
        # Watch
        watch_request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )
        await watcher_api.handle_watch(watch_request)
        assert watcher_api.config_manager.get("test-session") is not None

        # Unwatch
        unwatch_request = MockRequest(match_info={"session_id": "test-session"})
        await watcher_api.handle_unwatch(unwatch_request)

        assert watcher_api.config_manager.get("test-session") is None

    async def test_unwatch_removes_from_file_watcher(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """DELETE /unwatch removes file from file watcher."""
        # Watch
        watch_request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )
        await watcher_api.handle_watch(watch_request)
        assert "test-session" in watcher_api.file_watcher.watched_sessions

        # Unwatch
        unwatch_request = MockRequest(match_info={"session_id": "test-session"})
        await watcher_api.handle_unwatch(unwatch_request)

        assert "test-session" not in watcher_api.file_watcher.watched_sessions


class TestHandleUnwatchNotFound:
    """Tests for DELETE /unwatch with not found."""

    async def test_unwatch_not_found(self, watcher_api: WatcherAPI) -> None:
        """DELETE /unwatch for nonexistent session returns 404."""
        request = MockRequest(match_info={"session_id": "nonexistent"})

        response = await watcher_api.handle_unwatch(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert "not found" in data["error"].lower()


# --- Tests for GET /sessions ---


class TestHandleListSessions:
    """Tests for GET /sessions endpoint."""

    async def test_empty_list(self, watcher_api: WatcherAPI) -> None:
        """GET /sessions returns empty list when no sessions."""
        request = MockRequest()

        response = await watcher_api.handle_list_sessions(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["sessions"] == []

    async def test_list_sessions(
        self, watcher_api: WatcherAPI, tmp_path: Path
    ) -> None:
        """GET /sessions returns all watched sessions."""
        # Create and watch two sessions
        file1 = tmp_path / "session1.jsonl"
        file2 = tmp_path / "session2.jsonl"
        file1.write_text('{"type":"user"}\n')
        file2.write_text('{"type":"user"}\n')

        await watcher_api.handle_watch(
            MockRequest(_json_data={"session_id": "session-1", "path": str(file1)})
        )
        await watcher_api.handle_watch(
            MockRequest(_json_data={"session_id": "session-2", "path": str(file2)})
        )

        # List sessions
        request = MockRequest()
        response = await watcher_api.handle_list_sessions(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert len(data["sessions"]) == 2

        session_ids = {s["session_id"] for s in data["sessions"]}
        assert "session-1" in session_ids
        assert "session-2" in session_ids

    async def test_list_sessions_includes_status(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions includes status for each session."""
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        request = MockRequest()
        response = await watcher_api.handle_list_sessions(request)

        data = json.loads(response.body)
        session = data["sessions"][0]
        assert session["status"] == "watching"

    async def test_list_sessions_includes_path(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions includes path for each session."""
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        request = MockRequest()
        response = await watcher_api.handle_list_sessions(request)

        data = json.loads(response.body)
        session = data["sessions"][0]
        assert session["path"] == str(session_file)

    async def test_list_sessions_includes_file_position(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions includes file_position for each session."""
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        request = MockRequest()
        response = await watcher_api.handle_list_sessions(request)

        data = json.loads(response.body)
        session = data["sessions"][0]
        assert "file_position" in session
        assert isinstance(session["file_position"], int)

    async def test_list_sessions_includes_last_event_id(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions includes last_event_id (or null) for each session."""
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        request = MockRequest()
        response = await watcher_api.handle_list_sessions(request)

        data = json.loads(response.body)
        session = data["sessions"][0]
        assert "last_event_id" in session


# --- Tests for GET /health ---


class TestHandleHealth:
    """Tests for GET /health endpoint."""

    async def test_health_returns_status(self, watcher_api: WatcherAPI) -> None:
        """GET /health returns healthy status."""
        request = MockRequest()

        response = await watcher_api.handle_health(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["status"] == "healthy"

    async def test_health_returns_session_count(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """GET /health returns sessions_watched count."""
        # Watch a session
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        request = MockRequest()
        response = await watcher_api.handle_health(request)

        data = json.loads(response.body)
        assert data["sessions_watched"] == 1

    async def test_health_returns_uptime(self, watcher_api: WatcherAPI) -> None:
        """GET /health returns uptime_seconds."""
        request = MockRequest()

        response = await watcher_api.handle_health(request)

        data = json.loads(response.body)
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0

    async def test_health_uptime_increases(self, watcher_api: WatcherAPI) -> None:
        """GET /health uptime increases over time."""
        request = MockRequest()

        response1 = await watcher_api.handle_health(request)
        data1 = json.loads(response1.body)
        uptime1 = data1["uptime_seconds"]

        # Wait a bit
        await asyncio.sleep(0.1)

        response2 = await watcher_api.handle_health(request)
        data2 = json.loads(response2.body)
        uptime2 = data2["uptime_seconds"]

        # Uptime should be same or greater (small sleep might not tick)
        assert uptime2 >= uptime1


# --- Tests for GET /sessions/{session_id}/events ---


class TestHandleSessionEventsNotFound:
    """Tests for GET /sessions/{session_id}/events with not found."""

    async def test_session_not_found(self, watcher_api: WatcherAPI) -> None:
        """GET /sessions/{id}/events for nonexistent session returns 404."""
        request = MockRequest(match_info={"session_id": "nonexistent"})

        response = await watcher_api.handle_session_events(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert "not found" in data["error"].lower()


# --- Tests for WatcherAPI.create_app ---


class TestCreateApp:
    """Tests for WatcherAPI.create_app method."""

    def test_creates_application(self, watcher_api: WatcherAPI) -> None:
        """create_app() returns an aiohttp Application."""
        from aiohttp import web

        app = watcher_api.create_app()

        assert isinstance(app, web.Application)

    def test_registers_routes(self, watcher_api: WatcherAPI) -> None:
        """create_app() registers all required routes."""
        app = watcher_api.create_app()

        # Get route info
        routes = {r.resource.canonical for r in app.router.routes() if r.resource}

        assert "/watch" in routes
        assert "/unwatch/{session_id}" in routes
        assert "/sessions" in routes
        assert "/sessions/{session_id}/events" in routes
        assert "/health" in routes


# --- Tests for integration scenarios ---


class TestIntegrationWatchUnwatchFlow:
    """Integration tests for watch → unwatch flow."""

    async def test_watch_then_unwatch(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """Watch and unwatch a session successfully."""
        session_id = "integration-test"

        # Watch
        watch_response = await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": session_id, "path": str(session_file)}
            )
        )
        assert watch_response.status == 201

        # List should show session
        list_response = await watcher_api.handle_list_sessions(MockRequest())
        list_data = json.loads(list_response.body)
        assert len(list_data["sessions"]) == 1

        # Unwatch
        unwatch_response = await watcher_api.handle_unwatch(
            MockRequest(match_info={"session_id": session_id})
        )
        assert unwatch_response.status == 204

        # List should be empty
        list_response2 = await watcher_api.handle_list_sessions(MockRequest())
        list_data2 = json.loads(list_response2.body)
        assert len(list_data2["sessions"]) == 0

    async def test_watch_multiple_unwatch_one(
        self, watcher_api: WatcherAPI, tmp_path: Path
    ) -> None:
        """Watch multiple sessions and unwatch one."""
        # Create session files
        file1 = tmp_path / "session1.jsonl"
        file2 = tmp_path / "session2.jsonl"
        file1.write_text('{"type":"user"}\n')
        file2.write_text('{"type":"user"}\n')

        # Watch both
        await watcher_api.handle_watch(
            MockRequest(_json_data={"session_id": "session-1", "path": str(file1)})
        )
        await watcher_api.handle_watch(
            MockRequest(_json_data={"session_id": "session-2", "path": str(file2)})
        )

        # Unwatch one
        await watcher_api.handle_unwatch(
            MockRequest(match_info={"session_id": "session-1"})
        )

        # List should show only session-2
        list_response = await watcher_api.handle_list_sessions(MockRequest())
        list_data = json.loads(list_response.body)
        assert len(list_data["sessions"]) == 1
        assert list_data["sessions"][0]["session_id"] == "session-2"


class TestIntegrationHealthWithSessions:
    """Integration tests for health endpoint with sessions."""

    async def test_health_count_updates(
        self, watcher_api: WatcherAPI, tmp_path: Path
    ) -> None:
        """Health endpoint session count updates with watch/unwatch."""
        # Initially no sessions
        response1 = await watcher_api.handle_health(MockRequest())
        data1 = json.loads(response1.body)
        assert data1["sessions_watched"] == 0

        # Watch a session
        file1 = tmp_path / "session1.jsonl"
        file1.write_text('{"type":"user"}\n')
        await watcher_api.handle_watch(
            MockRequest(_json_data={"session_id": "session-1", "path": str(file1)})
        )

        response2 = await watcher_api.handle_health(MockRequest())
        data2 = json.loads(response2.body)
        assert data2["sessions_watched"] == 1

        # Unwatch
        await watcher_api.handle_unwatch(
            MockRequest(match_info={"session_id": "session-1"})
        )

        response3 = await watcher_api.handle_health(MockRequest())
        data3 = json.loads(response3.body)
        assert data3["sessions_watched"] == 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    async def test_watch_empty_file(
        self, watcher_api: WatcherAPI, empty_session_file: Path
    ) -> None:
        """Can watch an empty session file."""
        response = await watcher_api.handle_watch(
            MockRequest(
                _json_data={
                    "session_id": "empty-session",
                    "path": str(empty_session_file),
                }
            )
        )

        assert response.status == 201

    async def test_session_id_with_special_chars(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """Session ID with special characters is handled."""
        # UUID-style session ID with dashes
        response = await watcher_api.handle_watch(
            MockRequest(
                _json_data={
                    "session_id": "014d9d94-abc1-4def-8901-234567890abc",
                    "path": str(session_file),
                }
            )
        )

        assert response.status == 201

        # Verify it's stored correctly
        config = watcher_api.config_manager.get("014d9d94-abc1-4def-8901-234567890abc")
        assert config is not None

    async def test_path_with_spaces(self, watcher_api: WatcherAPI, tmp_path: Path) -> None:
        """Path with spaces is handled correctly."""
        dir_with_space = tmp_path / "dir with spaces"
        dir_with_space.mkdir()
        session_file = dir_with_space / "session.jsonl"
        session_file.write_text('{"type":"user"}\n')

        response = await watcher_api.handle_watch(
            MockRequest(
                _json_data={
                    "session_id": "space-test",
                    "path": str(session_file),
                }
            )
        )

        assert response.status == 201


class TestUnwatchCleansUpResources:
    """Tests that unwatch properly cleans up all resources."""

    async def test_unwatch_removes_event_buffer(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """Unwatch removes the event buffer for the session."""
        # Watch and add an event
        await watcher_api.handle_watch(
            MockRequest(
                _json_data={"session_id": "test-session", "path": str(session_file)}
            )
        )

        # Add an event to the buffer
        event = AddBlock(
            block=Block(
                id="block_1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="test"),
            )
        )
        watcher_api.event_buffer.add_event("test-session", event)

        # Buffer should have the session
        buffer = watcher_api.event_buffer.get_buffer("test-session")
        assert len(buffer) > 0

        # Unwatch
        await watcher_api.handle_unwatch(
            MockRequest(match_info={"session_id": "test-session"})
        )

        # Buffer should be removed (new buffer will be empty)
        new_buffer = watcher_api.event_buffer.get_buffer("test-session")
        assert len(new_buffer) == 0


class TestWatcherAPIStartTime:
    """Tests for WatcherAPI start time tracking."""

    def test_start_time_is_set(self, watcher_api: WatcherAPI) -> None:
        """WatcherAPI has a start time set on creation."""
        assert hasattr(watcher_api, "_start_time")
        assert watcher_api._start_time <= time.time()

    def test_custom_start_time(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """WatcherAPI can be created with custom start time."""
        custom_time = time.time() - 3600  # 1 hour ago

        config_manager = ConfigManager(temp_config_path)
        state_manager = StateManager(temp_state_dir)
        event_buffer = EventBufferManager()
        file_watcher = FileWatcher(
            on_lines_callback=dummy_callback,
        )
        sse_manager = SSEManager(event_buffer=event_buffer)

        api = WatcherAPI(
            config_manager=config_manager,
            state_manager=state_manager,
            file_watcher=file_watcher,
            event_buffer=event_buffer,
            sse_manager=sse_manager,
            _start_time=custom_time,
        )

        assert api._start_time == custom_time
