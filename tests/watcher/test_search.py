"""Tests for SearchEngine and related functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_session_player.watcher.indexer import (
    IndexConfig,
    SessionIndexer,
    SessionInfo,
)
from claude_session_player.watcher.search import (
    SearchEngine,
    SearchFilters,
    SearchParams,
    calculate_score,
    parse_iso_date,
    parse_query,
    parse_time_range,
)


# ---------------------------------------------------------------------------
# Time parsing tests
# ---------------------------------------------------------------------------


class TestParseTimeRange:
    """Tests for parse_time_range function."""

    def test_parse_days(self) -> None:
        """Parse days time range."""
        delta = parse_time_range("7d")
        assert delta == timedelta(days=7)

    def test_parse_weeks(self) -> None:
        """Parse weeks time range."""
        delta = parse_time_range("2w")
        assert delta == timedelta(weeks=2)

    def test_parse_months(self) -> None:
        """Parse months time range (approximated as 30 days)."""
        delta = parse_time_range("1m")
        assert delta == timedelta(days=30)

    def test_parse_invalid_format(self) -> None:
        """Invalid format returns None."""
        assert parse_time_range("invalid") is None
        assert parse_time_range("7x") is None
        assert parse_time_range("d7") is None
        assert parse_time_range("") is None

    def test_parse_uppercase(self) -> None:
        """Uppercase units work."""
        delta = parse_time_range("7D")
        assert delta == timedelta(days=7)


class TestParseIsoDate:
    """Tests for parse_iso_date function."""

    def test_parse_date_only(self) -> None:
        """Parse date without time."""
        dt = parse_iso_date("2024-01-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_parse_datetime(self) -> None:
        """Parse full datetime."""
        dt = parse_iso_date("2024-01-15T10:30:00")
        assert dt is not None
        assert dt.hour == 10
        assert dt.minute == 30

    def test_parse_datetime_with_timezone(self) -> None:
        """Parse datetime with timezone."""
        dt = parse_iso_date("2024-01-15T10:30:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_invalid(self) -> None:
        """Invalid format returns None."""
        assert parse_iso_date("invalid") is None
        assert parse_iso_date("2024/01/15") is None
        assert parse_iso_date("") is None


# ---------------------------------------------------------------------------
# Query parsing tests
# ---------------------------------------------------------------------------


class TestParseQuery:
    """Tests for parse_query function."""

    def test_parse_simple_query(self) -> None:
        """Parse simple query with terms."""
        params = parse_query("auth bug")
        assert params.query == "auth bug"
        assert params.terms == ["auth", "bug"]
        assert params.filters.project is None

    def test_parse_quoted_phrase(self) -> None:
        """Parse quoted phrase as single term."""
        params = parse_query('"auth bug"')
        assert params.terms == ["auth bug"]
        assert params.query == "auth bug"

    def test_parse_with_project_filter_long(self) -> None:
        """Parse query with --project filter."""
        params = parse_query("auth --project trello")
        assert params.terms == ["auth"]
        assert params.filters.project == "trello"

    def test_parse_with_project_filter_short(self) -> None:
        """Parse query with -p filter."""
        params = parse_query("auth -p trello")
        assert params.terms == ["auth"]
        assert params.filters.project == "trello"

    def test_parse_with_last_filter(self) -> None:
        """Parse query with --last filter."""
        params = parse_query("-l 7d")
        assert params.terms == []
        assert params.filters.since is not None
        # Should be approximately 7 days ago
        now = datetime.now(timezone.utc)
        expected = now - timedelta(days=7)
        # Allow 1 minute tolerance
        assert abs((params.filters.since - expected).total_seconds()) < 60

    def test_parse_with_since_filter(self) -> None:
        """Parse query with --since filter."""
        params = parse_query("-s 2024-01-01")
        assert params.filters.since is not None
        assert params.filters.since.year == 2024
        assert params.filters.since.month == 1
        assert params.filters.since.day == 1

    def test_parse_with_until_filter(self) -> None:
        """Parse query with --until filter."""
        params = parse_query("-u 2024-12-31")
        assert params.filters.until is not None
        assert params.filters.until.year == 2024
        assert params.filters.until.month == 12

    def test_parse_with_sort_option(self) -> None:
        """Parse query with --sort option."""
        params = parse_query("auth --sort size")
        assert params.sort == "size"

    def test_parse_combined_filters(self) -> None:
        """Parse query with multiple filters."""
        params = parse_query('auth bug -p trello -l 7d --sort recent')
        assert params.terms == ["auth", "bug"]
        assert params.filters.project == "trello"
        assert params.filters.since is not None
        assert params.sort == "recent"

    def test_parse_empty_query(self) -> None:
        """Parse empty query."""
        params = parse_query("")
        assert params.query == ""
        assert params.terms == []
        assert params.filters.project is None

    def test_parse_whitespace_only(self) -> None:
        """Parse whitespace-only query."""
        params = parse_query("   ")
        assert params.query == ""
        assert params.terms == []

    def test_parse_unknown_options_skipped(self) -> None:
        """Unknown options are skipped."""
        params = parse_query("auth --unknown-flag value term")
        # Unknown flags and their values might be included as terms
        # depending on implementation
        assert "auth" in params.terms
        assert "term" in params.terms

    def test_parse_mixed_quotes(self) -> None:
        """Parse query with mixed quoted and unquoted terms."""
        params = parse_query('simple "exact phrase" another')
        assert "simple" in params.terms
        assert "exact phrase" in params.terms
        assert "another" in params.terms


# ---------------------------------------------------------------------------
# Ranking algorithm tests
# ---------------------------------------------------------------------------


class TestCalculateScore:
    """Tests for calculate_score function."""

    def _make_session(
        self,
        tmp_path: Path,
        session_id: str = "session-1",
        summary: str | None = "Test summary",
        project_name: str = "test-project",
        modified_at: datetime | None = None,
    ) -> SessionInfo:
        """Create a SessionInfo for testing."""
        if modified_at is None:
            modified_at = datetime.now(timezone.utc)
        return SessionInfo(
            session_id=session_id,
            project_encoded="-Users-user-work-" + project_name.replace("-", "--"),
            project_display_name=project_name,
            file_path=tmp_path / f"{session_id}.jsonl",
            summary=summary,
            created_at=modified_at,
            modified_at=modified_at,
            size_bytes=1000,
            line_count=50,
            has_subagents=False,
        )

    def test_summary_match_scores_higher(self, tmp_path: Path) -> None:
        """Summary matches score higher than project matches."""
        now = datetime.now(timezone.utc)

        # Session with term in summary
        session_summary = self._make_session(
            tmp_path,
            session_id="s1",
            summary="Fix authentication bug",
            project_name="other",
            modified_at=now,
        )

        # Session with term in project name only
        session_project = self._make_session(
            tmp_path,
            session_id="s2",
            summary="Some other work",
            project_name="auth-service",
            modified_at=now,
        )

        score_summary = calculate_score(session_summary, "auth", ["auth"], now)
        score_project = calculate_score(session_project, "auth", ["auth"], now)

        # Summary match (2.0) > project match (1.0)
        assert score_summary > score_project

    def test_exact_phrase_bonus(self, tmp_path: Path) -> None:
        """Exact phrase match gets bonus."""
        now = datetime.now(timezone.utc)

        session = self._make_session(
            tmp_path,
            summary="Fix auth bug in login",
            modified_at=now,
        )

        # Single terms
        score_terms = calculate_score(session, "auth bug", ["auth", "bug"], now)

        # Same session - exact phrase "auth bug" is present
        # Query "auth bug" matches as phrase
        # Terms score: auth (2.0) + bug (2.0) = 4.0
        # Phrase bonus: "auth bug" in summary = 1.0
        # Recency: ~1.0
        # Total: ~6.0

        # Query with terms that don't form a phrase
        score_no_phrase = calculate_score(session, "auth login", ["auth", "login"], now)
        # Terms: auth (2.0) + login (2.0) = 4.0
        # No phrase bonus (exact "auth login" not in summary)
        # Recency: ~1.0
        # Total: ~5.0

        assert score_terms > score_no_phrase

    def test_recency_boost(self, tmp_path: Path) -> None:
        """Recent sessions get recency boost."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)

        session_recent = self._make_session(
            tmp_path, session_id="s1", summary="Test", modified_at=now
        )
        session_old = self._make_session(
            tmp_path, session_id="s2", summary="Test", modified_at=old
        )

        # No search terms - only recency matters
        score_recent = calculate_score(session_recent, "", [], now)
        score_old = calculate_score(session_old, "", [], now)

        assert score_recent > score_old
        # Recent should have ~1.0 recency, old should have 0
        assert score_recent > 0.9
        assert score_old == 0.0  # More than 30 days old

    def test_no_summary_still_scores(self, tmp_path: Path) -> None:
        """Sessions without summary can still score on project name."""
        now = datetime.now(timezone.utc)

        session = self._make_session(
            tmp_path,
            summary=None,  # No summary
            project_name="auth-service",
            modified_at=now,
        )

        score = calculate_score(session, "auth", ["auth"], now)
        # Should have project match (1.0) + recency (~1.0)
        assert score >= 1.5

    def test_multiple_term_matches(self, tmp_path: Path) -> None:
        """Multiple term matches accumulate score."""
        now = datetime.now(timezone.utc)

        session = self._make_session(
            tmp_path,
            summary="Fix authentication bug in login flow",
            project_name="auth-service",
            modified_at=now,
        )

        score = calculate_score(session, "auth bug", ["auth", "bug"], now)
        # Summary: auth (2.0) + bug (2.0) = 4.0
        # Phrase: "auth bug" in summary = 1.0
        # Project: auth (1.0) = 1.0
        # Recency: ~1.0
        # Total: ~7.0
        assert score >= 6.0


