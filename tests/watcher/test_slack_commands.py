"""Tests for the SlackCommandHandler module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.indexer import SessionInfo
from claude_session_player.watcher.rate_limit import RateLimiter
from claude_session_player.watcher.search import SearchEngine, SearchFilters, SearchResults
from claude_session_player.watcher.search_state import SearchState, SearchStateManager
from claude_session_player.watcher.slack_commands import (
    PAGE_SIZE,
    SlackCommandHandler,
    _escape_mrkdwn,
    _format_date,
    _format_duration,
    _format_file_size,
    format_empty_results,
    format_error,
    format_preview,
    format_rate_limited,
    format_search_results,
    format_watch_confirmation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_session_info(
    session_id: str = "sess-001",
    project_display_name: str = "test-project",
    summary: str | None = "Test summary",
    modified_at: datetime | None = None,
    duration_ms: int | None = 60000,
    size_bytes: int = 1024,
) -> SessionInfo:
    """Create a SessionInfo for testing."""
    if modified_at is None:
        modified_at = datetime.now(timezone.utc)
    return SessionInfo(
        session_id=session_id,
        project_encoded="-test-project",
        project_display_name=project_display_name,
        file_path=Path(f"/path/to/{session_id}.jsonl"),
        summary=summary,
        created_at=modified_at - timedelta(hours=1),
        modified_at=modified_at,
        size_bytes=size_bytes,
        line_count=100,
        has_subagents=False,
    )


@pytest.fixture
def search_state_manager() -> SearchStateManager:
    """Create a SearchStateManager."""
    return SearchStateManager(ttl_seconds=300)


@pytest.fixture
def rate_limiter() -> RateLimiter:
    """Create a RateLimiter for search commands."""
    return RateLimiter(rate=10, window_seconds=60)


@pytest.fixture
def mock_search_engine() -> MagicMock:
    """Create a mock SearchEngine."""
    engine = MagicMock(spec=SearchEngine)
    engine.parse_query = MagicMock()
    engine.search = AsyncMock()
    return engine


@pytest.fixture
def mock_slack_publisher() -> MagicMock:
    """Create a mock SlackPublisher."""
    publisher = MagicMock()
    publisher.send_message = AsyncMock(return_value="123.456")
    publisher.update_message = AsyncMock(return_value=True)
    publisher._client = MagicMock()
    publisher._client.chat_postMessage = AsyncMock()
    return publisher


@pytest.fixture
def handler(
    mock_search_engine: MagicMock,
    search_state_manager: SearchStateManager,
    rate_limiter: RateLimiter,
    mock_slack_publisher: MagicMock,
) -> SlackCommandHandler:
    """Create a SlackCommandHandler."""
    return SlackCommandHandler(
        search_engine=mock_search_engine,
        search_state_manager=search_state_manager,
        rate_limiter=rate_limiter,
        slack_publisher=mock_slack_publisher,
    )


@pytest.fixture
def sample_sessions() -> list[SessionInfo]:
    """Create sample sessions for testing."""
    now = datetime.now(timezone.utc)
    return [
        make_session_info(
            session_id="sess-001",
            project_display_name="trello-clone",
            summary="Fix authentication bug in login flow",
            modified_at=now - timedelta(days=1),
            duration_ms=1380000,
            size_bytes=2457,
        ),
        make_session_info(
            session_id="sess-002",
            project_display_name="api-server",
            summary="Debug JWT auth issues in middleware",
            modified_at=now - timedelta(days=5),
            duration_ms=2700000,
            size_bytes=5243,
        ),
        make_session_info(
            session_id="sess-003",
            project_display_name="mobile-app",
            summary="OAuth2 authentication setup",
            modified_at=now - timedelta(days=8),
            duration_ms=720000,
            size_bytes=1228,
        ),
    ]


@pytest.fixture
def search_state(sample_sessions: list[SessionInfo]) -> SearchState:
    """Create a SearchState for testing."""
    return SearchState(
        query="auth bug",
        filters=SearchFilters(),
        results=sample_sessions,
        current_offset=0,
        message_id="123.456",
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests for utility functions
# ---------------------------------------------------------------------------


class TestFormatFileSize:
    """Tests for _format_file_size."""

    def test_bytes(self) -> None:
        """Test formatting bytes."""
        assert _format_file_size(500) == "500 B"

    def test_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        assert _format_file_size(2048) == "2.0 KB"
        assert _format_file_size(1536) == "1.5 KB"

    def test_megabytes(self) -> None:
        """Test formatting megabytes."""
        assert _format_file_size(1048576) == "1.0 MB"
        assert _format_file_size(2621440) == "2.5 MB"


class TestFormatDuration:
    """Tests for _format_duration."""

    def test_none(self) -> None:
        """Test formatting None duration."""
        assert _format_duration(None) == "?"

    def test_seconds(self) -> None:
        """Test formatting seconds."""
        assert _format_duration(30000) == "30s"

    def test_minutes(self) -> None:
        """Test formatting minutes."""
        assert _format_duration(120000) == "2m"
        assert _format_duration(60000) == "1m"

    def test_hours(self) -> None:
        """Test formatting hours."""
        assert _format_duration(3660000) == "1h 1m"
        assert _format_duration(7200000) == "2h 0m"


class TestFormatDate:
    """Tests for _format_date."""

    def test_format(self) -> None:
        """Test date formatting."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert _format_date(dt) == "Jan 15"


