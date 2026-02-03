"""Tests for the TelegramCommandHandler module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.indexer import SessionInfo
from claude_session_player.watcher.rate_limit import RateLimiter
from claude_session_player.watcher.search import SearchEngine, SearchFilters, SearchResults
from claude_session_player.watcher.search_state import SearchState, SearchStateManager
from claude_session_player.watcher.telegram_commands import (
    PAGE_SIZE,
    TelegramCommandHandler,
    _build_search_keyboard,
    _escape_markdown,
    _format_date,
    _format_duration,
    _format_file_size,
    format_empty_results_telegram,
    format_error_telegram,
    format_expired_state_telegram,
    format_preview_telegram,
    format_rate_limited_telegram,
    format_search_results_telegram,
    format_watch_confirmation_telegram,
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
def mock_telegram_publisher() -> MagicMock:
    """Create a mock TelegramPublisher."""
    publisher = MagicMock()
    publisher.send_message = AsyncMock(return_value=123)
    publisher.edit_message = AsyncMock(return_value=True)
    publisher.validate = AsyncMock()
    publisher._bot = MagicMock()
    publisher._bot.send_message = AsyncMock(return_value=MagicMock(message_id=123))
    publisher._bot.edit_message_text = AsyncMock()
    return publisher


@pytest.fixture
def handler(
    mock_search_engine: MagicMock,
    search_state_manager: SearchStateManager,
    rate_limiter: RateLimiter,
    mock_telegram_publisher: MagicMock,
) -> TelegramCommandHandler:
    """Create a TelegramCommandHandler."""
    return TelegramCommandHandler(
        search_engine=mock_search_engine,
        search_state_manager=search_state_manager,
        rate_limiter=rate_limiter,
        telegram_publisher=mock_telegram_publisher,
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
        message_id=123,
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests for utility functions
# ---------------------------------------------------------------------------


class TestEscapeMarkdown:
    """Tests for _escape_markdown."""

    def test_underscore(self) -> None:
        """Test escaping underscore."""
        assert _escape_markdown("foo_bar") == r"foo\_bar"

    def test_asterisk(self) -> None:
        """Test escaping asterisk."""
        assert _escape_markdown("foo*bar") == r"foo\*bar"

    def test_backtick(self) -> None:
        """Test escaping backtick."""
        assert _escape_markdown("foo`bar") == r"foo\`bar"

    def test_bracket(self) -> None:
        """Test escaping bracket."""
        assert _escape_markdown("foo[bar") == r"foo\[bar"

    def test_combined(self) -> None:
        """Test escaping all special characters."""
        assert _escape_markdown("_*`[") == r"\_\*\`\["


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


# ---------------------------------------------------------------------------
# Tests for Markdown formatting
# ---------------------------------------------------------------------------


class TestFormatSearchResultsTelegram:
    """Tests for format_search_results_telegram."""

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
        text, keyboard = format_search_results_telegram(results, search_state)

        # Check header
        assert "Found 3 sessions" in text
        assert 'matching "auth bug"' in text

        # Check results are numbered
        assert "1. 📁" in text
        assert "2. 📁" in text
        assert "3. 📁" in text

        # Check project names
        assert "trello-clone" in text
        assert "api-server" in text

        # Check page info
        assert "Page 1 of 1" in text

    def test_single_result_grammar(self, sample_sessions: list[SessionInfo]) -> None:
        """Test that single result uses singular 'session'."""
        single_session = [sample_sessions[0]]
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=single_session,
            current_offset=0,
            message_id=123,
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
        text, _ = format_search_results_telegram(results, state)

        # Should say "session" not "sessions"
        assert "Found 1 session" in text
        assert "sessions" not in text

    def test_keyboard_structure(
        self, sample_sessions: list[SessionInfo], search_state: SearchState
    ) -> None:
        """Test inline keyboard structure."""
        results = SearchResults(
            query="auth bug",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=PAGE_SIZE,
            results=sample_sessions,
        )
        _, keyboard = format_search_results_telegram(results, search_state)

        # Should have 3 rows: watch, preview, navigation
        assert len(keyboard) == 3

        # Row 1: Watch buttons (one per result)
        assert len(keyboard[0]) == 3
        assert keyboard[0][0]["callback_data"] == "w:0"
        assert keyboard[0][1]["callback_data"] == "w:1"
        assert keyboard[0][2]["callback_data"] == "w:2"

        # Row 2: Preview buttons
        assert len(keyboard[1]) == 3
        assert keyboard[1][0]["callback_data"] == "p:0"
        assert keyboard[1][1]["callback_data"] == "p:1"
        assert keyboard[1][2]["callback_data"] == "p:2"

        # Row 3: Navigation
        nav_row = keyboard[2]
        callbacks = [btn["callback_data"] for btn in nav_row]
        assert "noop" in callbacks  # prev disabled or page indicator
        assert "s:r" in callbacks  # refresh

    def test_pagination_with_more_pages(self) -> None:
        """Test pagination when there are more pages."""
        # Create 8 sessions (more than one page)
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id=123,
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
        text, keyboard = format_search_results_telegram(results, state)

        # Check page info shows multiple pages
        assert "Page 1 of 2" in text

        # Check next button is enabled
        nav_row = keyboard[2]
        callbacks = [btn["callback_data"] for btn in nav_row]
        assert "s:n" in callbacks  # next enabled

    def test_summary_truncation(self) -> None:
        """Test that long summaries are truncated."""
        long_summary = "A" * 200
        session = make_session_info(summary=long_summary)
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=[session],
            current_offset=0,
            message_id=123,
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
        text, _ = format_search_results_telegram(results, state)

        # Summary should be truncated with ...
        assert "..." in text


class TestBuildSearchKeyboard:
    """Tests for _build_search_keyboard."""

    def test_watch_buttons(self, sample_sessions: list[SessionInfo]) -> None:
        """Test watch button generation."""
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        keyboard = _build_search_keyboard(sample_sessions, state, 1, 1)

        # First row should be watch buttons
        watch_row = keyboard[0]
        assert len(watch_row) == 3
        for i, btn in enumerate(watch_row):
            assert btn["text"] == f"👁 {i + 1}"
            assert btn["callback_data"] == f"w:{i}"

    def test_preview_buttons(self, sample_sessions: list[SessionInfo]) -> None:
        """Test preview button generation."""
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        keyboard = _build_search_keyboard(sample_sessions, state, 1, 1)

        # Second row should be preview buttons
        preview_row = keyboard[1]
        assert len(preview_row) == 3
        for i, btn in enumerate(preview_row):
            assert btn["text"] == f"📋 {i + 1}"
            assert btn["callback_data"] == f"p:{i}"

    def test_navigation_row(self, sample_sessions: list[SessionInfo]) -> None:
        """Test navigation row structure."""
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        keyboard = _build_search_keyboard(sample_sessions, state, 1, 1)

        # Third row should be navigation
        nav_row = keyboard[2]
        assert len(nav_row) == 4  # prev, page, next, refresh

        # Check button types
        assert nav_row[0]["text"] == "◀️"  # prev
        assert "1/1" in nav_row[1]["text"]  # page indicator
        assert nav_row[2]["text"] == "▶️"  # next
        assert nav_row[3]["text"] == "🔄"  # refresh
        assert nav_row[3]["callback_data"] == "s:r"


class TestFormatEmptyResultsTelegram:
    """Tests for format_empty_results_telegram."""

    def test_with_query(self) -> None:
        """Test empty results with a query."""
        text, keyboard = format_empty_results_telegram("quantum computing")
        assert "No sessions found" in text
        assert "quantum computing" in text
        assert "Broader search terms" in text

    def test_without_query(self) -> None:
        """Test empty results without a query."""
        text, keyboard = format_empty_results_telegram("")
        assert "No sessions found" in text
        assert "Browse Projects" in keyboard[0][0]["text"]


class TestFormatRateLimitedTelegram:
    """Tests for format_rate_limited_telegram."""

    def test_format(self) -> None:
        """Test rate limit message formatting."""
        text = format_rate_limited_telegram(10)
        assert "Please wait 10 seconds" in text


class TestFormatWatchConfirmationTelegram:
    """Tests for format_watch_confirmation_telegram."""

    def test_format(self, sample_sessions: list[SessionInfo]) -> None:
        """Test watch confirmation formatting."""
        text, keyboard = format_watch_confirmation_telegram(sample_sessions[0])
        assert "Now watching" in text
        assert "Fix authentication bug" in text
        assert "trello-clone" in text
        assert "events will appear" in text
        assert "Stop Watching" in keyboard[0][0]["text"]


class TestFormatPreviewTelegram:
    """Tests for format_preview_telegram."""

    def test_basic_preview(self, sample_sessions: list[SessionInfo]) -> None:
        """Test basic preview formatting."""
        events = [
            {"type": "user", "text": "Can you fix the login bug?"},
            {"type": "assistant", "text": "I'll investigate the authentication flow."},
            {"type": "tool_call", "tool_name": "Read", "label": "src/auth.ts", "result_preview": "150 lines"},
        ]
        text = format_preview_telegram(sample_sessions[0], events)

        # Check header
        assert "Preview" in text
        assert "last 3 events" in text

        # Check events
        assert "User" in text
        assert "Assistant" in text
        assert "Read" in text

    def test_empty_events(self, sample_sessions: list[SessionInfo]) -> None:
        """Test preview with no events."""
        text = format_preview_telegram(sample_sessions[0], [])
        assert "Preview" in text
        assert "last 0 events" in text


class TestFormatErrorTelegram:
    """Tests for format_error_telegram."""

    def test_format(self) -> None:
        """Test error message formatting."""
        text = format_error_telegram("Something went wrong")
        assert "Something went wrong" in text
        assert "⚠️" in text


class TestFormatExpiredStateTelegram:
    """Tests for format_expired_state_telegram."""

    def test_format(self) -> None:
        """Test expired state message."""
        text = format_expired_state_telegram()
        assert "Search expired" in text
        assert "search again" in text


# ---------------------------------------------------------------------------
# Tests for TelegramCommandHandler
# ---------------------------------------------------------------------------


class TestHandleSearchRateLimiting:
    """Tests for rate limiting in handle_search."""

    @pytest.mark.asyncio
    async def test_rate_limited_sends_message(
        self, handler: TelegramCommandHandler, mock_telegram_publisher: MagicMock
    ) -> None:
        """Test that rate limited requests send a rate limit message."""
        # Exhaust rate limit
        for _ in range(10):
            handler.rate_limiter.check("telegram:123456")

        await handler.handle_search("auth bug", 123456)

        # Should have sent rate limit message
        mock_telegram_publisher.send_message.assert_called_once()
        call_args = mock_telegram_publisher.send_message.call_args
        assert "wait" in call_args.args[1].lower()

    @pytest.mark.asyncio
    async def test_allowed_request_processes_search(
        self, handler: TelegramCommandHandler, mock_search_engine: MagicMock, sample_sessions: list[SessionInfo]
    ) -> None:
        """Test that allowed requests process the search."""
        from claude_session_player.watcher.search import SearchParams

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

        with patch.object(handler, "_send_message_with_keyboard", new_callable=AsyncMock, return_value=123):
            await handler.handle_search("auth bug", 123456)

        # Should have called search
        mock_search_engine.search.assert_called()


class TestHandleCallback:
    """Tests for handle_callback."""

    @pytest.mark.asyncio
    async def test_noop_returns_none(self, handler: TelegramCommandHandler) -> None:
        """Test that noop callback returns None."""
        result = await handler.handle_callback("noop", 123456, 789)
        assert result is None

    @pytest.mark.asyncio
    async def test_watch_callback(
        self,
        handler: TelegramCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test watch callback handling."""
        # Set up search state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        # Set up attach callback
        attach_callback = AsyncMock()
        handler.attach_callback = attach_callback

        with patch.object(handler, "_send_message_with_keyboard", new_callable=AsyncMock, return_value=456):
            result = await handler.handle_callback("w:0", 123456, 789)

        # Should have called attach callback
        attach_callback.assert_called_once()
        call_kwargs = attach_callback.call_args.kwargs
        assert call_kwargs["session_id"] == "sess-001"
        assert call_kwargs["destination"]["type"] == "telegram"
        assert call_kwargs["destination"]["chat_id"] == "123456"

        assert "watching" in result.lower() or "trello-clone" in result

    @pytest.mark.asyncio
    async def test_preview_callback(
        self,
        handler: TelegramCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test preview callback handling."""
        # Set up search state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_send_reply", new_callable=AsyncMock, return_value=456):
            result = await handler.handle_callback("p:0", 123456, 789)

        assert "Preview" in result

    @pytest.mark.asyncio
    async def test_navigation_next(
        self,
        handler: TelegramCommandHandler,
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test next page callback."""
        # Create 8 sessions (more than one page)
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            result = await handler.handle_callback("s:n", 123456, 123)

        # Should have updated offset
        updated_state = search_state_manager.get("telegram:123456")
        assert updated_state is not None
        assert updated_state.current_offset == PAGE_SIZE
        assert "Next" in result

    @pytest.mark.asyncio
    async def test_navigation_prev(
        self,
        handler: TelegramCommandHandler,
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test prev page callback."""
        # Create 8 sessions and start on page 2
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(8)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=PAGE_SIZE,  # Start on page 2
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            result = await handler.handle_callback("s:p", 123456, 123)

        # Should have updated offset back to 0
        updated_state = search_state_manager.get("telegram:123456")
        assert updated_state is not None
        assert updated_state.current_offset == 0
        assert "Previous" in result

    @pytest.mark.asyncio
    async def test_navigation_refresh(
        self,
        handler: TelegramCommandHandler,
        mock_search_engine: MagicMock,
        search_state_manager: SearchStateManager,
        sample_sessions: list[SessionInfo],
    ) -> None:
        """Test refresh callback."""
        from claude_session_player.watcher.search import SearchParams

        # Set up initial state
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        # Mock search engine response
        mock_search_engine.parse_query.return_value = SearchParams(
            query="auth", terms=["auth"], filters=SearchFilters()
        )
        mock_search_engine.search.return_value = SearchResults(
            query="auth",
            filters=SearchFilters(),
            sort="recent",
            total=3,
            offset=0,
            limit=1000,
            results=sample_sessions,
        )

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            result = await handler.handle_callback("s:r", 123456, 123)

        # Should have called search
        mock_search_engine.search.assert_called_once()
        assert "Refresh" in result


class TestHandleWatch:
    """Tests for _handle_watch."""

    @pytest.mark.asyncio
    async def test_watch_with_valid_index(
        self,
        handler: TelegramCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test watch with valid session index."""
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        attach_callback = AsyncMock()
        handler.attach_callback = attach_callback

        with patch.object(handler, "_send_message_with_keyboard", new_callable=AsyncMock, return_value=456):
            result = await handler._handle_watch("123456", 789, 0)

        attach_callback.assert_called_once()
        assert "trello-clone" in result

    @pytest.mark.asyncio
    async def test_watch_with_expired_state(
        self, handler: TelegramCommandHandler, mock_telegram_publisher: MagicMock
    ) -> None:
        """Test watch when search state has expired."""
        result = await handler._handle_watch("123456", 789, 0)

        mock_telegram_publisher.send_message.assert_called_once()
        assert "expired" in result.lower()

    @pytest.mark.asyncio
    async def test_watch_with_invalid_index(
        self,
        handler: TelegramCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test watch with invalid session index."""
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        result = await handler._handle_watch("123456", 789, 10)  # Index out of range
        assert "not found" in result.lower()


class TestHandlePreview:
    """Tests for _handle_preview."""

    @pytest.mark.asyncio
    async def test_preview_with_valid_index(
        self,
        handler: TelegramCommandHandler,
        sample_sessions: list[SessionInfo],
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test preview with valid session index."""
        state = SearchState(
            query="auth",
            filters=SearchFilters(),
            results=sample_sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_send_reply", new_callable=AsyncMock, return_value=456):
            result = await handler._handle_preview("123456", 789, 0)

        assert "Preview" in result

    @pytest.mark.asyncio
    async def test_preview_with_expired_state(
        self, handler: TelegramCommandHandler, mock_telegram_publisher: MagicMock
    ) -> None:
        """Test preview when search state has expired."""
        result = await handler._handle_preview("123456", 789, 0)

        mock_telegram_publisher.send_message.assert_called_once()
        assert "expired" in result.lower()


class TestHandlePagination:
    """Tests for pagination callbacks."""

    @pytest.mark.asyncio
    async def test_next_page_updates_offset(
        self,
        handler: TelegramCommandHandler,
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test next page updates offset correctly."""
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(10)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            await handler._handle_next_page("123456", 123)

        updated = search_state_manager.get("telegram:123456")
        assert updated.current_offset == PAGE_SIZE

    @pytest.mark.asyncio
    async def test_prev_page_updates_offset(
        self,
        handler: TelegramCommandHandler,
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test prev page updates offset correctly."""
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(10)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=PAGE_SIZE,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            await handler._handle_prev_page("123456", 123)

        updated = search_state_manager.get("telegram:123456")
        assert updated.current_offset == 0

    @pytest.mark.asyncio
    async def test_prev_page_at_start_stays_at_zero(
        self,
        handler: TelegramCommandHandler,
        search_state_manager: SearchStateManager,
    ) -> None:
        """Test prev page at start doesn't go negative."""
        sessions = [make_session_info(session_id=f"sess-{i:03d}") for i in range(10)]
        state = SearchState(
            query="test",
            filters=SearchFilters(),
            results=sessions,
            current_offset=0,
            message_id=123,
        )
        search_state_manager.save("telegram:123456", state)

        with patch.object(handler, "_update_search_message", new_callable=AsyncMock):
            await handler._handle_prev_page("123456", 123)

        updated = search_state_manager.get("telegram:123456")
        assert updated.current_offset == 0

    @pytest.mark.asyncio
    async def test_pagination_with_expired_state(
        self, handler: TelegramCommandHandler, mock_telegram_publisher: MagicMock
    ) -> None:
        """Test pagination when search state has expired."""
        result = await handler._handle_next_page("123456", 123)

        mock_telegram_publisher.send_message.assert_called_once()
        assert "expired" in result.lower()


class TestIntegration:
    """Integration tests for full search flow."""

    @pytest.mark.asyncio
    async def test_full_search_flow(
        self,
        handler: TelegramCommandHandler,
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
            limit=1000,
            results=sample_sessions,
        )

        with patch.object(handler, "_send_message_with_keyboard", new_callable=AsyncMock, return_value=123):
            await handler.handle_search("auth bug", 123456)

        # Should have saved state
        state = search_state_manager.get("telegram:123456")
        assert state is not None
        assert state.query == "auth bug"
        assert len(state.results) == 3


class TestCallbackDataParsing:
    """Tests for callback data parsing."""

    @pytest.mark.asyncio
    async def test_parse_watch_callback(self, handler: TelegramCommandHandler) -> None:
        """Test parsing watch callback data."""
        mock_handle_watch = AsyncMock(return_value="result")
        with patch.object(handler, "_handle_watch", mock_handle_watch):
            result = await handler.handle_callback("w:0", 123456, 789)
        mock_handle_watch.assert_called_once_with("123456", 789, 0)

    @pytest.mark.asyncio
    async def test_parse_preview_callback(self, handler: TelegramCommandHandler) -> None:
        """Test parsing preview callback data."""
        mock_handle_preview = AsyncMock(return_value="result")
        with patch.object(handler, "_handle_preview", mock_handle_preview):
            result = await handler.handle_callback("p:2", 123456, 789)
        mock_handle_preview.assert_called_once_with("123456", 789, 2)

    @pytest.mark.asyncio
    async def test_parse_next_page_callback(self, handler: TelegramCommandHandler) -> None:
        """Test parsing next page callback data."""
        mock_handle_next = AsyncMock(return_value="result")
        with patch.object(handler, "_handle_next_page", mock_handle_next):
            result = await handler.handle_callback("s:n", 123456, 789)
        mock_handle_next.assert_called_once_with("123456", 789)

    @pytest.mark.asyncio
    async def test_parse_prev_page_callback(self, handler: TelegramCommandHandler) -> None:
        """Test parsing prev page callback data."""
        mock_handle_prev = AsyncMock(return_value="result")
        with patch.object(handler, "_handle_prev_page", mock_handle_prev):
            result = await handler.handle_callback("s:p", 123456, 789)
        mock_handle_prev.assert_called_once_with("123456", 789)

    @pytest.mark.asyncio
    async def test_parse_refresh_callback(self, handler: TelegramCommandHandler) -> None:
        """Test parsing refresh callback data."""
        mock_handle_refresh = AsyncMock(return_value="result")
        with patch.object(handler, "_handle_refresh", mock_handle_refresh):
            result = await handler.handle_callback("s:r", 123456, 789)
        mock_handle_refresh.assert_called_once_with("123456", 789)

    @pytest.mark.asyncio
    async def test_invalid_callback_data(self, handler: TelegramCommandHandler) -> None:
        """Test handling invalid callback data."""
        # Empty index (parts[1] is empty string)
        result = await handler.handle_callback("w:", 123456, 789)
        assert result == "Invalid index"  # Empty string fails int conversion

        # Non-numeric index
        result = await handler.handle_callback("w:abc", 123456, 789)
        assert result == "Invalid index"

        # Missing index entirely (no colon separator)
        result = await handler.handle_callback("w", 123456, 789)
        assert result == "Invalid action"

        # Unknown action
        result = await handler.handle_callback("x:0", 123456, 789)
        assert result is None