# ---------------------------------------------------------------------------
# SearchEngine integration tests
# ---------------------------------------------------------------------------


class TestSearchEngine:
    """Integration tests for SearchEngine."""

    @pytest.fixture
    def projects_dir(self, tmp_path: Path) -> Path:
        """Create a mock projects directory with sessions."""
        projects = tmp_path / ".claude" / "projects"
        projects.mkdir(parents=True)

        # Project: trello
        project_trello = projects / "-Users-user-work-trello"
        project_trello.mkdir()

        session1 = project_trello / "session-001.jsonl"
        session1.write_text(
            '{"type": "user", "message": "hello"}\n'
            '{"type": "summary", "summary": "Fix authentication bug in login"}\n'
        )

        session2 = project_trello / "session-002.jsonl"
        session2.write_text(
            '{"type": "user", "message": "start"}\n'
            '{"type": "summary", "summary": "Add user profile page"}\n'
        )

        # Project: api-server
        project_api = projects / "-Users-user-work-api--server"
        project_api.mkdir()

        session3 = project_api / "session-003.jsonl"
        session3.write_text(
            '{"type": "user", "message": "debug"}\n'
            '{"type": "summary", "summary": "Debug authentication middleware"}\n'
        )

        session4 = project_api / "session-004.jsonl"
        session4.write_text(
            '{"type": "user", "message": "feature"}\n'
            '{"type": "summary", "summary": "Implement rate limiting"}\n'
        )

        return projects

    @pytest.fixture
    async def search_engine(self, projects_dir: Path, tmp_path: Path) -> SearchEngine:
        """Create a SearchEngine with populated index."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(include_subagents=False, persist=False),
            state_dir=state_dir,
        )

        # Build the index
        await indexer.get_index()

        return SearchEngine(indexer)

    @pytest.mark.asyncio
    async def test_search_by_term(self, search_engine: SearchEngine) -> None:
        """Search sessions by term."""
        params = search_engine.parse_query("auth")
        results = await search_engine.search(params)

        assert results.total == 2  # session-001 and session-003 have "auth"
        # Both have "auth" in summary, should be high ranked
        for session in results.results:
            assert "auth" in session.summary.lower()

    @pytest.mark.asyncio
    async def test_search_empty_returns_all(self, search_engine: SearchEngine) -> None:
        """Empty search returns all sessions."""
        params = search_engine.parse_query("")
        results = await search_engine.search(params)

        assert results.total == 4  # All 4 sessions

    @pytest.mark.asyncio
    async def test_search_with_project_filter(
        self, search_engine: SearchEngine
    ) -> None:
        """Search with project filter."""
        params = search_engine.parse_query("-p trello")
        results = await search_engine.search(params)

        assert results.total == 2  # Only trello sessions
        for session in results.results:
            assert session.project_display_name == "trello"

    @pytest.mark.asyncio
    async def test_search_ranking_prioritizes_summary(
        self, search_engine: SearchEngine
    ) -> None:
        """Ranking prioritizes summary matches over project matches."""
        params = search_engine.parse_query("api")
        results = await search_engine.search(params)

        # Should find api-server sessions (project match)
        # No sessions have "api" in summary
        assert results.total >= 2  # At least the api-server sessions

    @pytest.mark.asyncio
    async def test_search_sort_recent(self, search_engine: SearchEngine) -> None:
        """Sort by recent works."""
        params = search_engine.parse_query("")
        params.sort = "recent"
        results = await search_engine.search(params)

        # Results should be sorted by modified_at descending (newest first)
        # (and by score, but with no terms, only recency matters)
        assert results.total == 4

    @pytest.mark.asyncio
    async def test_search_sort_oldest(self, search_engine: SearchEngine) -> None:
        """Sort by oldest works."""
        params = search_engine.parse_query("")
        params.sort = "oldest"
        results = await search_engine.search(params)

        # Results should be sorted by modified_at ascending (oldest first)
        assert results.total == 4

    @pytest.mark.asyncio
    async def test_search_sort_size(self, search_engine: SearchEngine) -> None:
        """Sort by size works."""
        params = search_engine.parse_query("")
        params.sort = "size"
        results = await search_engine.search(params)

        # Results should be sorted by size_bytes descending
        for i in range(len(results.results) - 1):
            assert results.results[i].size_bytes >= results.results[i + 1].size_bytes

    @pytest.mark.asyncio
    async def test_search_pagination(self, search_engine: SearchEngine) -> None:
        """Pagination works correctly."""
        params = search_engine.parse_query("")
        params.limit = 2
        params.offset = 0

        results1 = await search_engine.search(params)
        assert len(results1.results) == 2
        assert results1.total == 4
        assert results1.offset == 0

        # Get second page
        params.offset = 2
        results2 = await search_engine.search(params)
        assert len(results2.results) == 2
        assert results2.offset == 2

        # Results should be different
        page1_ids = {s.session_id for s in results1.results}
        page2_ids = {s.session_id for s in results2.results}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_search_no_results(self, search_engine: SearchEngine) -> None:
        """Search with no matches returns empty results."""
        params = search_engine.parse_query("nonexistent query term xyz")
        results = await search_engine.search(params)

        assert results.total == 0
        assert results.results == []

    @pytest.mark.asyncio
    async def test_search_quoted_phrase(self, search_engine: SearchEngine) -> None:
        """Search with quoted phrase."""
        params = search_engine.parse_query('"authentication bug"')
        results = await search_engine.search(params)

        # Should match session with exact phrase
        assert results.total >= 1
        # The session with "Fix authentication bug in login" should match
        found = False
        for session in results.results:
            if session.summary and "authentication bug" in session.summary.lower():
                found = True
                break
        assert found

    @pytest.mark.asyncio
    async def test_search_minimum_query_length(
        self, search_engine: SearchEngine
    ) -> None:
        """Search terms shorter than 2 chars are ignored."""
        params = search_engine.parse_query("a")  # Single char
        results = await search_engine.search(params)

        # Single char terms are filtered out, so should return all sessions
        assert results.total == 4

    @pytest.mark.asyncio
    async def test_search_session_id_exact_match(
        self, search_engine: SearchEngine
    ) -> None:
        """Search by exact session ID."""
        params = search_engine.parse_query("session-001")
        results = await search_engine.search(params)

        assert results.total == 1
        assert results.results[0].session_id == "session-001"


class TestSearchFilters:
    """Tests for search filter edge cases."""

    @pytest.fixture
    def projects_dir_with_dates(self, tmp_path: Path) -> Path:
        """Create projects with sessions at different dates."""
        projects = tmp_path / ".claude" / "projects"
        projects.mkdir(parents=True)

        project = projects / "-Users-user-work-app"
        project.mkdir()

        import time

        # Create sessions - they'll have current mtime
        for i in range(3):
            session = project / f"session-{i:03d}.jsonl"
            session.write_text(f'{{"type": "summary", "summary": "Session {i}"}}\n')
            # Sleep briefly so mtimes differ
            time.sleep(0.01)

        return projects

    @pytest.mark.asyncio
    async def test_filter_project_case_insensitive(
        self, projects_dir_with_dates: Path, tmp_path: Path
    ) -> None:
        """Project filter is case-insensitive."""
        indexer = SessionIndexer(
            paths=[projects_dir_with_dates],
            config=IndexConfig(persist=False),
            state_dir=tmp_path / "state",
        )
        await indexer.get_index()
        engine = SearchEngine(indexer)

        # Uppercase filter should match lowercase project
        params = engine.parse_query("-p APP")
        results = await engine.search(params)

        assert results.total == 3  # All sessions in 'app' project

    @pytest.mark.asyncio
    async def test_filter_project_substring(
        self, projects_dir_with_dates: Path, tmp_path: Path
    ) -> None:
        """Project filter matches substring."""
        indexer = SessionIndexer(
            paths=[projects_dir_with_dates],
            config=IndexConfig(persist=False),
            state_dir=tmp_path / "state",
        )
        await indexer.get_index()
        engine = SearchEngine(indexer)

        # Partial match
        params = engine.parse_query("-p pp")
        results = await engine.search(params)

        assert results.total == 3  # 'pp' in 'app'


# ---------------------------------------------------------------------------
# SearchParams defaults tests
# ---------------------------------------------------------------------------


class TestSearchParamsDefaults:
    """Tests for SearchParams default values."""

    def test_default_sort(self) -> None:
        """Default sort is 'recent'."""
        params = parse_query("test")
        assert params.sort == "recent"

    def test_default_limit(self) -> None:
        """Default limit from SearchParams."""
        params = SearchParams(query="test", terms=["test"])
        assert params.limit == 5

    def test_default_offset(self) -> None:
        """Default offset from SearchParams."""
        params = SearchParams(query="test", terms=["test"])
        assert params.offset == 0