class TestEscapeMrkdwn:
    """Tests for _escape_mrkdwn."""

    def test_ampersand(self) -> None:
        """Test escaping ampersand."""
        assert _escape_mrkdwn("foo & bar") == "foo &amp; bar"

    def test_less_than(self) -> None:
        """Test escaping less than."""
        assert _escape_mrkdwn("a < b") == "a &lt; b"

    def test_greater_than(self) -> None:
        """Test escaping greater than."""
        assert _escape_mrkdwn("a > b") == "a &gt; b"

    def test_combined(self) -> None:
        """Test escaping all special characters."""
        assert _escape_mrkdwn("<a & b>") == "&lt;a &amp; b&gt;"


# ---------------------------------------------------------------------------
# Tests for Block Kit formatting
# ---------------------------------------------------------------------------


class TestFormatSearchResults:
    """Tests for format_search_results."""

    def test_basic_formatting(
        self, sample_sessions: list[SessionInfo], search_state: SearchState
    ) -> None:
        """Test basic search results formatting."""
        results = SearchResults(
            query="auth bug",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )
        blocks = format_search_results(results, search_state)

        # Should have header
        assert blocks[0]["type"] == "header"
        assert "Found 3 sessions" in blocks[0]["text"]["text"]

        # Should have result sections
        section_blocks = [b for b in blocks if b["type"] == "section" and "accessory" in b]
        assert len(section_blocks) == 3

        # First result should have project name
        assert "trello-clone" in section_blocks[0]["text"]["text"]

    def test_single_result_grammar(self, sample_sessions: list[SessionInfo]) -> None:
        """Test that single result uses singular 'session'."""
        single_session = [sample_sessions[0]]
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=single_session,
            current_offset=0,
            message_id="123.456",
        )
        results = SearchResults(
            query="auth",
            filters=SearchFilters(),
            sort="recent",
            total=1,
            offset=0,
            limit=PAGE_SIZE,
            results=single_session,
        )
        blocks = format_search_results(results, state)

        # Should say "session" not "sessions"
        assert "Found 1 session" in blocks[0]["text"]["text"]

    def test_overflow_menu(
        self, sample_sessions: list[SessionInfo], search_state: SearchState
    ) -> None:
        """Test that each result has an overflow menu."""
        results = SearchResults(
            query="auth bug",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )
        blocks = format_search_results(results, search_state)

        # Find section blocks with accessory
        section_blocks = [b for b in blocks if b["type"] == "section" and "accessory" in b]
        for i, block in enumerate(section_blocks):
            accessory = block["accessory"]
            assert accessory["type"] == "overflow"
            assert accessory["action_id"] == f"session_menu:{i}"
            assert len(accessory["options"]) == 2
            assert accessory["options"][0]["value"] == f"watch:{i}"
            assert accessory["options"][1]["value"] == f"preview:{i}"

    def test_pagination_buttons(
        self, sample_sessions: list[SessionInfo], search_state: SearchState
    ) -> None:
        """Test that pagination buttons are present."""
        results = SearchResults(
            query="auth bug",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )
        blocks = format_search_results(results, search_state)

        # Find actions block
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        assert len(action_blocks) == 1

        elements = action_blocks[0]["elements"]
        action_ids = [e["action_id"] for e in elements]
        assert "search_prev_disabled" in action_ids or "search_prev" in action_ids
        assert "search_page_indicator" in action_ids
        assert "search_next_disabled" in action_ids or "search_next" in action_ids
        assert "search_refresh" in action_ids

    def test_pagination_with_more_pages(self) -> None:
        """Test pagination when there are more pages."""
        # Create 8 sessions (more than one page)
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id="123.456",
        )
        results = SearchResults(
            query="test",
            filters=SearchFilters(),
            sort="recent",
            total=8,
            offset=0,
            limit=PAGE_SIZE,
            results=sessions[:PAGE_SIZE],
        )
        blocks = format_search_results(results, state)

        # Find actions block
        action_blocks = [b for b in blocks if b["type"] == "actions"]
        elements = action_blocks[0]["elements"]
        action_ids = [e["action_id"] for e in elements]

        # Next should be enabled since there are more results
        assert "search_next" in action_ids

    def test_summary_truncation(self) -> None:
        """Test that long summaries are truncated."""
        long_summary = "A" * 200
        session = make_session_info(summary=long_summary)
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[session],
            current_offset=0,
            message_id="123.456",
        )
        results = SearchResults(
            query="test",
            filters=SearchFilters(),
            sort="recent",
            total=1,
            offset=0,
            limit=PAGE_SIZE,
            results=[session],
        )
        blocks = format_search_results(results, state)

        # Find section with accessory
        section = next(b for b in blocks if b["type"] == "section" and "accessory" in b)
        # Summary should be truncated with ...
        assert "..." in section["text"]["text"]


