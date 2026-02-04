"""Tests for the REST API search endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.api import WatcherAPI
from claude_session_player.watcher.config import BotConfig, ConfigManager
from claude_session_player.watcher.destinations import DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.indexer import (
    IndexConfig,
    SessionIndexer,
    SessionInfo,
    ProjectInfo,
    SessionIndex,
)
from claude_session_player.watcher.rate_limit import RateLimiter
from claude_session_player.watcher.search import SearchEngine
from claude_session_player.watcher.sse import SSEManager


# --- Mock HTTP Request ---


@dataclass
class MockRequest:
    """Mock aiohttp request for testing."""

    match_info: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    _json_data: dict | None = None
    _json_error: bool = False
    transport: Any = None

    async def json(self) -> dict:
        """Return JSON body."""
        if self._json_error:
            raise json.JSONDecodeError("Invalid JSON", "", 0)
        return self._json_data or {}


class MockTransport:
    """Mock transport with peer info."""

    def get_extra_info(self, key: str) -> Any:
        if key == "peername":
            return ("127.0.0.1", 12345)
        return None


# --- Fixtures ---


@pytest.fixture
def temp_config_path(tmp_path: Path) -> Path:
    """Create a temporary config file path."""
    return tmp_path / "config.yaml"


@pytest.fixture
def session_file(tmp_path: Path) -> Path:
    """Create a temporary session file with content."""
    session_path = tmp_path / "session.jsonl"
    session_path.write_text(
        '{"type":"user","message":{"content":"hello"}}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":"hi"}]}}\n'
        '{"type":"summary","summary":"Test session summary"}\n'
    )
    return session_path


@pytest.fixture
def config_manager(temp_config_path: Path) -> ConfigManager:
    """Create a ConfigManager instance."""
    return ConfigManager(temp_config_path)


@pytest.fixture
def destination_manager(config_manager: ConfigManager) -> DestinationManager:
    """Create a DestinationManager instance."""

    async def dummy_start(sid: str, path: Path) -> None:
        pass

    return DestinationManager(
        _config=config_manager,
        _on_session_start=dummy_start,
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
def indexer(tmp_path: Path, session_file: Path) -> SessionIndexer:
    """Create a SessionIndexer with test data."""
    # Create project structure
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "-test-project"
    project_dir.mkdir(parents=True)

    # Copy session file
    session_path = project_dir / "test-session-id.jsonl"
    session_path.write_text(session_file.read_text())

    # Create indexer
    indexer = SessionIndexer(
        paths=[projects_dir],
        config=IndexConfig(persist=False),
        state_dir=tmp_path / "state",
    )

    # Pre-populate index
    now = datetime.now(timezone.utc)
    session_info = SessionInfo(
        session_id="test-session-id",
        project_encoded="-test-project",
        project_display_name="test-project",
        file_path=session_path,
        summary="Test session summary",
        created_at=now - timedelta(hours=1),
        modified_at=now,
        size_bytes=150,
        line_count=3,
        has_subagents=False,
    )

    project_info = ProjectInfo(
        encoded_name="-test-project",
        decoded_path="/test/project",
        display_name="test-project",
        session_ids=["test-session-id"],
        total_size_bytes=150,
        latest_modified_at=now,
    )

    indexer._index = SessionIndex(
        sessions={"test-session-id": session_info},
        projects={"-test-project": project_info},
        created_at=now,
        last_refresh=now,
        refresh_duration_ms=100,
    )

    return indexer


@pytest.fixture
def search_engine(indexer: SessionIndexer) -> SearchEngine:
    """Create a SearchEngine instance."""
    return SearchEngine(indexer=indexer)


@pytest.fixture
def search_limiter() -> RateLimiter:
    """Create a rate limiter for search (30/min)."""
    return RateLimiter(rate=30, window_seconds=60)


@pytest.fixture
def preview_limiter() -> RateLimiter:
    """Create a rate limiter for preview (60/min)."""
    return RateLimiter(rate=60, window_seconds=60)


@pytest.fixture
def refresh_limiter() -> RateLimiter:
    """Create a rate limiter for refresh (1/60s global)."""
    return RateLimiter(rate=1, window_seconds=60)


@pytest.fixture
def watcher_api_with_search(
    config_manager: ConfigManager,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
    indexer: SessionIndexer,
    search_engine: SearchEngine,
    search_limiter: RateLimiter,
    preview_limiter: RateLimiter,
    refresh_limiter: RateLimiter,
) -> WatcherAPI:
    """Create a WatcherAPI instance with search components."""
    return WatcherAPI(
        config_manager=config_manager,
        destination_manager=destination_manager,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
        indexer=indexer,
        search_engine=search_engine,
        search_limiter=search_limiter,
        preview_limiter=preview_limiter,
        refresh_limiter=refresh_limiter,
    )


@pytest.fixture
def watcher_api_no_search(
    config_manager: ConfigManager,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
) -> WatcherAPI:
    """Create a WatcherAPI instance without search components."""
    return WatcherAPI(
        config_manager=config_manager,
        destination_manager=destination_manager,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
    )


# --- Tests for GET /search ---


class TestHandleSearchSuccess:
    """Tests for GET /search success cases."""

    async def test_search_returns_results(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search returns matching sessions."""
        request = MockRequest(
            query={"q": "test"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "test"

    async def test_search_empty_query(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with empty query returns all sessions."""
        request = MockRequest(
            query={},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["query"] == ""
        assert data["total"] >= 0

    async def test_search_with_project_filter(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with project filter."""
        request = MockRequest(
            query={"q": "test", "project": "test-project"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["filters"]["project"] == "test-project"

    async def test_search_with_date_filters(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with since/until filters."""
        request = MockRequest(
            query={
                "q": "test",
                "since": "2024-01-01",
                "until": "2024-12-31",
            },
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["filters"]["since"] is not None
        assert data["filters"]["until"] is not None

    async def test_search_pagination(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with limit and offset."""
        request = MockRequest(
            query={"limit": "3", "offset": "0"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["limit"] == 3
        assert data["offset"] == 0

    async def test_search_limit_clamped(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search clamps limit to max 10."""
        request = MockRequest(
            query={"limit": "100"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["limit"] == 10

    async def test_search_sort_options(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search accepts sort parameter."""
        for sort in ["recent", "oldest", "size", "duration"]:
            request = MockRequest(
                query={"sort": sort},
                transport=MockTransport(),
            )

            response = await watcher_api_with_search.handle_search(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert data["sort"] == sort


class TestHandleSearchErrors:
    """Tests for GET /search error cases."""

    async def test_search_not_available(
        self, watcher_api_no_search: WatcherAPI
    ) -> None:
        """GET /search returns 503 when search not available."""
        request = MockRequest(transport=MockTransport())

        response = await watcher_api_no_search.handle_search(request)

        assert response.status == 503
        data = json.loads(response.body)
        assert "not available" in data["error"].lower()

    async def test_search_rate_limited(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search returns 429 when rate limited."""
        request = MockRequest(transport=MockTransport())

        # Exhaust rate limit
        for _ in range(30):
            watcher_api_with_search.search_limiter.check("api:127.0.0.1")

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 429
        data = json.loads(response.body)
        assert data["error"] == "rate_limited"
        assert "retry_after_seconds" in data


# --- Tests for GET /projects ---


class TestHandleProjectsSuccess:
    """Tests for GET /projects success cases."""

    async def test_projects_returns_list(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /projects returns project list."""
        request = MockRequest(transport=MockTransport())

        response = await watcher_api_with_search.handle_projects(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert "projects" in data
        assert "total_projects" in data
        assert "total_sessions" in data
        assert "index_age_seconds" in data

    async def test_projects_with_date_filters(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /projects with date filters."""
        request = MockRequest(
            query={
                "since": "2024-01-01",
                "until": "2026-12-31",
            },
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_projects(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["total_projects"] >= 0


class TestHandleProjectsErrors:
    """Tests for GET /projects error cases."""

    async def test_projects_not_available(
        self, watcher_api_no_search: WatcherAPI
    ) -> None:
        """GET /projects returns 503 when search not available."""
        request = MockRequest(transport=MockTransport())

        response = await watcher_api_no_search.handle_projects(request)

        assert response.status == 503


# --- Tests for GET /sessions/{id}/preview ---


class TestHandleSessionPreviewSuccess:
    """Tests for GET /sessions/{id}/preview success cases."""

    async def test_preview_returns_events(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview returns preview events."""
        request = MockRequest(
            match_info={"session_id": "test-session-id"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["session_id"] == "test-session-id"
        assert "project_name" in data
        assert "summary" in data
        assert "total_events" in data
        assert "preview_events" in data
        assert "duration_ms" in data

    async def test_preview_with_limit(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview respects limit parameter."""
        request = MockRequest(
            match_info={"session_id": "test-session-id"},
            query={"limit": "10"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 200

    async def test_preview_limit_clamped(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview clamps limit to max 20."""
        request = MockRequest(
            match_info={"session_id": "test-session-id"},
            query={"limit": "100"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 200


class TestHandleSessionPreviewErrors:
    """Tests for GET /sessions/{id}/preview error cases."""

    async def test_preview_session_not_found(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview returns 404 for unknown session."""
        request = MockRequest(
            match_info={"session_id": "nonexistent-session"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert data["error"] == "session_not_found"

    async def test_preview_not_available(
        self, watcher_api_no_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview returns 503 when search not available."""
        request = MockRequest(
            match_info={"session_id": "test-session-id"},
            transport=MockTransport(),
        )

        response = await watcher_api_no_search.handle_session_preview(request)

        assert response.status == 503


# --- Tests for POST /index/refresh ---


class TestHandleIndexRefreshSuccess:
    """Tests for POST /index/refresh success cases."""

    async def test_refresh_starts_indexing(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /index/refresh returns 202 and starts refresh."""
        request = MockRequest()

        response = await watcher_api_with_search.handle_index_refresh(request)

        assert response.status == 202
        data = json.loads(response.body)
        assert data["status"] == "started"
        assert "message" in data


class TestHandleIndexRefreshErrors:
    """Tests for POST /index/refresh error cases."""

    async def test_refresh_not_available(
        self, watcher_api_no_search: WatcherAPI
    ) -> None:
        """POST /index/refresh returns 503 when search not available."""
        request = MockRequest()

        response = await watcher_api_no_search.handle_index_refresh(request)

        assert response.status == 503

    async def test_refresh_rate_limited(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /index/refresh returns 429 when rate limited."""
        request = MockRequest()

        # First request succeeds
        response1 = await watcher_api_with_search.handle_index_refresh(request)
        assert response1.status == 202

        # Second request is rate limited
        response2 = await watcher_api_with_search.handle_index_refresh(request)
        assert response2.status == 429
        data = json.loads(response2.body)
        assert data["error"] == "rate_limited"
        assert "retry_after_seconds" in data


# --- Tests for POST /search/watch ---


class TestHandleSearchWatchSuccess:
    """Tests for POST /search/watch success cases."""

    async def test_search_watch_attaches_session(
        self, watcher_api_with_search: WatcherAPI, temp_config_path: Path
    ) -> None:
        """POST /search/watch attaches session from index."""
        # Configure telegram token
        watcher_api_with_search.config_manager.set_bot_config(
            BotConfig(telegram_token="test-token")
        )

        # Mock validate_destination
        with patch.object(
            watcher_api_with_search, "_validate_destination", new_callable=AsyncMock
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session-id",
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                    "preset": "desktop",
                }
            )

            response = await watcher_api_with_search.handle_search_watch(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["attached"] is True
            assert data["session_id"] == "test-session-id"
            assert data["preset"] == "desktop"
            assert data["session_summary"] == "Test session summary"

    async def test_search_watch_default_replay_count(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch uses default replay_count of 5."""
        watcher_api_with_search.config_manager.set_bot_config(
            BotConfig(telegram_token="test-token")
        )

        with patch.object(
            watcher_api_with_search, "_validate_destination", new_callable=AsyncMock
        ):
            request = MockRequest(
                _json_data={
                    "session_id": "test-session-id",
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                    "preset": "mobile",
                }
            )

            response = await watcher_api_with_search.handle_search_watch(request)

            assert response.status == 201


class TestHandleSearchWatchErrors:
    """Tests for POST /search/watch error cases."""

    async def test_search_watch_invalid_json(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 400 for invalid JSON."""
        request = MockRequest(_json_error=True)

        response = await watcher_api_with_search.handle_search_watch(request)

        assert response.status == 400

    async def test_search_watch_missing_session_id(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 400 for missing session_id."""
        request = MockRequest(
            _json_data={
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api_with_search.handle_search_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "session_id required" in data["error"]

    async def test_search_watch_missing_destination(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 400 for missing destination."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session-id",
            }
        )

        response = await watcher_api_with_search.handle_search_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "destination required" in data["error"]

    async def test_search_watch_missing_preset(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 400 for missing preset."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session-id",
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api_with_search.handle_search_watch(request)

        assert response.status == 400
        data = json.loads(response.body)
        assert "preset must be" in data["error"]

    async def test_search_watch_session_not_found(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 404 for unknown session."""
        request = MockRequest(
            _json_data={
                "session_id": "nonexistent-session",
                "destination": {"type": "telegram", "chat_id": "123"},
                "preset": "desktop",
            }
        )

        response = await watcher_api_with_search.handle_search_watch(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert data["error"] == "session_not_found"

    async def test_search_watch_not_available(
        self, watcher_api_no_search: WatcherAPI
    ) -> None:
        """POST /search/watch returns 503 when search not available."""
        request = MockRequest(
            _json_data={
                "session_id": "test-session-id",
                "destination": {"type": "telegram", "chat_id": "123"},
            }
        )

        response = await watcher_api_no_search.handle_search_watch(request)

        assert response.status == 503


# --- Tests for route registration ---


class TestCreateAppSearchRoutes:
    """Tests for search route registration."""

    def test_registers_search_routes(self, watcher_api_with_search: WatcherAPI) -> None:
        """create_app() registers search routes."""
        app = watcher_api_with_search.create_app()

        routes = {r.resource.canonical for r in app.router.routes() if r.resource}

        assert "/search" in routes
        assert "/projects" in routes
        assert "/sessions/{session_id}/preview" in routes
        assert "/index/refresh" in routes
        assert "/search/watch" in routes


# --- Tests for helper methods ---


class TestGetClientIp:
    """Tests for _get_client_ip method."""

    def test_from_transport(self, watcher_api_with_search: WatcherAPI) -> None:
        """_get_client_ip gets IP from transport."""
        request = MockRequest(transport=MockTransport())

        ip = watcher_api_with_search._get_client_ip(request)

        assert ip == "127.0.0.1"

    def test_from_x_forwarded_for(self, watcher_api_with_search: WatcherAPI) -> None:
        """_get_client_ip gets IP from X-Forwarded-For header."""
        request = MockRequest(
            headers={"X-Forwarded-For": "192.168.1.1, 10.0.0.1"},
            transport=MockTransport(),
        )

        ip = watcher_api_with_search._get_client_ip(request)

        assert ip == "192.168.1.1"

    def test_no_transport(self, watcher_api_with_search: WatcherAPI) -> None:
        """_get_client_ip returns 'unknown' when no transport."""
        request = MockRequest(transport=None)

        ip = watcher_api_with_search._get_client_ip(request)

        assert ip == "unknown"


class TestGetIndexAgeSeconds:
    """Tests for _get_index_age_seconds method."""

    def test_returns_age(self, watcher_api_with_search: WatcherAPI) -> None:
        """_get_index_age_seconds returns index age."""
        age = watcher_api_with_search._get_index_age_seconds()

        assert isinstance(age, int)
        assert age >= 0

    def test_no_indexer(self, watcher_api_no_search: WatcherAPI) -> None:
        """_get_index_age_seconds returns 0 when no indexer."""
        age = watcher_api_no_search._get_index_age_seconds()

        assert age == 0


# --- Integration tests ---


class TestSearchIntegration:
    """Integration tests for search flow."""

    async def test_full_search_flow(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """Test searching, previewing, and watching a session."""
        # 1. Search for sessions
        search_request = MockRequest(
            query={"q": "test"},
            transport=MockTransport(),
        )
        search_response = await watcher_api_with_search.handle_search(search_request)
        assert search_response.status == 200
        search_data = json.loads(search_response.body)
        assert search_data["total"] > 0

        # 2. Get preview of first result
        session_id = search_data["results"][0]["session_id"]
        preview_request = MockRequest(
            match_info={"session_id": session_id},
            transport=MockTransport(),
        )
        preview_response = await watcher_api_with_search.handle_session_preview(
            preview_request
        )
        assert preview_response.status == 200

        # 3. Watch the session (skip actual attach due to bot token requirement)
        # This would normally attach the session via POST /search/watch
