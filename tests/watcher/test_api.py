"""Tests for the REST API module."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
)
from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import BotConfig, ConfigManager
from claude_session_player.watcher.destinations import DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.sse import SSEManager


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


async def dummy_session_start(session_id: str, path: Path) -> None:
    """Dummy callback for session start."""
    pass


@pytest.fixture
def config_manager(temp_config_path: Path) -> ConfigManager:
    """Create a ConfigManager instance."""
    return ConfigManager(temp_config_path)


@pytest.fixture
def destination_manager(config_manager: ConfigManager) -> DestinationManager:
    """Create a DestinationManager instance."""
    return DestinationManager(
        _config=config_manager,
        _on_session_start=dummy_session_start,
    )


@pytest.fixture
def event_buffer() -> EventBufferManager:
    """Create an EventBufferManager instance."""
    return EventBufferManager()


@pytest.fixture
def sse_manager(event_buffer: EventBufferManager) -> SSEManager:
    """Create an SSEManager instance."""
    return SSEManager(event_buffer=event_buffer)


@pytest.fixture
def watcher_api(
    config_manager: ConfigManager,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
) -> WatcherAPI:
    """Create a WatcherAPI instance with all dependencies."""
    return WatcherAPI(
        config_manager=config_manager,
        destination_manager=destination_manager,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
    )


@pytest.fixture
def watcher_api_with_telegram_token(
    temp_config_path: Path,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
) -> WatcherAPI:
    """Create a WatcherAPI instance with telegram token configured."""
    config_manager = ConfigManager(temp_config_path)
    config_manager.set_bot_config(BotConfig(telegram_token="test-token"))
    config_manager.save([])

    # Re-attach config to destination manager
    destination_manager._config = config_manager

    return WatcherAPI(
        config_manager=config_manager,
        destination_manager=destination_manager,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
    )


@pytest.fixture
def watcher_api_with_slack_token(
    temp_config_path: Path,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
) -> WatcherAPI:
    """Create a WatcherAPI instance with slack token configured."""
    config_manager = ConfigManager(temp_config_path)
    config_manager.set_bot_config(BotConfig(slack_token="xoxb-test-token"))
    config_manager.save([])

    # Re-attach config to destination manager
    destination_manager._config = config_manager

    return WatcherAPI(
        config_manager=config_manager,
        destination_manager=destination_manager,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
    )


# --- Tests for POST /attach ---


class TestHandleAttachSuccess:
    """Tests for POST /attach success cases."""

    async def test_attach_telegram_success(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """Successful POST /attach for telegram returns 201."""
        # Mock validate to not actually call Telegram API
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                    "preset": "desktop",
                }
            )

            response = await watcher_api_with_telegram_token.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["attached"] is True
            assert data["session_id"] == "test-session"
            assert data["destination"]["type"] == "telegram"
            assert data["destination"]["chat_id"] == "123456789"
            assert data["preset"] == "desktop"
            assert data["message_id"] is None  # Set by WatcherService
            assert data["replayed_events"] == 0

    async def test_attach_slack_success(
        self, watcher_api_with_slack_token: WatcherAPI, session_file: Path
    ) -> None:
        """Successful POST /attach for slack returns 201."""
        with patch.object(
            watcher_api_with_slack_token, "_validate_destination", new_callable=AsyncMock
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "slack",
                        "channel": "C0123456789",
                    },
                    "preset": "mobile",
                }
            )

            response = await watcher_api_with_slack_token.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["attached"] is True
            assert data["session_id"] == "test-session"
            assert data["destination"]["type"] == "slack"
            assert data["destination"]["channel"] == "C0123456789"
            assert data["preset"] == "mobile"
            assert data["message_id"] is None  # Set by WatcherService

    async def test_attach_idempotent(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """Duplicate attach returns success (idempotent)."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                    "preset": "desktop",
                }
            )

            # First attach
            response1 = await watcher_api_with_telegram_token.handle_attach(request)
            assert response1.status == 201

            # Second attach (idempotent)
            response2 = await watcher_api_with_telegram_token.handle_attach(request)
            assert response2.status == 201

    async def test_attach_with_replay_count(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """Attach with replay_count returns replayed_events count."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            # Add some events to the buffer
            event = AddBlock(
                block=Block(
                    id="block_1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="test"),
                )
            )
            watcher_api_with_telegram_token.event_buffer.add_event("test-session", event)
            watcher_api_with_telegram_token.event_buffer.add_event("test-session", event)

            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                    "preset": "desktop",
                    "replay_count": 5,
                }
            )

            response = await watcher_api_with_telegram_token.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["replayed_events"] == 2  # Only 2 events in buffer


class TestHandleAttachValidationErrors:
    """Tests for POST /attach validation errors."""

    async def test_invalid_json(self, watcher_api: WatcherAPI) -> None:
        """POST /attach with invalid JSON returns 400."""
        request = MockRequest(_json_error=True)

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "Invalid JSON" in data["error"]

    async def test_missing_session_id(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach without session_id returns 400."""
        request = MockRequest(
            _json_data={
                "path": str(session_file),
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "session_id required" in data["error"]

    async def test_missing_destination(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach without destination returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "destination required" in data["error"]

    async def test_invalid_destination_type(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach with invalid destination type returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "discord"},
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "telegram" in data["error"] and "slack" in data["error"]

    async def test_missing_telegram_chat_id(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for telegram without chat_id returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "telegram"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "chat_id required" in data["error"]

    async def test_missing_slack_channel(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for slack without channel returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "slack"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "channel required" in data["error"]

    async def test_missing_preset(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach without preset returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "preset must be" in data["error"]

    async def test_invalid_preset(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach with invalid preset returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "telegram", "chat_id": "123"},
                "preset": "tablet",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "preset must be" in data["error"]

    async def test_relative_path(self, watcher_api: WatcherAPI) -> None:
        """POST /attach with relative path returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": "relative/path.jsonl",
                "destination": {"type": "telegram", "chat_id": "123"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "absolute" in data["error"].lower()


class TestHandleAttachNotFound:
    """Tests for POST /attach with file not found."""

    async def test_path_not_found(self, watcher_api: WatcherAPI) -> None:
        """POST /attach with nonexistent path returns 404."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": "/nonexistent/path/session.jsonl",
                "destination": {"type": "telegram", "chat_id": "123"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert "not found" in data["error"].lower()


class TestHandleAttachAuthErrors:
    """Tests for POST /attach auth errors (401, 403)."""

    async def test_telegram_token_not_configured(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for telegram without token returns 401."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "telegram", "chat_id": "123"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert "not configured" in data["error"].lower()

    async def test_slack_token_not_configured(
        self, watcher_api: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for slack without token returns 401."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "path": str(session_file),
                "destination": {"type": "slack", "channel": "C123"},
                "preset": "desktop",
            }
        )

        response = await watcher_api.handle_attach(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert "not configured" in data["error"].lower()

    async def test_telegram_validation_failed(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for telegram with invalid token returns 403."""
        from claude_session_player.watcher.telegram_publisher import TelegramAuthError

        with patch.object(
            watcher_api_with_telegram_token,
            "_validate_destination",
            new_callable=AsyncMock,
            side_effect=TelegramAuthError("Invalid token"),
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {"type": "telegram", "chat_id": "123"},
                    "preset": "desktop",
                }
            )

            response = await watcher_api_with_telegram_token.handle_attach(request)

            assert response.status == 403
            data = json.loads(response.body)
            assert "validation failed" in data["error"].lower()

    async def test_slack_validation_failed(
        self, watcher_api_with_slack_token: WatcherAPI, session_file: Path
    ) -> None:
        """POST /attach for slack with invalid token returns 403."""
        from claude_session_player.watcher.slack_publisher import SlackAuthError

        with patch.object(
            watcher_api_with_slack_token,
            "_validate_destination",
            new_callable=AsyncMock,
            side_effect=SlackAuthError("Invalid token"),
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {"type": "slack", "channel": "C123"},
                    "preset": "desktop",
                }
            )

            response = await watcher_api_with_slack_token.handle_attach(request)

            assert response.status == 403
            data = json.loads(response.body)
            assert "validation failed" in data["error"].lower()


# --- Tests for POST /detach ---


class TestHandleDetachSuccess:
    """Tests for POST /detach success cases."""

    async def test_detach_success(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """POST /detach returns 204 on success."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            # First attach
            attach_request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {"type": "telegram", "chat_id": "123"},
                    "preset": "desktop",
                }
            )
            await watcher_api_with_telegram_token.handle_attach(attach_request)

            # Then detach
            detach_request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "destination": {"type": "telegram", "chat_id": "123"},
                }
            )
            response = await watcher_api_with_telegram_token.handle_detach(detach_request)

            assert response.status == 204


class TestHandleDetachValidationErrors:
    """Tests for POST /detach validation errors."""

    async def test_invalid_json(self, watcher_api: WatcherAPI) -> None:
        """POST /detach with invalid JSON returns 400."""
        request = MockRequest(_json_error=True)

        response = await watcher_api.handle_detach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "Invalid JSON" in data["error"]

    async def test_missing_session_id(self, watcher_api: WatcherAPI) -> None:
        """POST /detach without session_id returns 400."""
        request = MockRequest(
            _json_data={
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api.handle_detach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "required" in data["error"]

    async def test_missing_destination(self, watcher_api: WatcherAPI) -> None:
        """POST /detach without destination returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
            }
        )

        response = await watcher_api.handle_detach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "required" in data["error"]

    async def test_invalid_destination_type(self, watcher_api: WatcherAPI) -> None:
        """POST /detach with invalid destination type returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "destination": {"type": "discord"},
            }
        )

        response = await watcher_api.handle_detach(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "Invalid destination type" in data["error"]

    async def test_missing_identifier(self, watcher_api: WatcherAPI) -> None:
        """POST /detach without identifier returns 400."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session",
                "destination": {"type": "telegram"},
            }
        )

        response = await watcher_api.handle_detach(request)

        assert response.status == 400
        data = json.loads(response.body)
        # Error message says "chat_id required" for telegram
        assert "chat_id required" in data["error"].lower() or "identifier required" in data["error"].lower()


class TestHandleDetachNotFound:
    """Tests for POST /detach with not found."""

    async def test_destination_not_found(self, watcher_api: WatcherAPI) -> None:
        """POST /detach for nonexistent destination returns 404."""
        request = MockRequest(
            _json_data={
                "session_id": "nonexistent-session",
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api.handle_detach(request)

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

    async def test_list_sessions_with_destinations(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions returns sessions with destinations."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            # Attach a destination
            attach_request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {"type": "telegram", "chat_id": "123456789"},
                    "preset": "desktop",
                }
            )
            await watcher_api_with_telegram_token.handle_attach(attach_request)

            # List sessions
            request = MockRequest()
            response = await watcher_api_with_telegram_token.handle_list_sessions(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert len(data["sessions"]) == 1
            session = data["sessions"][0]
            assert session["session_id"] == "test-session"
            assert session["path"] == str(session_file)
            assert "sse_clients" in session
            assert "destinations" in session
            assert session["destinations"]["telegram"] == [{"chat_id": "123456789"}]
            assert session["destinations"]["slack"] == []

    async def test_list_sessions_multiple_destinations(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """GET /sessions shows multiple destinations."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            # Attach first destination
            await watcher_api_with_telegram_token.handle_attach(
                MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "path": str(session_file),
                        "destination": {"type": "telegram", "chat_id": "111"},
                        "preset": "desktop",
                    }
                )
            )

            # Attach second destination
            await watcher_api_with_telegram_token.handle_attach(
                MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "destination": {"type": "telegram", "chat_id": "222"},
                        "preset": "mobile",
                    }
                )
            )

            # List sessions
            response = await watcher_api_with_telegram_token.handle_list_sessions(
                MockRequest()
            )

            data = json.loads(response.body)
            session = data["sessions"][0]
            telegram_dests = session["destinations"]["telegram"]
            assert len(telegram_dests) == 2
            chat_ids = {d["chat_id"] for d in telegram_dests}
            assert "111" in chat_ids
            assert "222" in chat_ids


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

    async def test_health_returns_uptime(self, watcher_api: WatcherAPI) -> None:
        """GET /health returns uptime_seconds."""
        request = MockRequest()

        response = await watcher_api.handle_health(request)

        data = json.loads(response.body)
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0

    async def test_health_returns_bot_status_not_configured(
        self, watcher_api: WatcherAPI
    ) -> None:
        """GET /health returns not_configured for bots without tokens."""
        request = MockRequest()

        response = await watcher_api.handle_health(request)

        data = json.loads(response.body)
        assert "bots" in data
        assert data["bots"]["telegram"] == "not_configured"
        assert data["bots"]["slack"] == "not_configured"

    async def test_health_returns_bot_status_telegram_configured(
        self, watcher_api_with_telegram_token: WatcherAPI
    ) -> None:
        """GET /health returns configured for telegram with token."""
        request = MockRequest()

        response = await watcher_api_with_telegram_token.handle_health(request)

        data = json.loads(response.body)
        assert data["bots"]["telegram"] == "configured"
        assert data["bots"]["slack"] == "not_configured"

    async def test_health_returns_bot_status_slack_configured(
        self, watcher_api_with_slack_token: WatcherAPI
    ) -> None:
        """GET /health returns configured for slack with token."""
        request = MockRequest()

        response = await watcher_api_with_slack_token.handle_health(request)

        data = json.loads(response.body)
        assert data["bots"]["telegram"] == "not_configured"
        assert data["bots"]["slack"] == "configured"


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

        assert "/attach" in routes
        assert "/detach" in routes
        assert "/sessions" in routes
        assert "/sessions/{session_id}/events" in routes
        assert "/health" in routes

        # Old endpoints should NOT be registered
        assert "/watch" not in routes
        assert "/unwatch/{session_id}" not in routes


# --- Tests for integration scenarios ---


class TestIntegrationAttachDetachFlow:
    """Integration tests for attach → detach flow."""

    async def test_attach_then_detach(
        self, watcher_api_with_telegram_token: WatcherAPI, session_file: Path
    ) -> None:
        """Attach and detach a destination successfully."""
        with patch.object(
            watcher_api_with_telegram_token, "_validate_destination", new_callable=AsyncMock
        ):
            # Attach
            attach_response = await watcher_api_with_telegram_token.handle_attach(
                MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "path": str(session_file),
                        "destination": {"type": "telegram", "chat_id": "123"},
                        "preset": "desktop",
                    }
                )
            )
            assert attach_response.status == 201

            # List should show session with destination
            list_response = await watcher_api_with_telegram_token.handle_list_sessions(
                MockRequest()
            )
            list_data = json.loads(list_response.body)
            assert len(list_data["sessions"]) == 1
            assert list_data["sessions"][0]["destinations"]["telegram"] == [{"chat_id": "123"}]

            # Detach
            detach_response = await watcher_api_with_telegram_token.handle_detach(
                MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "destination": {"type": "telegram", "chat_id": "123"},
                    }
                )
            )
            assert detach_response.status == 204

            # Session still exists in config (keep-alive timer will remove it later)
            list_response2 = await watcher_api_with_telegram_token.handle_list_sessions(
                MockRequest()
            )
            list_data2 = json.loads(list_response2.body)
            # Destinations should be empty but session may still exist
            if list_data2["sessions"]:
                assert list_data2["sessions"][0]["destinations"]["telegram"] == []


class TestWatcherAPIStartTime:
    """Tests for WatcherAPI start time tracking."""

    def test_start_time_is_set(self, watcher_api: WatcherAPI) -> None:
        """WatcherAPI has a start time set on creation."""
        assert hasattr(watcher_api, "_start_time")
        assert watcher_api._start_time <= time.time()

    def test_custom_start_time(
        self,
        config_manager: ConfigManager,
        destination_manager: DestinationManager,
        event_buffer: EventBufferManager,
        sse_manager: SSEManager,
    ) -> None:
        """WatcherAPI can be created with custom start time."""
        custom_time = time.time() - 3600  # 1 hour ago

        api = WatcherAPI(
            config_manager=config_manager,
            destination_manager=destination_manager,
            event_buffer=event_buffer,
            sse_manager=sse_manager,
            _start_time=custom_time,
        )

        assert api._start_time == custom_time


# --- Tests for module imports ---


class TestModuleImports:
    """Tests for module imports and __all__."""

    def test_watcher_api_importable(self) -> None:
        """WatcherAPI can be imported from watcher module."""
        from claude_session_player.watcher import WatcherAPI

        assert WatcherAPI is not None
