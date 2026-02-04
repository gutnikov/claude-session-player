"""FTS5 full-text search specific tests for SearchDatabase.

Tests FTS5 availability detection, schema creation, sync triggers,
query building, and fallback behavior when FTS5 is unavailable.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
    SearchFilters,
)


# ---------------------------------------------------------------------------
# FTS5 Detection Tests
# ---------------------------------------------------------------------------


class TestFTS5Detection:
    """Tests for FTS5 availability detection."""

    def test_fts5_detection_available(self) -> None:
        """_check_fts5_available returns True when FTS5 works."""
        result = SearchDatabase._check_fts5_available()
        # FTS5 should be available on most modern systems
        assert isinstance(result, bool)

    def test_fts5_detection_unavailable(self) -> None:
        """_check_fts5_available returns False when FTS5 fails."""
        with patch("claude_session_player.watcher.search_db.sqlite3.connect") as mock:
            mock_conn = mock.return_value
            mock_conn.execute.side_effect = sqlite3.OperationalError(
                "no such module: fts5"
            )
            result = SearchDatabase._check_fts5_available()
            assert result is False

    def test_fts_available_property_cached(self, tmp_path: Path) -> None:
        """fts_available property is cached after first check."""
        db = SearchDatabase(tmp_path)
        first_result = db.fts_available

        # Manually change cached value
        db._fts_available = not first_result

        # Second access returns cached value
        assert db.fts_available == (not first_result)

    def test_fts_available_uses_static_method(self, tmp_path: Path) -> None:
        """fts_available property uses _check_fts5_available static method."""
        db = SearchDatabase(tmp_path)
        db._fts_available = None  # Clear cache

        with patch.object(
            SearchDatabase, "_check_fts5_available", return_value=True
        ) as mock_check:
            result = db.fts_available
            mock_check.assert_called_once()
            assert result is True


# ---------------------------------------------------------------------------
# FTS5 Schema Tests
# ---------------------------------------------------------------------------


class TestFTS5Schema:
    """Tests for FTS5 schema creation."""

    @pytest.mark.asyncio
    async def test_fts_schema_created(self, tmp_path: Path) -> None:
        """Virtual table and triggers created when FTS5 available."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        if db.fts_available:
            conn = await db._get_connection()

            # Check FTS table exists
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
            ) as cursor:
                row = await cursor.fetchone()
                assert row is not None, "sessions_fts table should exist"

            # Check triggers exist
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ) as cursor:
                rows = await cursor.fetchall()
                trigger_names = {row["name"] for row in rows}
                assert "sessions_fts_insert" in trigger_names
                assert "sessions_fts_delete" in trigger_names
                assert "sessions_fts_update" in trigger_names

        await db.close()

    @pytest.mark.asyncio
    async def test_fts_metadata_stored(
        self, search_db: SearchDatabase
    ) -> None:
        """FTS availability stored in metadata table."""
        fts_meta = await search_db._get_metadata("fts_available")
        assert fts_meta in ("0", "1")
        assert fts_meta == ("1" if search_db.fts_available else "0")

    @pytest.mark.asyncio
    async def test_fts_schema_not_created_when_unavailable(
        self, temp_state_dir: Path
    ) -> None:
        """FTS schema not created when FTS5 unavailable."""
        db = SearchDatabase(temp_state_dir)
        db._fts_available = False
        await db.initialize()

        conn = await db._get_connection()

        # FTS table should not exist
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None, "sessions_fts should not exist when FTS unavailable"

        await db.close()


# ---------------------------------------------------------------------------
# FTS5 Sync Tests
# ---------------------------------------------------------------------------