class TestFormatEmptyResults:
    """Tests for format_empty_results."""

    def test_with_query(self) -> None:
        """Test empty results with a query."""
        blocks = format_empty_results("quantum computing")
        assert len(blocks) == 2
        assert 'No sessions found matching "quantum computing"' in blocks[0]["text"]["text"]
        assert "Suggestions:" in blocks[1]["text"]["text"]

    def test_without_query(self) -> None:
        """Test empty results without a query."""
        blocks = format_empty_results("")
        assert "No sessions found" in blocks[0]["text"]["text"]


class TestFormatRateLimited:
    """Tests for format_rate_limited."""

    def test_format(self) -> None:
        """Test rate limit message formatting."""
        blocks = format_rate_limited(10)
        assert len(blocks) == 1
        assert "Too many searches" in blocks[0]["text"]["text"]
        assert "10 seconds" in blocks[0]["text"]["text"]


class TestFormatWatchConfirmation:
    """Tests for format_watch_confirmation."""

    def test_format(self, sample_sessions: list[SessionInfo]) -> None:
        """Test watch confirmation formatting."""
        blocks = format_watch_confirmation(sample_sessions[0])
        assert len(blocks) == 1
        assert "Now watching" in blocks[0]["text"]["text"]
        assert "Fix authentication bug" in blocks[0]["text"]["text"]
        assert "trello-clone" in blocks[0]["text"]["text"]


class TestFormatPreview:
    """Tests for format_preview."""

    def test_basic_preview(self, sample_sessions: list[SessionInfo]) -> None:
        """Test basic preview formatting."""
        events = [
            {"type": "user", "text": "Can you fix the login bug?"},
            {"type": "assistant", "text": "I'll investigate the authentication flow."},
            {"type": "tool_call", "tool_name": "Read", "label": "src/auth.ts", "result_preview": "150 lines"},
        ]
        blocks = format_preview(sample_sessions[0], events)

        # Should have header
        assert "Preview" in blocks[0]["text"]["text"]

        # Should have event blocks
        texts = " ".join(b.get("text", {}).get("text", "") for b in blocks if b["type"] == "section")
        assert "User" in texts
        assert "Assistant" in texts
        assert "Read" in texts

    def test_empty_events(self, sample_sessions: list[SessionInfo]) -> None:
        """Test preview with no events."""
        blocks = format_preview(sample_sessions[0], [])
        # Should still have header and divider
        assert blocks[0]["type"] == "section"
        assert "Preview" in blocks[0]["text"]["text"]


class TestFormatError:
    """Tests for format_error."""

    def test_format(self) -> None:
        """Test error message formatting."""
        blocks = format_error("Something went wrong")
        assert len(blocks) == 1
        assert "Something went wrong" in blocks[0]["text"]["text"]


# ---------------------------------------------------------------------------
# Tests for SlackCommandHandler
# ---------------------------------------------------------------------------


