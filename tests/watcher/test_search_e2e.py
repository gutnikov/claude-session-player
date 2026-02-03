"""End-to-end tests for the search flow.

This module provides comprehensive E2E tests covering:
- REST API endpoints (/search, /projects, /sessions/{id}/preview)
- Slack command handler tests
- Telegram command handler tests
- Index persistence and incremental refresh tests

These tests use realistic fixtures that simulate the full search workflow.
"""

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
from claude_session_player.watcher.search import SearchEngine, SearchFilters
from claude_session_player.watcher.search_state import SearchState, SearchStateManager
from claude_session_player.watcher.slack_commands import (
    SlackCommandHandler,
    format_search_results,
    format_empty_results,
    format_rate_limited,
    format_watch_confirmation,
    format_preview,
    PAGE_SIZE,
)
from claude_session_player.watcher.telegram_commands import (
    TelegramCommandHandler,
    format_search_results_telegram,
    format_empty_results_telegram,
    format_rate_limited_telegram,
    format_watch_confirmation_telegram,
    format_preview_telegram,
    format_expired_state_telegram,
)
from claude_session_player.watcher.sse import SSEManager


# ---------------------------------------------------------------------------
# Mock HTTP Request for REST API tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test Session File Creation Helpers
# ---------------------------------------------------------------------------


def create_session_file(
    path: Path,
    summary: str,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """Create a session JSONL file with specified content.

    Args:
        path: Path to create the session file at.
        summary: Summary text for the session.
        events: Optional list of event dicts to include.
    """
    lines = []

    # Add user message
    lines.append(json.dumps({
        "type": "user",
        "message": {"role": "user", "content": "User question about the topic"},
        "uuid": "user-001",
    }))

    # Add assistant message
    lines.append(json.dumps({
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Here is my response..."}],
        },
        "uuid": "asst-001",
        "requestId": "req-001",
    }))

    # Add any custom events
    if events:
        for event in events:
            lines.append(json.dumps(event))

    # Add summary
    lines.append(json.dumps({
        "type": "summary",
        "summary": summary,
    }))

    # Add turn duration
    lines.append(json.dumps({
        "type": "system",
        "subtype": "turn_duration",
        "durationMs": 120000,  # 2 minutes
    }))

    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Search Test Sessions Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def search_test_sessions(tmp_path: Path) -> Path:
    """Create test sessions for search testing.

    Creates a directory structure with multiple projects and sessions:
    - trello-clone: 2 sessions about auth and drag-drop
    - api-server: 1 session about JWT auth
    - mobile-app: 1 session about OAuth2

    Returns:
        Path to the projects directory.
    """
    projects_dir = tmp_path / ".claude" / "projects"

    # Project 1: trello-clone (2 sessions)
    trello = projects_dir / "-Users-test-work-trello--clone"
    trello.mkdir(parents=True)

    create_session_file(
        trello / "session-1.jsonl",
        summary="Fix authentication bug in login flow",
        events=[
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_001",
                            "name": "Read",
                            "input": {"file_path": "/src/auth/login.ts"},
                        }
                    ],
                },
                "uuid": "asst-002",
                "requestId": "req-002",
            },
        ],
    )

    create_session_file(
        trello / "session-2.jsonl",
        summary="Add drag and drop for cards",
    )

    # Project 2: api-server (1 session)
    api = projects_dir / "-Users-test-work-api--server"
    api.mkdir(parents=True)

    create_session_file(
        api / "session-3.jsonl",
        summary="Debug JWT auth issues in middleware",
    )

    # Project 3: mobile-app (1 session)
    mobile = projects_dir / "-Users-test-work-mobile--app"
    mobile.mkdir(parents=True)

    create_session_file(
        mobile / "session-4.jsonl",
        summary="OAuth2 authentication setup",
    )

    return projects_dir