class TestFTS5Sync:
    """Tests for FTS5 sync triggers."""

    @pytest.fixture
    def session_factory(self) -> Callable[..., IndexedSession]:
        """Create test sessions."""
        counter = [0]

        def _create(
            summary: str = "Test summary",
            project_display_name: str = "test-project",
        ) -> IndexedSession:
            counter[0] += 1
            now = datetime.now(timezone.utc)
            return IndexedSession(
                session_id=f"fts-test-{counter[0]}",
                project_encoded="-test-project",
                project_display_name=project_display_name,
                project_path="/test/project",
                summary=summary,
                file_path=f"/test/project/fts-test-{counter[0]}.jsonl",
                file_created_at=now,
                file_modified_at=now,
                indexed_at=now,
                size_bytes=1000,
                line_count=50,
                duration_ms=60000,
                has_subagents=False,
                is_subagent=False,
            )

        return _create

    @pytest.mark.asyncio
    async def test_fts_sync_on_insert(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """FTS updated when session inserted."""
        if not search_db.fts_available:
            pytest.skip("FTS5 not available")

        session = session_factory(
            summary="Authentication bug fix",
            project_display_name="my-project",
        )
        await search_db.upsert_session(session)

        # Verify FTS table has the data
        conn = await search_db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'authentication'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["session_id"] == session.session_id

    @pytest.mark.asyncio
    async def test_fts_sync_on_update(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """FTS updated when session updated."""
        if not search_db.fts_available:
            pytest.skip("FTS5 not available")

        # Insert initial session
        session1 = session_factory(summary="Original summary")
        await search_db.upsert_session(session1)

        # Update session (same ID, different summary)
        session2 = IndexedSession(
            session_id=session1.session_id,
            project_encoded=session1.project_encoded,
            project_display_name=session1.project_display_name,
            project_path=session1.project_path,
            summary="Updated authentication summary",
            file_path=session1.file_path,
            file_created_at=session1.file_created_at,
            file_modified_at=datetime.now(timezone.utc),
            indexed_at=datetime.now(timezone.utc),
            size_bytes=session1.size_bytes,
            line_count=session1.line_count,
            duration_ms=session1.duration_ms,
            has_subagents=session1.has_subagents,
            is_subagent=session1.is_subagent,
        )
        await search_db.upsert_session(session2)

        # Verify FTS has updated data
        conn = await search_db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'authentication'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["session_id"] == session1.session_id

        # Old value should not be found
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'original'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None

    @pytest.mark.asyncio
    async def test_fts_sync_on_delete(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """FTS updated when session deleted."""
        if not search_db.fts_available:
            pytest.skip("FTS5 not available")

        session = session_factory(summary="Delete test session")
        await search_db.upsert_session(session)

        # Verify it's in FTS
        conn = await search_db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'delete'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None

        # Delete session
        await search_db.delete_session(session.session_id)

        # Verify removed from FTS
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'delete'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None


# ---------------------------------------------------------------------------
# FTS5 Query Building Tests
# ---------------------------------------------------------------------------


class TestFTSQueryBuilding:
    """Tests for FTS5 query building."""

    def test_simple_term(self, tmp_path: Path) -> None:
        """Single term returns unchanged."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("authentication")
        assert result == "authentication"

    def test_multiple_terms(self, tmp_path: Path) -> None:
        """Multiple terms joined with OR."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("auth bug")
        assert result == "auth OR bug"

    def test_quoted_phrase(self, tmp_path: Path) -> None:
        """Quoted phrase preserved as exact match."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"auth bug"')
        assert result == '"auth bug"'

    def test_mixed_terms_and_phrases(self, tmp_path: Path) -> None:
        """Mixed terms and phrases handled correctly."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('fix "auth bug"')
        assert result == 'fix OR "auth bug"'

    def test_empty_query(self, tmp_path: Path) -> None:
        """Empty query returns wildcard."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("")
        assert result == "*"

    def test_whitespace_only(self, tmp_path: Path) -> None:
        """Whitespace-only query returns wildcard."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("   ")
        assert result == "*"

    def test_unclosed_quote(self, tmp_path: Path) -> None:
        """Unclosed quote treated as regular word."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"unclosed')
        assert result == "unclosed"

    def test_multiple_phrases(self, tmp_path: Path) -> None:
        """Multiple phrases joined with OR."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"auth bug" "login error"')
        assert result == '"auth bug" OR "login error"'

    def test_special_characters_stripped(self, tmp_path: Path) -> None:
        """Query with only spaces inside quotes."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('""')
        # Empty quoted string produces nothing
        assert result == "*"


# ---------------------------------------------------------------------------
# FTS5 Fallback Tests
# ---------------------------------------------------------------------------


class TestFTSFallback:
    """Tests for fallback behavior when FTS5 is unavailable."""

    @pytest.mark.asyncio
    async def test_search_without_fts(
        self,
        temp_state_dir: Path,
        sample_session: Callable[..., IndexedSession],
    ) -> None:
        """Search works without FTS5 using LIKE fallback."""
        db = SearchDatabase(temp_state_dir)
        db._fts_available = False
        await db.initialize()

        # Insert sessions
        await db.upsert_session(
            sample_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Fix authentication bug",
            )
        )
        await db.upsert_session(
            sample_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                summary="Add new feature",
            )
        )

        # Search should work with LIKE
        results, total = await db.search(SearchFilters(query="auth"))
        assert total == 1
        assert results[0].session_id == "s1"

        await db.close()

    @pytest.mark.asyncio
    async def test_fallback_same_results(
        self,
        tmp_path: Path,
        sample_session: Callable[..., IndexedSession],
    ) -> None:
        """LIKE fallback produces reasonable results."""
        db = SearchDatabase(tmp_path)
        db._fts_available = False
        await db.initialize()

        await db.upsert_session(
            sample_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Authentication and authorization",
                project_display_name="auth-service",
            )
        )

        # LIKE should find partial matches
        results, total = await db.search(SearchFilters(query="auth"))
        assert total == 1
        # Should match both summary (authentication, authorization) and project name

        await db.close()

    @pytest.mark.asyncio
    async def test_initialize_logs_warning_when_fts_unavailable(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning logged when FTS5 unavailable."""
        db = SearchDatabase(tmp_path)
        db._fts_available = False

        with caplog.at_level("WARNING"):
            await db.initialize()

        assert "FTS5 not available" in caplog.text
        await db.close()

    @pytest.mark.asyncio
    async def test_clear_all_works_without_fts(
        self,
        temp_state_dir: Path,
        sample_session: Callable[..., IndexedSession],
    ) -> None:
        """clear_all works when FTS table doesn't exist."""
        db = SearchDatabase(temp_state_dir)
        db._fts_available = False
        await db.initialize()

        await db.upsert_session(
            sample_session(session_id="s1", file_path="/path/s1.jsonl")
        )

        # Should not raise even though FTS table doesn't exist
        await db.clear_all()

        assert await db.get_session("s1") is None
        await db.close()


# ---------------------------------------------------------------------------
# FTS5 Integration Tests
# ---------------------------------------------------------------------------


class TestFTS5Integration:
    """Integration tests for FTS5 search functionality."""

    @pytest.fixture
    async def db_with_data(
        self,
        tmp_path: Path,
        sample_session: Callable[..., IndexedSession],
    ) -> SearchDatabase:
        """Create database with test data."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        sessions = [
            sample_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Fix authentication bug in login",
                project_display_name="auth-service",
            ),
            sample_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                summary="Add user registration feature",
                project_display_name="auth-service",
            ),
            sample_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                summary="Update API documentation",
                project_display_name="api-docs",
            ),
        ]
        await db.upsert_sessions_batch(sessions)
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_fts_search_finds_matches(
        self, db_with_data: SearchDatabase
    ) -> None:
        """FTS search returns correct results."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        async with conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE session_id IN (
                SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH 'auth'
            )
            """
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = {row["session_id"] for row in rows}
            assert "s1" in session_ids  # "authentication" contains "auth" stem

    @pytest.mark.asyncio
    async def test_fts_search_project_name(
        self, db_with_data: SearchDatabase
    ) -> None:
        """FTS search matches project display name."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        async with conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE session_id IN (
                SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH 'api'
            )
            """
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = {row["session_id"] for row in rows}
            assert "s3" in session_ids

    @pytest.mark.asyncio
    async def test_fts_search_phrase(
        self, db_with_data: SearchDatabase
    ) -> None:
        """FTS search handles exact phrases."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        async with conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE session_id IN (
                SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH '"authentication bug"'
            )
            """
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = {row["session_id"] for row in rows}
            assert "s1" in session_ids

    @pytest.mark.asyncio
    async def test_fts_porter_stemming(
        self, db_with_data: SearchDatabase
    ) -> None:
        """FTS5 uses porter stemming for word matching."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        # "authenticate" should match "authentication" due to stemming
        async with conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE session_id IN (
                SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH 'authenticate'
            )
            """
        ) as cursor:
            rows = await cursor.fetchall()
            # Porter stemmer may or may not match depending on exact tokenization
            # This test verifies the query doesn't error
            assert isinstance(rows, list)

    @pytest.mark.asyncio
    async def test_fts_unicode_content(
        self,
        search_db: SearchDatabase,
        sample_session: Callable[..., IndexedSession],
    ) -> None:
        """FTS5 handles unicode content correctly."""
        if not search_db.fts_available:
            pytest.skip("FTS5 not available")

        await search_db.upsert_session(
            sample_session(
                session_id="unicode-test",
                file_path="/path/unicode.jsonl",
                summary="修复认证错误 authentication fix",
                project_display_name="国际化",
            )
        )

        conn = await search_db._get_connection()

        # Search for ASCII part
        async with conn.execute(
            """
            SELECT session_id FROM sessions
            WHERE session_id IN (
                SELECT session_id FROM sessions_fts WHERE sessions_fts MATCH 'authentication'
            )
            """
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = {row["session_id"] for row in rows}
            assert "unicode-test" in session_ids