class TestHandleSearchRateLimiting:
    """Tests for rate limiting in handle_search."""

    @pytest.mark.asyncio
    async def test_rate_limited_returns_immediate_response(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test that rate limited requests return an immediate response."""
        # Exhaust rate limit
        for _ in range(10):
            handler.rate_limiter.check("slack:U123")

        result = await handler.handle_search(
            command="/search",
            text="auth bug",
            user_id="U123",
            channel_id="C456",
            response_url="https://hooks.slack.com/...",
        )

        assert result is not None
        assert result["response_type"] == "ephemeral"
        assert "Too many searches" in result["text"]

    @pytest.mark.asyncio
    async def test_allowed_request_returns_none(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test that allowed requests return None for async processing."""
        with patch.object(handler, "_process_search_and_respond", new_callable=AsyncMock):
            result = await handler.handle_search(
                command="/search",
                text="auth bug",
                user_id="U123",
                channel_id="C456",
                response_url="https://hooks.slack.com/...",
            )

        assert result is None


class TestHandleWatch:
    """Tests for handle_watch."""

    @pytest.mark.asyncio
    async def test_watch_with_valid_index(
        self,
        handler: SlackCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test watch button with valid session index."""
        # Set up search state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id="123.456",
        )
        search_state_manager.save("slack:C456", state)

        # Set up attach callback
        attach_callback = AsyncMock()
        handler.attach_callback = attach_callback

        payload = {
            "channel": {"id": "C456"},
            "user": {"id": "U123"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        await handler.handle_watch("session_menu:0", "watch:0", payload)

        # Should have called attach callback
        attach_callback.assert_called_once()
        call_kwargs = attach_callback.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-001"
        assert call_kwargs["destination"]["type"] == "slack"
        assert call_kwargs["destination"]["channel"] == "C456"

    @pytest.mark.asyncio
    async def test_watch_with_expired_state(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test watch button when search state has expired."""
        payload = {
            "channel": {"id": "C456"},
            "user": {"id": "U123"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        # Mock _respond_ephemeral
        with patch.object(handler, "_respond_ephemeral", new_callable=AsyncMock) as mock_respond:
            await handler.handle_watch("session_menu:0", "watch:0", payload)
            mock_respond.assert_called_once()
            assert "expired" in mock_respond.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_watch_with_invalid_value(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test watch button with invalid value."""
        payload = {"channel": {"id": "C456"}}

        # Should not raise
        await handler.handle_watch("session_menu:0", "invalid", payload)
        await handler.handle_watch("session_menu:0", None, payload)


class TestHandlePreview:
    """Tests for handle_preview."""

    @pytest.mark.asyncio
    async def test_preview_with_valid_index(
        self,
        handler: SlackCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
        mock_slack_publisher: MagicMock,
    ) -> None:
        """Test preview button with valid session index."""
        # Set up search state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id="123.456",
        )
        search_state_manager.save("slack:C456", state)

        payload = {
            "channel": {"id": "C456"},
            "user": {"id": "U123"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        await handler.handle_preview("session_menu:0", "preview:0", payload)

        # Should have called chat_postMessage with thread_ts
        mock_slack_publisher._client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_publisher._client.chat_postMessage.call_args.kwargs
        assert call_kwargs["thread_ts"] == "123.456"

    @pytest.mark.asyncio
    async def test_preview_with_expired_state(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test preview button when search state has expired."""
        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        with patch.object(handler, "_respond_ephemeral", new_callable=AsyncMock) as mock_respond:
            await handler.handle_preview("session_menu:0", "preview:0", payload)
            mock_respond.assert_called_once()
            assert "expired" in mock_respond.call_args.args[1].lower()


class TestHandlePagination:
    """Tests for handle_pagination."""

    @pytest.mark.asyncio
    async def test_next_page(
        self,
        handler: SlackCommandHandler,
        search_state_manager: SearchStateManager,
        mock_slack_publisher: MagicMock,
    ) -> None:
        """Test next page button."""
        # Create 8 sessions (more than one page)
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id="123.456",
        )
        search_state_manager.save("slack:C456", state)

        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        await handler.handle_pagination("search_next", None, payload)

        # Should have updated offset
        updated_state = search_state_manager.get("slack:C456")
        assert updated_state is not None
        assert updated_state.current_offset == PAGE_SIZE

        # Should have called update_message
        mock_slack_publisher.update_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_prev_page(
        self,
        handler: SlackCommandHandler,
        search_state_manager: SearchStateManager,
        mock_slack_publisher: MagicMock,
    ) -> None:
        """Test prev page button."""
        # Create 8 sessions and start on page 2
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=PAGE_SIZE,  # Start on page 2
            message_id="123.456",
        )
        search_state_manager.save("slack:C456", state)

        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
        }

        await handler.handle_pagination("search_prev", None, payload)

        # Should have updated offset back to 0
        updated_state = search_state_manager.get("slack:C456")
        assert updated_state is not None
        assert updated_state.current_offset == 0

    @pytest.mark.asyncio
    async def test_disabled_buttons_ignored(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test that disabled pagination buttons are ignored."""
        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
        }

        # These should not raise or do anything
        await handler.handle_pagination("search_prev_disabled", None, payload)
        await handler.handle_pagination("search_next_disabled", None, payload)
        await handler.handle_pagination("search_page_indicator", None, payload)

    @pytest.mark.asyncio
    async def test_pagination_with_expired_state(
        self, handler: SlackCommandHandler
    ) -> None:
        """Test pagination when search state has expired."""
        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
            "response_url": "https://hooks.slack.com/...",
        }

        with patch.object(handler, "_respond_ephemeral", new_callable=AsyncMock) as mock_respond:
            await handler.handle_pagination("search_next", None, payload)
            mock_respond.assert_called_once()
            assert "expired" in mock_respond.call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_refresh_reruns_search(
        self,
        handler: SlackCommandHandler,
        search_state_manager: SearchStateManager,
        mock_search_engine: MagicMock,
        mock_slack_publisher: MagicMock,
        sample_sessions: list[SessionInfo],
    ) -> None:
        """Test that refresh button re-runs the search."""
        # Set up initial state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id="123.456",
        )
        search_state_manager.save("slack:C456", state)

        # Mock search engine response
        from claude_session_player.watcher.search import SearchParams

        mock_search_engine.parse_query.return_value = SearchParams(
            query="auth", terms=["auth"], filters=SearchFilters()
        )
        mock_search_engine.search.return_value = SearchResults(
            query="auth",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )

        payload = {
            "channel": {"id": "C456"},
            "message": {"ts": "123.456"},
        }

        await handler.handle_pagination("search_refresh", None, payload)

        # Should have called search
        mock_search_engine.search.assert_called_once()

        # Should have updated message
        mock_slack_publisher.update_message.assert_called()


class TestIntegration:
    """Integration tests for full search flow."""

    @pytest.mark.asyncio
    async def test_full_search_flow(
        self,
        handler: SlackCommandHandler,
        mock_search_engine: MagicMock,
        search_state_manager: SearchStateManager,
        sample_sessions: list[SessionInfo],
    ) -> None:
        """Test the full search command flow."""
        from claude_session_player.watcher.search import SearchParams

        # Mock search engine
        mock_search_engine.parse_query.return_value = SearchParams(
            query="auth bug", terms=["auth", "bug"], filters=SearchFilters()
        )
        mock_search_engine.search.return_value = SearchResults(
            query="auth bug",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )

        # Mock HTTP session for response_url
        mock_response = MagicMock()
        mock_response.status = 200

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.post = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()))
            mock_session_class.return_value = mock_session
            handler._http_session = mock_session

            # Process search directly
            await handler._process_search_and_respond(
                "auth bug", "C456", "https://hooks.slack.com/..."
            )

            # Should have posted to response_url
            mock_session.post.assert_called_once()
            call_args = mock_session.post.call_args
            assert call_args.args[0] == "https://hooks.slack.com/..."

            # Should have saved state
            state = search_state_manager.get("slack:C456")
            assert state is not None
            assert state.query == "auth bug"
            assert len(state.results) == 3


class TestCleanup:
    """Tests for handler cleanup."""

    @pytest.mark.asyncio
    async def test_close_http_session(self, handler: SlackCommandHandler) -> None:
        """Test that close() closes the HTTP session."""
        # Create a mock session
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        handler._http_session = mock_session

        await handler.close()

        mock_session.close.assert_called_once()
        assert handler._http_session is None

    @pytest.mark.asyncio
    async def test_close_when_no_session(self, handler: SlackCommandHandler) -> None:
        """Test that close() works when no session exists."""
        handler._http_session = None
        await handler.close()  # Should not raise