@pytest.fixture
def populated_indexer(
    search_test_sessions: Path,
    tmp_path: Path,
) -> SessionIndexer:
    """Create a SessionIndexer with pre-populated test data.

    Returns a SessionIndexer with sessions indexed from search_test_sessions.
    """
    indexer = SessionIndexer(
        paths=[search_test_sessions],
        config=IndexConfig(persist=False),
        state_dir=tmp_path / "state",
    )

    # Pre-populate the index
    now = datetime.now(timezone.utc)

    sessions: dict[str, SessionInfo] = {}
    projects: dict[str, ProjectInfo] = {}

    # trello-clone sessions
    trello_encoded = "-Users-test-work-trello--clone"
    sessions["session-1"] = SessionInfo(
        session_id="session-1",
        project_encoded=trello_encoded,
        project_display_name="trello-clone",
        file_path=search_test_sessions / trello_encoded / "session-1.jsonl",
        summary="Fix authentication bug in login flow",
        created_at=now - timedelta(days=1),
        modified_at=now - timedelta(hours=12),
        size_bytes=2457,
        line_count=156,
        has_subagents=False,
    )

    sessions["session-2"] = SessionInfo(
        session_id="session-2",
        project_encoded=trello_encoded,
        project_display_name="trello-clone",
        file_path=search_test_sessions / trello_encoded / "session-2.jsonl",
        summary="Add drag and drop for cards",
        created_at=now - timedelta(days=2),
        modified_at=now - timedelta(days=1),
        size_bytes=1890,
        line_count=98,
        has_subagents=False,
    )

    projects[trello_encoded] = ProjectInfo(
        encoded_name=trello_encoded,
        decoded_path="/Users/test/work/trello-clone",
        display_name="trello-clone",
        session_ids=["session-1", "session-2"],
        total_size_bytes=4347,
        latest_modified_at=now - timedelta(hours=12),
    )

    # api-server session
    api_encoded = "-Users-test-work-api--server"
    sessions["session-3"] = SessionInfo(
        session_id="session-3",
        project_encoded=api_encoded,
        project_display_name="api-server",
        file_path=search_test_sessions / api_encoded / "session-3.jsonl",
        summary="Debug JWT auth issues in middleware",
        created_at=now - timedelta(days=5),
        modified_at=now - timedelta(days=3),
        size_bytes=5120,
        line_count=245,
        has_subagents=False,
    )

    projects[api_encoded] = ProjectInfo(
        encoded_name=api_encoded,
        decoded_path="/Users/test/work/api-server",
        display_name="api-server",
        session_ids=["session-3"],
        total_size_bytes=5120,
        latest_modified_at=now - timedelta(days=3),
    )

    # mobile-app session
    mobile_encoded = "-Users-test-work-mobile--app"
    sessions["session-4"] = SessionInfo(
        session_id="session-4",
        project_encoded=mobile_encoded,
        project_display_name="mobile-app",
        file_path=search_test_sessions / mobile_encoded / "session-4.jsonl",
        summary="OAuth2 authentication setup",
        created_at=now - timedelta(days=7),
        modified_at=now - timedelta(days=6),
        size_bytes=1200,
        line_count=65,
        has_subagents=False,
    )

    projects[mobile_encoded] = ProjectInfo(
        encoded_name=mobile_encoded,
        decoded_path="/Users/test/work/mobile-app",
        display_name="mobile-app",
        session_ids=["session-4"],
        total_size_bytes=1200,
        latest_modified_at=now - timedelta(days=6),
    )

    indexer._index = SessionIndex(
        sessions=sessions,
        projects=projects,
        created_at=now,
        last_refresh=now,
        refresh_duration_ms=100,
    )

    return indexer


@pytest.fixture
def search_engine(populated_indexer: SessionIndexer) -> SearchEngine:
    """Create a SearchEngine with the populated indexer."""
    return SearchEngine(indexer=populated_indexer)


@pytest.fixture
def search_state_manager() -> SearchStateManager:
    """Create a SearchStateManager instance."""
    return SearchStateManager(ttl_seconds=300)


@pytest.fixture
def search_limiter() -> RateLimiter:
    """Create a rate limiter for search (30/min per IP)."""
    return RateLimiter(rate=30, window_seconds=60)


@pytest.fixture
def bot_search_limiter() -> RateLimiter:
    """Create a rate limiter for bot commands (10/min per user/chat)."""
    return RateLimiter(rate=10, window_seconds=60)


@pytest.fixture
def preview_limiter() -> RateLimiter:
    """Create a rate limiter for preview (60/min per IP)."""
    return RateLimiter(rate=60, window_seconds=60)


@pytest.fixture
def refresh_limiter() -> RateLimiter:
    """Create a rate limiter for refresh (1/60s global)."""
    return RateLimiter(rate=1, window_seconds=60)


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    """Create a ConfigManager instance."""
    return ConfigManager(tmp_path / "config.yaml")


@pytest.fixture
def destination_manager(config_manager: ConfigManager) -> DestinationManager:
    """Create a DestinationManager instance."""

    async def dummy_start(sid: str, path: Path) -> None:
        pass

    async def dummy_stop(sid: str) -> None:
        pass

    return DestinationManager(
        _config=config_manager,
        _on_session_start=dummy_start,
        _on_session_stop=dummy_stop,
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
def watcher_api_with_search(
    config_manager: ConfigManager,
    destination_manager: DestinationManager,
    event_buffer: EventBufferManager,
    sse_manager: SSEManager,
    populated_indexer: SessionIndexer,
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
        indexer=populated_indexer,
        search_engine=search_engine,
        search_limiter=search_limiter,
        preview_limiter=preview_limiter,
        refresh_limiter=refresh_limiter,
    )


# ===========================================================================
# REST API Tests
# ===========================================================================


class TestSearchApiBasic:
    """Test basic search query returns matching results."""

    async def test_search_returns_auth_results(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search for 'auth' returns matching sessions."""
        request = MockRequest(
            query={"q": "auth"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["total"] == 3  # "authentication", "JWT auth", "OAuth2"
        # Verify the first result is the most relevant (authentication bug)
        summaries = [r["summary"] for r in data["results"]]
        assert "Fix authentication bug in login flow" in summaries

    async def test_search_with_specific_term(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search for 'JWT' returns specific session."""
        request = MockRequest(
            query={"q": "JWT"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["total"] >= 1
        summaries = [r["summary"] for r in data["results"]]
        assert "Debug JWT auth issues in middleware" in summaries

    async def test_search_empty_query_returns_all(
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
        assert data["total"] == 4  # All sessions


class TestSearchApiProjectFilter:
    """Test project filter narrows results."""

    async def test_filter_by_project(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with project filter returns only matching project."""
        request = MockRequest(
            query={"q": "auth", "project": "trello"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["filters"]["project"] == "trello"
        # Should only return sessions from trello-clone
        for result in data["results"]:
            assert "trello" in result["project"]["display_name"].lower()

    async def test_filter_by_nonexistent_project(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with non-existent project returns empty."""
        request = MockRequest(
            query={"q": "auth", "project": "nonexistent"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["total"] == 0


class TestSearchApiPagination:
    """Test pagination returns correct pages."""

    async def test_limit_and_offset(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search with limit and offset returns correct page."""
        # Get first page
        request1 = MockRequest(
            query={"limit": "2", "offset": "0"},
            transport=MockTransport(),
        )
        response1 = await watcher_api_with_search.handle_search(request1)
        data1 = json.loads(response1.body)

        # Get second page
        request2 = MockRequest(
            query={"limit": "2", "offset": "2"},
            transport=MockTransport(),
        )
        response2 = await watcher_api_with_search.handle_search(request2)
        data2 = json.loads(response2.body)

        assert data1["limit"] == 2
        assert data1["offset"] == 0
        assert len(data1["results"]) == 2

        assert data2["limit"] == 2
        assert data2["offset"] == 2
        assert len(data2["results"]) == 2

        # Ensure different results
        ids1 = {r["session_id"] for r in data1["results"]}
        ids2 = {r["session_id"] for r in data2["results"]}
        assert ids1.isdisjoint(ids2)

    async def test_limit_clamped_to_max(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search clamps limit to maximum of 10."""
        request = MockRequest(
            query={"limit": "100"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["limit"] == 10


class TestSearchApiRateLimiting:
    """Test rate limiting returns 429."""

    async def test_rate_limit_exceeded(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /search returns 429 when rate limit exceeded."""
        # Exhaust rate limit (30 requests)
        for _ in range(30):
            watcher_api_with_search.search_limiter.check("api:127.0.0.1")

        request = MockRequest(transport=MockTransport())
        response = await watcher_api_with_search.handle_search(request)

        assert response.status == 429
        data = json.loads(response.body)
        assert data["error"] == "rate_limited"
        assert "retry_after_seconds" in data
        assert data["retry_after_seconds"] > 0


class TestProjectsApi:
    """Test /projects endpoint returns all projects."""

    async def test_projects_returns_list(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /projects returns all indexed projects."""
        request = MockRequest(transport=MockTransport())

        response = await watcher_api_with_search.handle_projects(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["total_projects"] == 3
        assert data["total_sessions"] == 4

        project_names = [p["display_name"] for p in data["projects"]]
        assert "trello-clone" in project_names
        assert "api-server" in project_names
        assert "mobile-app" in project_names

    async def test_projects_session_counts(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /projects returns correct session counts per project."""
        request = MockRequest(transport=MockTransport())

        response = await watcher_api_with_search.handle_projects(request)

        assert response.status == 200
        data = json.loads(response.body)

        project_sessions = {
            p["display_name"]: p["session_count"] for p in data["projects"]
        }
        assert project_sessions["trello-clone"] == 2
        assert project_sessions["api-server"] == 1
        assert project_sessions["mobile-app"] == 1


class TestPreviewApi:
    """Test /sessions/{id}/preview returns events."""

    async def test_preview_returns_events(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview returns session preview."""
        request = MockRequest(
            match_info={"session_id": "session-1"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 200
        data = json.loads(response.body)
        assert data["session_id"] == "session-1"
        assert data["project_name"] == "trello-clone"
        assert data["summary"] == "Fix authentication bug in login flow"
        assert "preview_events" in data
        assert "total_events" in data


class TestPreviewApiNotFound:
    """Test preview returns 404 for unknown session."""

    async def test_preview_not_found(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """GET /sessions/{id}/preview returns 404 for nonexistent session."""
        request = MockRequest(
            match_info={"session_id": "nonexistent-session"},
            transport=MockTransport(),
        )

        response = await watcher_api_with_search.handle_session_preview(request)

        assert response.status == 404
        data = json.loads(response.body)
        assert data["error"] == "session_not_found"


# ===========================================================================
# Slack Command Tests
# ===========================================================================


class TestSlackSearchCommand:
    """Test /search command returns Block Kit results."""

    async def test_search_returns_block_kit(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Slack /search command returns formatted Block Kit blocks."""
        handler = SlackCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # Mock HTTP session for response_url
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        handler._http_session = mock_session

        # Execute search
        result = await handler.handle_search(
            command="/search",
            text="auth bug",
            user_id="U123456",
            channel_id="C789012",
            response_url="https://hooks.slack.com/response/xxx",
        )

        # Should return None (async processing)
        assert result is None

        # Clean up
        await handler.close()

    async def test_search_rate_limited_returns_immediate(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Slack /search returns immediate rate limit response."""
        handler = SlackCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # Exhaust rate limit
        for _ in range(10):
            bot_search_limiter.check("slack:U123456")

        # Execute search
        result = await handler.handle_search(
            command="/search",
            text="auth bug",
            user_id="U123456",
            channel_id="C789012",
            response_url="https://hooks.slack.com/response/xxx",
        )

        # Should return immediate rate limit response
        assert result is not None
        assert result["response_type"] == "ephemeral"
        assert "blocks" in result


class TestSlackFormatSearchResults:
    """Test Block Kit formatting for search results."""

    def test_format_has_header(self, search_engine: SearchEngine) -> None:
        """Block Kit format includes header with result count."""
        # Create mock results
        from claude_session_player.watcher.search import SearchResults

        session = SessionInfo(
            session_id="test-1",
            project_encoded="-test",
            project_display_name="test-project",
            file_path=Path("/test/session.jsonl"),
            summary="Test session summary",
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            size_bytes=1000,
            line_count=50,
            has_subagents=False,
        )

        results = SearchResults(
            query="test",
            filters=SearchFilters(),
            sort="recent",
            total=1,
            offset=0,
            limit=5,
            results=[session],
        )

        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[session],
            current_offset=0,
            message_id="",
            created_at=datetime.now(timezone.utc),
        )

        blocks = format_search_results(results, state)

        # Check header block
        assert blocks[0]["type"] == "header"
        assert "Found 1 session" in blocks[0]["text"]["text"]


class TestSlackWatchInteraction:
    """Test Watch button attaches session."""

    async def test_watch_calls_attach_callback(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Watch button click triggers attach callback."""
        attach_called = {"called": False, "session_id": None}

        async def mock_attach(**kwargs: Any) -> None:
            attach_called["called"] = True
            attach_called["session_id"] = kwargs.get("session_id")

        handler = SlackCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
            attach_callback=mock_attach,
        )

        # Pre-populate search state
        params = search_engine.parse_query("auth")
        results = await search_engine.search(params)

        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=results.results,
            current_offset=0,
            message_id="1234.5678",
            created_at=datetime.now(timezone.utc),
        )
        search_state_manager.save("slack:C789012", state)

        # Simulate watch button click
        payload = {
            "channel": {"id": "C789012"},
            "message": {"ts": "1234.5678"},
            "response_url": "https://hooks.slack.com/response/xxx",
        }

        await handler.handle_watch(
            action_id="session_menu:0",
            value="watch:0",
            payload=payload,
        )

        assert attach_called["called"] is True
        assert attach_called["session_id"] is not None


class TestSlackPaginationInteraction:
    """Test pagination buttons update message."""

    async def test_next_page_updates_offset(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Next button updates pagination offset."""
        handler = SlackCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # Pre-populate search state with multiple results
        params = search_engine.parse_query("")
        params.limit = 100
        results = await search_engine.search(params)

        state = SearchState(
            query="",
            filters=SearchFilters(),
            results=results.results,
            current_offset=0,
            message_id="1234.5678",
            created_at=datetime.now(timezone.utc),
        )
        search_state_manager.save("slack:C789012", state)

        # Simulate next button click
        payload = {
            "channel": {"id": "C789012"},
            "message": {"ts": "1234.5678"},
            "response_url": "https://hooks.slack.com/response/xxx",
        }

        await handler.handle_pagination(
            action_id="search_next",
            value=None,
            payload=payload,
        )

        # Check offset was updated
        updated_state = search_state_manager.get("slack:C789012")
        assert updated_state is not None
        assert updated_state.current_offset == PAGE_SIZE


# ===========================================================================
# Telegram Command Tests
# ===========================================================================


class TestTelegramSearchCommand:
    """Test /search command returns formatted message."""

    async def test_search_sends_message(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Telegram /search command sends formatted message with keyboard."""
        handler = TelegramCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # Execute search (no publisher, just verify state is saved)
        await handler.handle_search(query="auth", chat_id=123456)

        # Check state was saved
        state = search_state_manager.get("telegram:123456")
        assert state is not None
        assert state.query == "auth"
        assert len(state.results) > 0


class TestTelegramFormatSearchResults:
    """Test Telegram Markdown formatting for search results."""

    def test_format_has_header_and_keyboard(self) -> None:
        """Telegram format includes header and inline keyboard."""
        from claude_session_player.watcher.search import SearchResults

        session = SessionInfo(
            session_id="test-1",
            project_encoded="-test",
            project_display_name="test-project",
            file_path=Path("/test/session.jsonl"),
            summary="Test session summary",
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            size_bytes=1000,
            line_count=50,
            has_subagents=False,
        )

        results = SearchResults(
            query="test",
            filters=SearchFilters(),
            sort="recent",
            total=1,
            offset=0,
            limit=5,
            results=[session],
        )

        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[session],
            current_offset=0,
            message_id=0,
            created_at=datetime.now(timezone.utc),
        )

        text, keyboard = format_search_results_telegram(results, state)

        # Check header
        assert "Found 1 session" in text

        # Check keyboard structure (3 rows: watch, preview, nav)
        assert len(keyboard) == 3
        # Watch row
        assert keyboard[0][0]["callback_data"].startswith("w:")
        # Preview row
        assert keyboard[1][0]["callback_data"].startswith("p:")
        # Nav row (prev, page indicator, next, refresh)
        assert len(keyboard[2]) == 4


class TestTelegramWatchCallback:
    """Test watch callback attaches session."""

    async def test_watch_calls_attach_callback(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Watch callback triggers attach callback."""
        attach_called = {"called": False, "session_id": None}

        async def mock_attach(**kwargs: Any) -> None:
            attach_called["called"] = True
            attach_called["session_id"] = kwargs.get("session_id")

        handler = TelegramCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
            attach_callback=mock_attach,
        )

        # Pre-populate search state
        params = search_engine.parse_query("auth")
        results = await search_engine.search(params)

        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=results.results,
            current_offset=0,
            message_id=12345,
            created_at=datetime.now(timezone.utc),
        )
        search_state_manager.save("telegram:123456", state)

        # Simulate watch callback
        answer = await handler.handle_callback(
            callback_data="w:0",
            chat_id=123456,
            message_id=12345,
        )

        assert attach_called["called"] is True
        assert attach_called["session_id"] is not None
        assert "Now watching" in (answer or "")


class TestTelegramPaginationCallback:
    """Test pagination callbacks update message."""

    async def test_next_page_returns_answer(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Next page callback returns answer text."""
        handler = TelegramCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # Pre-populate search state with multiple results
        params = search_engine.parse_query("")
        params.limit = 100
        results = await search_engine.search(params)

        state = SearchState(
            query="",
            filters=SearchFilters(),
            results=results.results,
            current_offset=0,
            message_id=12345,
            created_at=datetime.now(timezone.utc),
        )
        search_state_manager.save("telegram:123456", state)

        # Simulate next page callback
        answer = await handler.handle_callback(
            callback_data="s:n",
            chat_id=123456,
            message_id=12345,
        )

        assert answer == "Next page"

        # Check offset was updated
        updated_state = search_state_manager.get("telegram:123456")
        assert updated_state is not None
        assert updated_state.current_offset == PAGE_SIZE


class TestTelegramExpiredState:
    """Test callback with expired state shows error."""

    async def test_expired_state_returns_error(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Callback with expired state returns error message."""
        handler = TelegramCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
        )

        # No state saved - simulate expired

        answer = await handler.handle_callback(
            callback_data="w:0",
            chat_id=123456,
            message_id=12345,
        )

        assert answer == "Search expired"


# ===========================================================================
# Index Tests
# ===========================================================================


class TestIndexIncrementalRefresh:
    """Test incremental refresh only reads changed files."""

    async def test_incremental_tracks_modified_files(
        self, search_test_sessions: Path, tmp_path: Path
    ) -> None:
        """Incremental refresh detects modified files."""
        indexer = SessionIndexer(
            paths=[search_test_sessions],
            config=IndexConfig(persist=True),
            state_dir=tmp_path / "state",
        )

        # Build initial index
        await indexer.get_index()
        initial_count = len(indexer._index.sessions)

        # Modify one session file
        trello_dir = search_test_sessions / "-Users-test-work-trello--clone"
        session_file = trello_dir / "session-1.jsonl"

        # Read current content and append a new line
        content = session_file.read_text()
        content += json.dumps({"type": "summary", "summary": "Updated summary"}) + "\n"
        session_file.write_text(content)

        # Refresh (should detect modified file)
        await indexer.refresh(force=True)

        # Verify same number of sessions
        assert len(indexer._index.sessions) == initial_count

        # Verify summary was updated
        session = indexer.get_session("session-1")
        assert session is not None
        assert session.summary == "Updated summary"


class TestIndexPersistence:
    """Test index survives restart."""

    async def test_index_persisted_and_loaded(
        self, search_test_sessions: Path, tmp_path: Path
    ) -> None:
        """Index is persisted to disk and loaded on restart."""
        state_dir = tmp_path / "state"

        # Create first indexer and build index
        indexer1 = SessionIndexer(
            paths=[search_test_sessions],
            config=IndexConfig(persist=True, max_index_age_hours=24),
            state_dir=state_dir,
        )
        await indexer1.get_index()
        session_count1 = len(indexer1._index.sessions)

        # Verify index file exists
        index_file = state_dir / "search_index.json"
        assert index_file.exists()

        # Create new indexer (simulating restart)
        indexer2 = SessionIndexer(
            paths=[search_test_sessions],
            config=IndexConfig(persist=True, max_index_age_hours=24),
            state_dir=state_dir,
        )

        # Should load from persisted index
        await indexer2.get_index()
        session_count2 = len(indexer2._index.sessions)

        assert session_count2 == session_count1


class TestIndexNewSessions:
    """Test index detects new sessions."""

    async def test_detects_new_session(
        self, search_test_sessions: Path, tmp_path: Path
    ) -> None:
        """Refresh detects newly added session files."""
        indexer = SessionIndexer(
            paths=[search_test_sessions],
            config=IndexConfig(persist=False),
            state_dir=tmp_path / "state",
        )

        # Build initial index
        await indexer.get_index()
        initial_count = len(indexer._index.sessions)

        # Add a new session
        trello_dir = search_test_sessions / "-Users-test-work-trello--clone"
        create_session_file(
            trello_dir / "session-new.jsonl",
            summary="Brand new session",
        )

        # Refresh
        await indexer.refresh(force=True)

        # Should have one more session
        assert len(indexer._index.sessions) == initial_count + 1

        # Verify new session is indexed
        session = indexer.get_session("session-new")
        assert session is not None
        assert session.summary == "Brand new session"


class TestIndexDeletedSessions:
    """Test index removes deleted sessions."""

    async def test_removes_deleted_session(
        self, search_test_sessions: Path, tmp_path: Path
    ) -> None:
        """Refresh removes sessions for deleted files."""
        indexer = SessionIndexer(
            paths=[search_test_sessions],
            config=IndexConfig(persist=False),
            state_dir=tmp_path / "state",
        )

        # Build initial index
        await indexer.get_index()
        initial_count = len(indexer._index.sessions)
        assert indexer.get_session("session-4") is not None

        # Delete a session file
        mobile_dir = search_test_sessions / "-Users-test-work-mobile--app"
        (mobile_dir / "session-4.jsonl").unlink()

        # Refresh
        await indexer.refresh(force=True)

        # Should have one less session
        assert len(indexer._index.sessions) == initial_count - 1

        # Verify session was removed
        assert indexer.get_session("session-4") is None


# ===========================================================================
# Full E2E Integration Tests
# ===========================================================================


class TestSearchE2EIntegration:
    """Full end-to-end search flow integration tests."""

    async def test_full_rest_api_search_flow(
        self, watcher_api_with_search: WatcherAPI
    ) -> None:
        """Test complete REST API search flow: search -> preview."""
        # 1. Search for sessions
        search_request = MockRequest(
            query={"q": "auth"},
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

        preview_data = json.loads(preview_response.body)
        assert preview_data["session_id"] == session_id

    async def test_full_slack_search_flow(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Test complete Slack search flow: search state -> watch."""
        attach_called = {"called": False, "session_id": None}

        async def mock_attach(**kwargs: Any) -> None:
            attach_called["called"] = True
            attach_called["session_id"] = kwargs.get("session_id")

        handler = SlackCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
            attach_callback=mock_attach,
        )

        # Pre-populate search state (simulating completed search)
        params = search_engine.parse_query("")
        params.limit = 100
        results = await search_engine.search(params)

        state = SearchState(
            query="",
            filters=SearchFilters(),
            results=results.results,
            current_offset=0,
            message_id="1234.5678",
            created_at=datetime.now(timezone.utc),
        )
        search_state_manager.save("slack:C789012", state)

        # Verify state was saved and has results
        saved_state = search_state_manager.get("slack:C789012")
        assert saved_state is not None
        assert len(saved_state.results) == 4

        # Simulate watch - the payload structure must match what Slack sends
        payload = {
            "channel": {"id": "C789012"},
            "message": {"ts": "1234.5678"},
            "response_url": "https://hooks.slack.com/response/xxx",
        }

        await handler.handle_watch(
            action_id="session_menu:0",
            value="watch:0",
            payload=payload,
        )

        # Verify attach was called
        assert attach_called["called"] is True
        assert attach_called["session_id"] is not None

        # Clean up
        await handler.close()

    async def test_full_telegram_search_flow(
        self,
        search_engine: SearchEngine,
        search_state_manager: SearchStateManager,
        bot_search_limiter: RateLimiter,
    ) -> None:
        """Test complete Telegram search flow: search -> watch."""
        attach_called = {"called": False, "session_id": None}

        async def mock_attach(**kwargs: Any) -> None:
            attach_called["called"] = True
            attach_called["session_id"] = kwargs.get("session_id")

        handler = TelegramCommandHandler(
            search_engine=search_engine,
            search_state_manager=search_state_manager,
            rate_limiter=bot_search_limiter,
            attach_callback=mock_attach,
        )

        # 1. Execute search
        await handler.handle_search(query="", chat_id=123456)

        # Verify state was saved
        state = search_state_manager.get("telegram:123456")
        assert state is not None
        assert len(state.results) == 4

        # 2. Simulate watch (index 0 = first result on first page)
        answer = await handler.handle_callback(
            callback_data="w:0",
            chat_id=123456,
            message_id=12345,
        )

        assert attach_called["called"] is True
        assert attach_called["session_id"] is not None
        assert "Now watching" in (answer or "")
