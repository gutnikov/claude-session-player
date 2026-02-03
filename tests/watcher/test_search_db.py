"""Tests for SearchDatabase and IndexedSession."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
    SearchFilters,
    SearchResult,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def create_test_session(
    session_id: str = "test-session-001",
    project_encoded: str = "-Users-user-work-app",
    project_display_name: str = "app",
    project_path: str = "/Users/user/work/app",
    summary: str | None = "Test session summary",
    file_path: str = "/path/to/session.jsonl",
    file_created_at: datetime | None = None,
    file_modified_at: datetime | None = None,
    indexed_at: datetime | None = None,
    size_bytes: int = 1000,
    line_count: int = 50,
    duration_ms: int | None = 60000,
    has_subagents: bool = False,
    is_subagent: bool = False,
) -> IndexedSession:
    """Create a test IndexedSession with sensible defaults."""
    now = datetime.now(timezone.utc)
    return IndexedSession(
        session_id=session_id,
        project_encoded=project_encoded,
        project_display_name=project_display_name,
        project_path=project_path,
        summary=summary,
        file_path=file_path,
        file_created_at=file_created_at or now - timedelta(hours=1),
        file_modified_at=file_modified_at or now,
        indexed_at=indexed_at or now,
        size_bytes=size_bytes,
        line_count=line_count,
        duration_ms=duration_ms,
        has_subagents=has_subagents,
        is_subagent=is_subagent,
    )


# ---------------------------------------------------------------------------
# IndexedSession tests
# ---------------------------------------------------------------------------


class TestIndexedSession:
    """Tests for IndexedSession dataclass."""

    def test_create_indexed_session(self) -> None:
        """Create IndexedSession with all fields."""
        now = datetime.now(timezone.utc)
        session = IndexedSession(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            project_path="/Users/user/work/app",
            summary="Test session",
            file_path="/path/to/session.jsonl",
            file_created_at=now - timedelta(hours=1),
            file_modified_at=now,
            indexed_at=now,
            size_bytes=1234,
            line_count=50,
            duration_ms=60000,
            has_subagents=True,
            is_subagent=False,
        )
        assert session.session_id == "session-123"
        assert session.summary == "Test session"
        assert session.has_subagents is True
        assert session.is_subagent is False

    def test_create_indexed_session_null_summary(self) -> None:
        """Create IndexedSession with null summary."""
        session = create_test_session(summary=None)
        assert session.summary is None

    def test_create_indexed_session_null_duration(self) -> None:
        """Create IndexedSession with null duration."""
        session = create_test_session(duration_ms=None)
        assert session.duration_ms is None

    def test_to_row_returns_tuple(self) -> None:
        """to_row returns tuple in correct order."""
        now = datetime.now(timezone.utc)
        session = IndexedSession(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            project_path="/Users/user/work/app",
            summary="Test session",
            file_path="/path/to/session.jsonl",
            file_created_at=now,
            file_modified_at=now,
            indexed_at=now,
            size_bytes=1234,
            line_count=50,
            duration_ms=60000,
            has_subagents=True,
            is_subagent=False,
        )
        row = session.to_row()

        assert isinstance(row, tuple)
        assert len(row) == 14
        assert row[0] == "session-123"  # session_id
        assert row[1] == "-Users-user-work-app"  # project_encoded
        assert row[2] == "app"  # project_display_name
        assert row[3] == "/Users/user/work/app"  # project_path
        assert row[4] == "Test session"  # summary
        assert row[5] == "/path/to/session.jsonl"  # file_path
        assert row[6] == now.isoformat()  # file_created_at
        assert row[7] == now.isoformat()  # file_modified_at
        assert row[8] == now.isoformat()  # indexed_at
        assert row[9] == 1234  # size_bytes
        assert row[10] == 50  # line_count
        assert row[11] == 60000  # duration_ms
        assert row[12] == 1  # has_subagents (True → 1)
        assert row[13] == 0  # is_subagent (False → 0)

    def test_to_row_boolean_conversion(self) -> None:
        """to_row converts booleans to integers."""
        session_with_subagents = create_test_session(has_subagents=True, is_subagent=False)
        row1 = session_with_subagents.to_row()
        assert row1[12] == 1
        assert row1[13] == 0

        session_is_subagent = create_test_session(has_subagents=False, is_subagent=True)
        row2 = session_is_subagent.to_row()
        assert row2[12] == 0
        assert row2[13] == 1


# ---------------------------------------------------------------------------
# SearchDatabase initialization tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseInitialization:
    """Tests for SearchDatabase initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, tmp_path: Path) -> None:
        """Database initializes with correct schema."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # Verify tables exist by checking integrity
        assert await db.verify_integrity() is True

        await db.close()

    @pytest.mark.asyncio
    async def test_initialize_creates_state_dir(self, tmp_path: Path) -> None:
        """Initialize creates state directory if missing."""
        state_dir = tmp_path / "nested" / "state" / "dir"
        db = SearchDatabase(state_dir)
        await db.initialize()

        assert state_dir.exists()
        assert (state_dir / "search.db").exists()

        await db.close()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path: Path) -> None:
        """Initialize can be called multiple times safely."""
        db = SearchDatabase(tmp_path)

        await db.initialize()
        await db.initialize()  # Should not raise
        await db.initialize()  # Should not raise

        assert await db.verify_integrity() is True

        await db.close()

    @pytest.mark.asyncio
    async def test_close_connection(self, tmp_path: Path) -> None:
        """Close properly closes the connection."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        await db.close()

        # Connection should be None after close
        assert db._connection is None


# ---------------------------------------------------------------------------
# CRUD operation tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseCRUD:
    """Tests for SearchDatabase CRUD operations."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_upsert_session_insert(self, db: SearchDatabase) -> None:
        """New session is inserted."""
        session = create_test_session(session_id="new-session")
        await db.upsert_session(session)

        retrieved = await db.get_session("new-session")
        assert retrieved is not None
        assert retrieved.session_id == "new-session"
        assert retrieved.summary == "Test session summary"

    @pytest.mark.asyncio
    async def test_upsert_session_update(self, db: SearchDatabase) -> None:
        """Existing session is updated."""
        session1 = create_test_session(session_id="test-session", summary="Original")
        await db.upsert_session(session1)

        session2 = create_test_session(session_id="test-session", summary="Updated")
        await db.upsert_session(session2)

        retrieved = await db.get_session("test-session")
        assert retrieved is not None
        assert retrieved.summary == "Updated"

    @pytest.mark.asyncio
    async def test_upsert_sessions_batch(self, db: SearchDatabase) -> None:
        """Batch insert/update works."""
        sessions = [
            create_test_session(session_id="batch-1", file_path="/path/1.jsonl"),
            create_test_session(session_id="batch-2", file_path="/path/2.jsonl"),
            create_test_session(session_id="batch-3", file_path="/path/3.jsonl"),
        ]
        count = await db.upsert_sessions_batch(sessions)

        assert count == 3

        for i in range(1, 4):
            retrieved = await db.get_session(f"batch-{i}")
            assert retrieved is not None

    @pytest.mark.asyncio
    async def test_upsert_sessions_batch_empty(self, db: SearchDatabase) -> None:
        """Batch insert with empty list returns 0."""
        count = await db.upsert_sessions_batch([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_session(self, db: SearchDatabase) -> None:
        """Session is deleted."""
        session = create_test_session(session_id="to-delete")
        await db.upsert_session(session)

        result = await db.delete_session("to-delete")
        assert result is True

        retrieved = await db.get_session("to-delete")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, db: SearchDatabase) -> None:
        """Delete returns False for missing session."""
        result = await db.delete_session("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_session(self, db: SearchDatabase) -> None:
        """Get retrieves by ID."""
        session = create_test_session(session_id="find-me")
        await db.upsert_session(session)

        retrieved = await db.get_session("find-me")
        assert retrieved is not None
        assert retrieved.session_id == "find-me"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, db: SearchDatabase) -> None:
        """Get returns None for missing session."""
        retrieved = await db.get_session("nonexistent")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_session_by_path(self, db: SearchDatabase) -> None:
        """Get retrieves by file path."""
        session = create_test_session(
            session_id="path-session",
            file_path="/unique/path/to/session.jsonl",
        )
        await db.upsert_session(session)

        retrieved = await db.get_session_by_path("/unique/path/to/session.jsonl")
        assert retrieved is not None
        assert retrieved.session_id == "path-session"

    @pytest.mark.asyncio
    async def test_get_session_by_path_not_found(self, db: SearchDatabase) -> None:
        """Get by path returns None for missing path."""
        retrieved = await db.get_session_by_path("/nonexistent/path.jsonl")
        assert retrieved is None


# ---------------------------------------------------------------------------
# IndexedSession roundtrip tests
# ---------------------------------------------------------------------------


class TestIndexedSessionRoundtrip:
    """Tests for IndexedSession to_row/from_row roundtrip."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_data(self, db: SearchDatabase) -> None:
        """to_row/from_row roundtrip preserves all fields."""
        original = create_test_session(
            session_id="roundtrip-test",
            project_encoded="-Users-test-project",
            project_display_name="project",
            project_path="/Users/test/project",
            summary="Roundtrip test summary",
            file_path="/path/to/roundtrip.jsonl",
            size_bytes=5000,
            line_count=100,
            duration_ms=120000,
            has_subagents=True,
            is_subagent=False,
        )

        await db.upsert_session(original)
        retrieved = await db.get_session("roundtrip-test")

        assert retrieved is not None
        assert retrieved.session_id == original.session_id
        assert retrieved.project_encoded == original.project_encoded
        assert retrieved.project_display_name == original.project_display_name
        assert retrieved.project_path == original.project_path
        assert retrieved.summary == original.summary
        assert retrieved.file_path == original.file_path
        assert retrieved.size_bytes == original.size_bytes
        assert retrieved.line_count == original.line_count
        assert retrieved.duration_ms == original.duration_ms
        assert retrieved.has_subagents == original.has_subagents
        assert retrieved.is_subagent == original.is_subagent

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_timestamps(self, db: SearchDatabase) -> None:
        """Timestamps are preserved through roundtrip."""
        now = datetime.now(timezone.utc)
        original = create_test_session(
            session_id="timestamp-test",
            file_path="/path/to/timestamp.jsonl",
            file_created_at=now - timedelta(days=1),
            file_modified_at=now,
            indexed_at=now,
        )

        await db.upsert_session(original)
        retrieved = await db.get_session("timestamp-test")

        assert retrieved is not None
        # Compare ISO strings to avoid microsecond precision issues
        assert retrieved.file_created_at.isoformat() == original.file_created_at.isoformat()
        assert retrieved.file_modified_at.isoformat() == original.file_modified_at.isoformat()
        assert retrieved.indexed_at.isoformat() == original.indexed_at.isoformat()

    @pytest.mark.asyncio
    async def test_roundtrip_null_values(self, db: SearchDatabase) -> None:
        """Null values are preserved through roundtrip."""
        original = create_test_session(
            session_id="null-test",
            file_path="/path/to/null.jsonl",
            summary=None,
            duration_ms=None,
        )

        await db.upsert_session(original)
        retrieved = await db.get_session("null-test")

        assert retrieved is not None
        assert retrieved.summary is None
        assert retrieved.duration_ms is None


# ---------------------------------------------------------------------------
# Metadata operation tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseMetadata:
    """Tests for SearchDatabase metadata operations."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_metadata_set_get(self, db: SearchDatabase) -> None:
        """Metadata set and get works."""
        await db._set_metadata("test_key", "test_value")
        value = await db._get_metadata("test_key")
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_metadata_update(self, db: SearchDatabase) -> None:
        """Metadata can be updated."""
        await db._set_metadata("update_key", "original")
        await db._set_metadata("update_key", "updated")

        value = await db._get_metadata("update_key")
        assert value == "updated"

    @pytest.mark.asyncio
    async def test_metadata_get_missing(self, db: SearchDatabase) -> None:
        """Get metadata returns None for missing key."""
        value = await db._get_metadata("nonexistent_key")
        assert value is None


# ---------------------------------------------------------------------------
# File mtime tracking tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseFileMtime:
    """Tests for SearchDatabase file mtime tracking."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_file_mtime_set_get(self, db: SearchDatabase) -> None:
        """File mtime set and get works."""
        await db.set_file_mtime("/path/to/file.jsonl", 1234567890)
        mtime = await db.get_file_mtime("/path/to/file.jsonl")
        assert mtime == 1234567890

    @pytest.mark.asyncio
    async def test_file_mtime_update(self, db: SearchDatabase) -> None:
        """File mtime can be updated."""
        await db.set_file_mtime("/path/to/file.jsonl", 1000000000)
        await db.set_file_mtime("/path/to/file.jsonl", 2000000000)

        mtime = await db.get_file_mtime("/path/to/file.jsonl")
        assert mtime == 2000000000

    @pytest.mark.asyncio
    async def test_file_mtime_get_missing(self, db: SearchDatabase) -> None:
        """Get mtime returns None for missing path."""
        mtime = await db.get_file_mtime("/nonexistent/path.jsonl")
        assert mtime is None

    @pytest.mark.asyncio
    async def test_get_all_indexed_paths(self, db: SearchDatabase) -> None:
        """Get all indexed paths returns correct set."""
        sessions = [
            create_test_session(session_id="s1", file_path="/path/1.jsonl"),
            create_test_session(session_id="s2", file_path="/path/2.jsonl"),
            create_test_session(session_id="s3", file_path="/path/3.jsonl"),
        ]
        await db.upsert_sessions_batch(sessions)

        paths = await db.get_all_indexed_paths()
        assert paths == {"/path/1.jsonl", "/path/2.jsonl", "/path/3.jsonl"}

    @pytest.mark.asyncio
    async def test_get_all_indexed_paths_empty(self, db: SearchDatabase) -> None:
        """Get all indexed paths returns empty set when no sessions."""
        paths = await db.get_all_indexed_paths()
        assert paths == set()


# ---------------------------------------------------------------------------
# Maintenance operation tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseMaintenance:
    """Tests for SearchDatabase maintenance operations."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_clear_all(self, db: SearchDatabase) -> None:
        """Clear all removes all data."""
        # Insert some data
        sessions = [
            create_test_session(session_id="s1", file_path="/path/1.jsonl"),
            create_test_session(session_id="s2", file_path="/path/2.jsonl"),
        ]
        await db.upsert_sessions_batch(sessions)
        await db.set_file_mtime("/path/1.jsonl", 1234567890)

        # Clear all
        await db.clear_all()

        # Verify empty
        assert await db.get_session("s1") is None
        assert await db.get_session("s2") is None
        assert await db.get_file_mtime("/path/1.jsonl") is None

        paths = await db.get_all_indexed_paths()
        assert paths == set()

    @pytest.mark.asyncio
    async def test_verify_integrity(self, db: SearchDatabase) -> None:
        """Verify integrity returns True for valid DB."""
        result = await db.verify_integrity()
        assert result is True


# ---------------------------------------------------------------------------
# Connection handling tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseConnection:
    """Tests for SearchDatabase connection handling."""

    @pytest.mark.asyncio
    async def test_connection_reuse(self, tmp_path: Path) -> None:
        """Connection is reused across operations."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        conn1 = await db._get_connection()
        conn2 = await db._get_connection()

        assert conn1 is conn2

        await db.close()

    @pytest.mark.asyncio
    async def test_db_path_property(self, tmp_path: Path) -> None:
        """db_path is set correctly."""
        db = SearchDatabase(tmp_path)
        assert db.db_path == tmp_path / "search.db"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestSearchDatabaseEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_special_characters_in_summary(self, db: SearchDatabase) -> None:
        """Handle special characters in summary."""
        session = create_test_session(
            session_id="special-chars",
            file_path="/path/special.jsonl",
            summary="Summary with 'quotes', \"double quotes\", and emoji 🎉",
        )
        await db.upsert_session(session)

        retrieved = await db.get_session("special-chars")
        assert retrieved is not None
        assert "quotes" in retrieved.summary
        assert "🎉" in retrieved.summary

    @pytest.mark.asyncio
    async def test_unicode_in_paths(self, db: SearchDatabase) -> None:
        """Handle unicode in file paths."""
        session = create_test_session(
            session_id="unicode-path",
            file_path="/path/到/文件.jsonl",
        )
        await db.upsert_session(session)

        retrieved = await db.get_session_by_path("/path/到/文件.jsonl")
        assert retrieved is not None
        assert retrieved.session_id == "unicode-path"

    @pytest.mark.asyncio
    async def test_very_long_summary(self, db: SearchDatabase) -> None:
        """Handle very long summary."""
        long_summary = "A" * 10000  # 10KB summary
        session = create_test_session(
            session_id="long-summary",
            file_path="/path/long.jsonl",
            summary=long_summary,
        )
        await db.upsert_session(session)

        retrieved = await db.get_session("long-summary")
        assert retrieved is not None
        assert len(retrieved.summary) == 10000

    @pytest.mark.asyncio
    async def test_datetime_timezone_handling(self, db: SearchDatabase) -> None:
        """Handle datetime timezone conversion."""
        # Use a specific UTC time
        utc_time = datetime(2024, 6, 15, 12, 30, 45, tzinfo=timezone.utc)
        session = create_test_session(
            session_id="tz-test",
            file_path="/path/tz.jsonl",
            file_created_at=utc_time,
            file_modified_at=utc_time,
            indexed_at=utc_time,
        )
        await db.upsert_session(session)

        retrieved = await db.get_session("tz-test")
        assert retrieved is not None
        # Datetimes should match (stored as ISO strings, parsed back)
        assert retrieved.file_created_at.isoformat() == utc_time.isoformat()


# ---------------------------------------------------------------------------
# FTS5 detection tests
# ---------------------------------------------------------------------------


class TestFTS5Detection:
    """Tests for FTS5 availability detection."""

    def test_fts5_detection_available(self) -> None:
        """Returns True when FTS5 works."""
        # Test the actual method - FTS5 should be available on most systems
        result = SearchDatabase._check_fts5_available()
        # We can't guarantee FTS5 is available, but we can verify the method runs
        assert isinstance(result, bool)

    def test_fts5_detection_unavailable(self) -> None:
        """Returns False when FTS5 fails."""
        # Mock the sqlite3 module to simulate FTS5 not being available
        with patch("claude_session_player.watcher.search_db.sqlite3.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            mock_conn.execute.side_effect = sqlite3.OperationalError("no such module: fts5")

            result = SearchDatabase._check_fts5_available()
            assert result is False

    def test_fts_available_property_cached(self, tmp_path: Path) -> None:
        """fts_available property is cached after first check."""
        db = SearchDatabase(tmp_path)

        # First access
        first_result = db.fts_available

        # Manually change the cached value
        db._fts_available = not first_result

        # Second access should return cached value
        assert db.fts_available == (not first_result)

    def test_fts_available_uses_static_method(self, tmp_path: Path) -> None:
        """fts_available property uses _check_fts5_available."""
        db = SearchDatabase(tmp_path)
        # Clear cache
        db._fts_available = None

        with patch.object(
            SearchDatabase, "_check_fts5_available", return_value=True
        ) as mock_check:
            result = db.fts_available
            mock_check.assert_called_once()
            assert result is True


# ---------------------------------------------------------------------------
# FTS5 schema tests
# ---------------------------------------------------------------------------


class TestFTS5Schema:
    """Tests for FTS5 schema creation."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

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
                assert row is not None

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
    async def test_fts_metadata_stored(self, db: SearchDatabase) -> None:
        """FTS availability stored in metadata table."""
        fts_meta = await db._get_metadata("fts_available")
        assert fts_meta in ("0", "1")
        assert fts_meta == ("1" if db.fts_available else "0")


# ---------------------------------------------------------------------------
# FTS5 sync tests
# ---------------------------------------------------------------------------


class TestFTS5Sync:
    """Tests for FTS5 sync triggers."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> SearchDatabase:
        """Create and initialize test database."""
        db = SearchDatabase(tmp_path)
        await db.initialize()
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_fts_sync_on_insert(self, db: SearchDatabase) -> None:
        """FTS updated when session inserted."""
        if not db.fts_available:
            pytest.skip("FTS5 not available")

        session = create_test_session(
            session_id="fts-test",
            file_path="/path/fts.jsonl",
            summary="Authentication bug fix",
            project_display_name="my-project",
        )
        await db.upsert_session(session)

        # Verify FTS table has the data
        conn = await db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'authentication'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["session_id"] == "fts-test"

    @pytest.mark.asyncio
    async def test_fts_sync_on_update(self, db: SearchDatabase) -> None:
        """FTS updated when session updated."""
        if not db.fts_available:
            pytest.skip("FTS5 not available")

        # Insert initial session
        session1 = create_test_session(
            session_id="fts-update",
            file_path="/path/fts-update.jsonl",
            summary="Original summary",
        )
        await db.upsert_session(session1)

        # Update session
        session2 = create_test_session(
            session_id="fts-update",
            file_path="/path/fts-update.jsonl",
            summary="Updated authentication summary",
        )
        await db.upsert_session(session2)

        # Verify FTS table has updated data
        conn = await db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'authentication'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["session_id"] == "fts-update"

        # Old value should not be found
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'original'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None

    @pytest.mark.asyncio
    async def test_fts_sync_on_delete(self, db: SearchDatabase) -> None:
        """FTS updated when session deleted."""
        if not db.fts_available:
            pytest.skip("FTS5 not available")

        # Insert session
        session = create_test_session(
            session_id="fts-delete",
            file_path="/path/fts-delete.jsonl",
            summary="Delete test session",
        )
        await db.upsert_session(session)

        # Verify it's in FTS
        conn = await db._get_connection()
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'delete'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None

        # Delete session
        await db.delete_session("fts-delete")

        # Verify it's removed from FTS
        async with conn.execute(
            "SELECT * FROM sessions_fts WHERE sessions_fts MATCH 'delete'"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None


# ---------------------------------------------------------------------------
# FTS5 query building tests
# ---------------------------------------------------------------------------


class TestBuildFTSQuery:
    """Tests for FTS5 query building."""

    def test_build_fts_query_simple(self, tmp_path: Path) -> None:
        """'auth bug' -> 'auth OR bug'."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("auth bug")
        assert result == "auth OR bug"

    def test_build_fts_query_phrase(self, tmp_path: Path) -> None:
        """'"auth bug"' -> '"auth bug"'."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"auth bug"')
        assert result == '"auth bug"'

    def test_build_fts_query_mixed(self, tmp_path: Path) -> None:
        """'fix "auth bug"' -> 'fix OR "auth bug"'."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('fix "auth bug"')
        assert result == 'fix OR "auth bug"'

    def test_build_fts_query_empty(self, tmp_path: Path) -> None:
        """Empty query returns '*'."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("")
        assert result == "*"

    def test_build_fts_query_single_word(self, tmp_path: Path) -> None:
        """Single word returns unchanged."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("authentication")
        assert result == "authentication"

    def test_build_fts_query_unclosed_quote(self, tmp_path: Path) -> None:
        """Unclosed quote treated as regular word."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"unclosed')
        assert result == "unclosed"

    def test_build_fts_query_multiple_phrases(self, tmp_path: Path) -> None:
        """Multiple phrases are joined with OR."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query('"auth bug" "login error"')
        assert result == '"auth bug" OR "login error"'

    def test_build_fts_query_whitespace_only(self, tmp_path: Path) -> None:
        """Whitespace-only query returns '*'."""
        db = SearchDatabase(tmp_path)
        result = db._build_fts_query("   ")
        assert result == "*"


# ---------------------------------------------------------------------------
# FTS5 fallback tests
# ---------------------------------------------------------------------------


class TestFTS5Fallback:
    """Tests for fallback behavior when FTS5 is unavailable."""

    @pytest.mark.asyncio
    async def test_fallback_when_fts_unavailable(self, tmp_path: Path) -> None:
        """LIKE queries work when FTS5 unavailable."""
        db = SearchDatabase(tmp_path)
        # Force FTS to be unavailable
        db._fts_available = False

        await db.initialize()

        # Insert some sessions
        await db.upsert_session(
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Fix authentication bug",
            )
        )
        await db.upsert_session(
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                summary="Add new feature",
            )
        )

        # Verify FTS metadata shows unavailable
        fts_meta = await db._get_metadata("fts_available")
        assert fts_meta == "0"

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
    async def test_clear_all_works_without_fts(self, tmp_path: Path) -> None:
        """clear_all works when FTS table doesn't exist."""
        db = SearchDatabase(tmp_path)
        db._fts_available = False
        await db.initialize()

        # Insert some data
        await db.upsert_session(
            create_test_session(session_id="s1", file_path="/path/s1.jsonl")
        )

        # This should not raise even though FTS table doesn't exist
        await db.clear_all()

        # Verify data is cleared
        assert await db.get_session("s1") is None

        await db.close()


# ---------------------------------------------------------------------------
# FTS5 integration tests
# ---------------------------------------------------------------------------


class TestFTS5Integration:
    """Integration tests for FTS5 search functionality."""

    @pytest.fixture
    async def db_with_data(self, tmp_path: Path) -> SearchDatabase:
        """Create database with test data."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # Insert test sessions
        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Fix authentication bug in login",
                project_display_name="auth-service",
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                summary="Add user registration feature",
                project_display_name="auth-service",
            ),
            create_test_session(
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
    async def test_fts_search_finds_matches(self, db_with_data: SearchDatabase) -> None:
        """FTS search returns correct results."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        # Search for "auth" - should find s1 (in summary) and s1, s2 (in project name)
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
            # Should find sessions mentioning "auth" in summary or project name
            assert "s1" in session_ids  # "authentication" in summary

    @pytest.mark.asyncio
    async def test_fts_search_project_name(self, db_with_data: SearchDatabase) -> None:
        """FTS search matches project display name."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        # Search for "api" - should find s3 (project name "api-docs")
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
    async def test_fts_search_phrase(self, db_with_data: SearchDatabase) -> None:
        """FTS search handles exact phrases."""
        if not db_with_data.fts_available:
            pytest.skip("FTS5 not available")

        conn = await db_with_data._get_connection()

        # Search for exact phrase "authentication bug"
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
            assert "s1" in session_ids  # Has "authentication bug" in summary


# ---------------------------------------------------------------------------
# SearchFilters dataclass tests
# ---------------------------------------------------------------------------


class TestSearchFilters:
    """Tests for SearchFilters dataclass."""

    def test_create_search_filters_defaults(self) -> None:
        """Create SearchFilters with default values."""
        filters = SearchFilters()
        assert filters.query is None
        assert filters.project is None
        assert filters.since is None
        assert filters.until is None
        assert filters.include_subagents is False

    def test_create_search_filters_all_fields(self) -> None:
        """Create SearchFilters with all fields."""
        now = datetime.now(timezone.utc)
        filters = SearchFilters(
            query="auth bug",
            project="trello",
            since=now - timedelta(days=7),
            until=now,
            include_subagents=True,
        )
        assert filters.query == "auth bug"
        assert filters.project == "trello"
        assert filters.since is not None
        assert filters.until is not None
        assert filters.include_subagents is True


# ---------------------------------------------------------------------------
# SearchResult dataclass tests
# ---------------------------------------------------------------------------


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_create_search_result(self) -> None:
        """Create SearchResult with session and score."""
        session = create_test_session(session_id="test-result")
        result = SearchResult(session=session, score=4.5)
        assert result.session.session_id == "test-result"
        assert result.score == 4.5

    def test_search_result_zero_score(self) -> None:
        """Create SearchResult with zero score."""
        session = create_test_session(session_id="zero-score")
        result = SearchResult(session=session, score=0.0)
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Search basic tests
# ---------------------------------------------------------------------------


class TestSearchBasic:
    """Tests for basic search operations."""

    @pytest.fixture
    async def db_with_sessions(self, tmp_path: Path) -> SearchDatabase:
        """Create database with multiple test sessions."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Fix authentication bug in login",
                project_display_name="trello",
                file_modified_at=now - timedelta(days=1),
                size_bytes=1000,
                duration_ms=60000,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                summary="Add user registration feature",
                project_display_name="trello",
                file_modified_at=now - timedelta(days=2),
                size_bytes=2000,
                duration_ms=120000,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                summary="Update API documentation",
                project_display_name="api-docs",
                file_modified_at=now - timedelta(days=3),
                size_bytes=500,
                duration_ms=30000,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s4",
                file_path="/path/s4.jsonl",
                summary="Subagent task session",
                project_display_name="trello",
                file_modified_at=now - timedelta(days=1),
                is_subagent=True,
            ),
            create_test_session(
                session_id="s5",
                file_path="/path/s5.jsonl",
                summary="Debug authentication issues",
                project_display_name="auth-service",
                file_modified_at=now - timedelta(days=10),
                size_bytes=3000,
                duration_ms=90000,
                is_subagent=False,
            ),
        ]
        await db.upsert_sessions_batch(sessions)
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_search_no_filters(self, db_with_sessions: SearchDatabase) -> None:
        """Search with no filters returns all non-subagent sessions."""
        results, total = await db_with_sessions.search(SearchFilters())
        assert total == 4  # Excludes subagent session
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_search_by_query_fts(self, db_with_sessions: SearchDatabase) -> None:
        """Search by query using FTS5 (if available)."""
        # FTS5 uses porter stemmer, so "authentication" matches "auth" query
        results, total = await db_with_sessions.search(SearchFilters(query="authentication"))
        # Should find sessions with "authentication" in summary
        session_ids = {s.session_id for s in results}
        assert "s1" in session_ids  # "authentication bug" in summary
        assert "s5" in session_ids  # "authentication issues" in summary

    @pytest.mark.asyncio
    async def test_search_by_query_like(self, db_with_sessions: SearchDatabase) -> None:
        """Search by query using LIKE fallback."""
        # Force LIKE fallback
        db_with_sessions._fts_available = False

        # LIKE does substring matching, so "auth" should find "authentication"
        results, total = await db_with_sessions.search(SearchFilters(query="auth"))
        session_ids = {s.session_id for s in results}
        assert "s1" in session_ids  # "authentication" in summary
        assert "s5" in session_ids  # "authentication" in summary, "auth" in project

    @pytest.mark.asyncio
    async def test_search_by_project(self, db_with_sessions: SearchDatabase) -> None:
        """Search by project name filter."""
        results, total = await db_with_sessions.search(SearchFilters(project="trello"))
        assert total == 2  # 2 non-subagent trello sessions
        for session in results:
            assert session.project_display_name == "trello"

    @pytest.mark.asyncio
    async def test_search_by_since(self, db_with_sessions: SearchDatabase) -> None:
        """Search by since date filter."""
        since = datetime.now(timezone.utc) - timedelta(days=2, hours=1)
        results, total = await db_with_sessions.search(SearchFilters(since=since))
        # Should find sessions modified in last ~2 days
        assert total == 2  # s1 (1 day), s2 (2 days)

    @pytest.mark.asyncio
    async def test_search_by_until(self, db_with_sessions: SearchDatabase) -> None:
        """Search by until date filter."""
        until = datetime.now(timezone.utc) - timedelta(days=2)
        results, total = await db_with_sessions.search(SearchFilters(until=until))
        # Should find sessions modified 2+ days ago
        assert total >= 2  # s2, s3, s5

    @pytest.mark.asyncio
    async def test_search_combined_filters(self, db_with_sessions: SearchDatabase) -> None:
        """Search with multiple filters combined."""
        since = datetime.now(timezone.utc) - timedelta(days=3)
        results, total = await db_with_sessions.search(
            SearchFilters(project="trello", since=since)
        )
        # Should find trello sessions modified in last 3 days
        assert total == 2  # s1 and s2
        for session in results:
            assert session.project_display_name == "trello"

    @pytest.mark.asyncio
    async def test_search_excludes_subagents(
        self, db_with_sessions: SearchDatabase
    ) -> None:
        """Search excludes subagent sessions by default."""
        results, total = await db_with_sessions.search(SearchFilters())
        session_ids = {s.session_id for s in results}
        assert "s4" not in session_ids  # Subagent session excluded

    @pytest.mark.asyncio
    async def test_search_includes_subagents(
        self, db_with_sessions: SearchDatabase
    ) -> None:
        """Search includes subagent sessions when flag set."""
        results, total = await db_with_sessions.search(
            SearchFilters(include_subagents=True)
        )
        session_ids = {s.session_id for s in results}
        assert "s4" in session_ids  # Subagent session included
        assert total == 5

    @pytest.mark.asyncio
    async def test_search_pagination(self, db_with_sessions: SearchDatabase) -> None:
        """Search pagination with offset and limit."""
        # Get first 2
        results1, total = await db_with_sessions.search(SearchFilters(), limit=2, offset=0)
        assert len(results1) == 2
        assert total == 4  # Total unchanged by pagination

        # Get next 2
        results2, _ = await db_with_sessions.search(SearchFilters(), limit=2, offset=2)
        assert len(results2) == 2

        # No overlap
        ids1 = {s.session_id for s in results1}
        ids2 = {s.session_id for s in results2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_search_returns_total(self, db_with_sessions: SearchDatabase) -> None:
        """Search returns accurate total count."""
        results, total = await db_with_sessions.search(SearchFilters(), limit=2)
        assert len(results) == 2
        assert total == 4  # All non-subagent sessions


# ---------------------------------------------------------------------------
# Search sorting tests
# ---------------------------------------------------------------------------


class TestSearchSorting:
    """Tests for search sort options."""

    @pytest.fixture
    async def db_with_varied_sessions(self, tmp_path: Path) -> SearchDatabase:
        """Create database with sessions having varied attributes."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="recent",
                file_path="/path/recent.jsonl",
                summary="Recent session",
                project_display_name="alpha",
                file_modified_at=now - timedelta(hours=1),
                size_bytes=1000,
                duration_ms=30000,
            ),
            create_test_session(
                session_id="old",
                file_path="/path/old.jsonl",
                summary="Old session",
                project_display_name="zeta",
                file_modified_at=now - timedelta(days=30),
                size_bytes=5000,
                duration_ms=120000,
            ),
            create_test_session(
                session_id="medium",
                file_path="/path/medium.jsonl",
                summary="Medium session",
                project_display_name="beta",
                file_modified_at=now - timedelta(days=5),
                size_bytes=3000,
                duration_ms=60000,
            ),
        ]
        await db.upsert_sessions_batch(sessions)
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_search_sort_recent(
        self, db_with_varied_sessions: SearchDatabase
    ) -> None:
        """Sort by most recent first."""
        results, _ = await db_with_varied_sessions.search(SearchFilters(), sort="recent")
        assert results[0].session_id == "recent"
        assert results[-1].session_id == "old"

    @pytest.mark.asyncio
    async def test_search_sort_oldest(
        self, db_with_varied_sessions: SearchDatabase
    ) -> None:
        """Sort by oldest first."""
        results, _ = await db_with_varied_sessions.search(SearchFilters(), sort="oldest")
        assert results[0].session_id == "old"
        assert results[-1].session_id == "recent"

    @pytest.mark.asyncio
    async def test_search_sort_size(
        self, db_with_varied_sessions: SearchDatabase
    ) -> None:
        """Sort by size descending."""
        results, _ = await db_with_varied_sessions.search(SearchFilters(), sort="size")
        assert results[0].session_id == "old"  # 5000 bytes
        assert results[1].session_id == "medium"  # 3000 bytes
        assert results[2].session_id == "recent"  # 1000 bytes

    @pytest.mark.asyncio
    async def test_search_sort_duration(
        self, db_with_varied_sessions: SearchDatabase
    ) -> None:
        """Sort by duration descending."""
        results, _ = await db_with_varied_sessions.search(SearchFilters(), sort="duration")
        assert results[0].session_id == "old"  # 120000 ms
        assert results[1].session_id == "medium"  # 60000 ms
        assert results[2].session_id == "recent"  # 30000 ms

    @pytest.mark.asyncio
    async def test_search_sort_name(
        self, db_with_varied_sessions: SearchDatabase
    ) -> None:
        """Sort by project name ascending."""
        results, _ = await db_with_varied_sessions.search(SearchFilters(), sort="name")
        assert results[0].project_display_name == "alpha"
        assert results[1].project_display_name == "beta"
        assert results[2].project_display_name == "zeta"

    @pytest.mark.asyncio
    async def test_search_sort_duration_null(self, tmp_path: Path) -> None:
        """Sort by duration handles null values."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        sessions = [
            create_test_session(
                session_id="with_duration",
                file_path="/path/with.jsonl",
                duration_ms=60000,
            ),
            create_test_session(
                session_id="no_duration",
                file_path="/path/no.jsonl",
                duration_ms=None,
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        results, _ = await db.search(SearchFilters(), sort="duration")
        # Session with duration should come first
        assert results[0].session_id == "with_duration"

        await db.close()


# ---------------------------------------------------------------------------
# Search ranking tests
# ---------------------------------------------------------------------------


class TestSearchRanking:
    """Tests for search ranking algorithm."""

    @pytest.fixture
    async def db_for_ranking(self, tmp_path: Path) -> SearchDatabase:
        """Create database with sessions for ranking tests."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="summary_match",
                file_path="/path/summary_match.jsonl",
                summary="Fix authentication bug in login flow",
                project_display_name="backend",
                file_modified_at=now - timedelta(days=15),
            ),
            create_test_session(
                session_id="project_match",
                file_path="/path/project_match.jsonl",
                summary="Add new feature",
                project_display_name="auth-service",
                file_modified_at=now - timedelta(days=15),
            ),
            create_test_session(
                session_id="recent_match",
                file_path="/path/recent_match.jsonl",
                summary="Debug auth issues",
                project_display_name="api",
                file_modified_at=now,  # Today
            ),
            create_test_session(
                session_id="no_match",
                file_path="/path/no_match.jsonl",
                summary="Update docs",
                project_display_name="docs",
                file_modified_at=now - timedelta(days=15),
            ),
            create_test_session(
                session_id="exact_phrase",
                file_path="/path/exact_phrase.jsonl",
                summary="auth bug in login system",
                project_display_name="web",
                file_modified_at=now - timedelta(days=15),
            ),
        ]
        await db.upsert_sessions_batch(sessions)
        yield db
        await db.close()

    @pytest.mark.asyncio
    async def test_ranking_summary_match(self, db_for_ranking: SearchDatabase) -> None:
        """Summary match adds 2.0 per term."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="authentication"))
        # Should find session with "authentication" in summary
        session_ids = [r.session.session_id for r in results]
        assert "summary_match" in session_ids

        # Check score
        for r in results:
            if r.session.session_id == "summary_match":
                # 2.0 for "authentication" + recency boost
                assert r.score >= 2.0

    @pytest.mark.asyncio
    async def test_ranking_exact_phrase(self, db_for_ranking: SearchDatabase) -> None:
        """Exact phrase adds 1.0 bonus."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="auth bug"))

        # Find the exact phrase match session
        exact_match = next(
            (r for r in results if r.session.session_id == "exact_phrase"), None
        )
        assert exact_match is not None
        # 2.0 for "auth" + 2.0 for "bug" + 1.0 for exact phrase + recency
        assert exact_match.score >= 5.0

    @pytest.mark.asyncio
    async def test_ranking_project_match(self, db_for_ranking: SearchDatabase) -> None:
        """Project name match adds 1.0 per term."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="auth"))

        # Find the project match session
        project_match = next(
            (r for r in results if r.session.session_id == "project_match"), None
        )
        assert project_match is not None
        # 1.0 for "auth" in project name + recency boost
        assert project_match.score >= 1.0

    @pytest.mark.asyncio
    async def test_ranking_recency_boost(self, db_for_ranking: SearchDatabase) -> None:
        """Today's session adds 1.0, old sessions add less."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="auth"))

        # Find the recent match session
        recent_match = next(
            (r for r in results if r.session.session_id == "recent_match"), None
        )
        assert recent_match is not None
        # Should have nearly 1.0 recency boost (today)
        # 2.0 for "auth" in summary + ~1.0 recency = ~3.0
        assert recent_match.score >= 2.9

    @pytest.mark.asyncio
    async def test_ranking_recency_decay(self, db_for_ranking: SearchDatabase) -> None:
        """30 days old adds 0.0 recency boost."""
        db = db_for_ranking

        now = datetime.now(timezone.utc)
        old_session = create_test_session(
            session_id="very_old",
            file_path="/path/very_old.jsonl",
            summary="authentication check",
            project_display_name="myproject",
            file_modified_at=now - timedelta(days=30),
        )
        await db.upsert_session(old_session)

        results, _ = await db.search_ranked(SearchFilters(query="authentication"))

        very_old = next(
            (r for r in results if r.session.session_id == "very_old"), None
        )
        assert very_old is not None
        # 2.0 for "authentication" term match + 1.0 exact phrase bonus + 0.0 recency = 3.0
        assert very_old.score == pytest.approx(3.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_ranking_combined(self, db_for_ranking: SearchDatabase) -> None:
        """All ranking factors combine correctly."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="auth bug"))

        # exact_phrase should have highest score
        # 2.0 * 2 (two terms in summary) + 1.0 (exact phrase) + recency
        scores = {r.session.session_id: r.score for r in results}

        # Verify exact phrase match scores highest
        if "exact_phrase" in scores:
            for sid, score in scores.items():
                if sid != "exact_phrase":
                    assert scores["exact_phrase"] >= score

    @pytest.mark.asyncio
    async def test_ranking_order(self, db_for_ranking: SearchDatabase) -> None:
        """Results are ordered by score descending."""
        results, _ = await db_for_ranking.search_ranked(SearchFilters(query="auth"))

        # Verify scores are in descending order
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_ranking_tiebreaker(self, tmp_path: Path) -> None:
        """Same score sorted by date (tiebreaker)."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        # Create sessions with same words but different dates
        sessions = [
            create_test_session(
                session_id="older",
                file_path="/path/older.jsonl",
                summary="test word",
                project_display_name="app",
                file_modified_at=now - timedelta(days=15),
            ),
            create_test_session(
                session_id="newer",
                file_path="/path/newer.jsonl",
                summary="test word",
                project_display_name="app",
                file_modified_at=now - timedelta(days=14),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        results, _ = await db.search_ranked(SearchFilters(query="test"))

        # Newer should come first (tiebreaker by date)
        assert results[0].session.session_id == "newer"

        await db.close()

    @pytest.mark.asyncio
    async def test_ranking_no_query(self, db_for_ranking: SearchDatabase) -> None:
        """No query returns results by recency with score 0."""
        results, total = await db_for_ranking.search_ranked(SearchFilters())

        assert total > 0
        for result in results:
            assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_ranking_pagination(self, db_for_ranking: SearchDatabase) -> None:
        """Ranked search supports pagination."""
        all_results, total = await db_for_ranking.search_ranked(
            SearchFilters(query="auth"), limit=10
        )

        if total >= 2:
            # Get first result
            first_result, _ = await db_for_ranking.search_ranked(
                SearchFilters(query="auth"), limit=1, offset=0
            )
            # Get second result
            second_result, _ = await db_for_ranking.search_ranked(
                SearchFilters(query="auth"), limit=1, offset=1
            )

            assert first_result[0].session.session_id == all_results[0].session.session_id
            assert second_result[0].session.session_id == all_results[1].session.session_id


# ---------------------------------------------------------------------------
# Search edge cases and integration tests
# ---------------------------------------------------------------------------


class TestSearchEdgeCases:
    """Tests for search edge cases."""

    @pytest.mark.asyncio
    async def test_search_empty_database(self, tmp_path: Path) -> None:
        """Search on empty database returns empty results."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        results, total = await db.search(SearchFilters())
        assert results == []
        assert total == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_search_no_matches(self, tmp_path: Path) -> None:
        """Search with no matching results."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Python programming",
            )
        )

        results, total = await db.search(SearchFilters(query="javascript"))
        assert total == 0
        assert results == []

        await db.close()

    @pytest.mark.asyncio
    async def test_search_null_summary(self, tmp_path: Path) -> None:
        """Search handles sessions with null summary."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="no_summary",
                file_path="/path/no_summary.jsonl",
                summary=None,
                project_display_name="uniqueproject",
            )
        )

        # Should match on project name
        results, total = await db.search(SearchFilters(query="uniqueproject"))
        assert total == 1
        assert results[0].session_id == "no_summary"

        await db.close()

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, tmp_path: Path) -> None:
        """Search is case-insensitive."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="mixed_case",
                file_path="/path/mixed.jsonl",
                summary="Authentication Bug Fix",
            )
        )

        # Lowercase query should match
        results, _ = await db.search(SearchFilters(query="authentication"))
        assert len(results) == 1

        # Uppercase query should match
        results, _ = await db.search(SearchFilters(query="AUTHENTICATION"))
        assert len(results) == 1

        await db.close()

    @pytest.mark.asyncio
    async def test_search_ranked_no_positive_scores(self, tmp_path: Path) -> None:
        """Ranked search with no matches returns empty."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                summary="Python programming",
                project_display_name="backend",
            )
        )

        # Query that won't match
        results, total = await db.search_ranked(SearchFilters(query="javascript"))
        assert total == 0
        assert results == []

        await db.close()

    @pytest.mark.asyncio
    async def test_search_multiple_terms(self, tmp_path: Path) -> None:
        """Search with multiple terms uses OR logic."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        sessions = [
            create_test_session(
                session_id="has_auth",
                file_path="/path/auth.jsonl",
                summary="Fix authentication issue",
            ),
            create_test_session(
                session_id="has_bug",
                file_path="/path/bug.jsonl",
                summary="Fix UI bug",
            ),
            create_test_session(
                session_id="has_neither",
                file_path="/path/neither.jsonl",
                summary="Update docs",
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        # Multi-term query should match sessions with either term
        results, total = await db.search(SearchFilters(query="auth bug"))
        session_ids = {r.session_id for r in results}

        assert "has_auth" in session_ids
        assert "has_bug" in session_ids
        assert "has_neither" not in session_ids

        await db.close()


# ---------------------------------------------------------------------------
# Integration tests for search with real sessions
# ---------------------------------------------------------------------------


class TestSearchIntegration:
    """Integration tests for search functionality."""

    @pytest.mark.asyncio
    async def test_search_real_sessions(self, tmp_path: Path) -> None:
        """Search against a populated database with realistic data."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        # Create realistic session data
        sessions = [
            create_test_session(
                session_id="uuid-001",
                file_path=f"{tmp_path}/projects/trello/uuid-001.jsonl",
                summary="Implement user authentication flow with JWT tokens",
                project_display_name="trello",
                file_modified_at=now - timedelta(days=1),
                size_bytes=5000,
                duration_ms=1800000,
            ),
            create_test_session(
                session_id="uuid-002",
                file_path=f"{tmp_path}/projects/trello/uuid-002.jsonl",
                summary="Fix bug in card drag and drop functionality",
                project_display_name="trello",
                file_modified_at=now - timedelta(days=3),
                size_bytes=3000,
                duration_ms=900000,
            ),
            create_test_session(
                session_id="uuid-003",
                file_path=f"{tmp_path}/projects/api/uuid-003.jsonl",
                summary="Add rate limiting to API endpoints",
                project_display_name="api-server",
                file_modified_at=now - timedelta(days=5),
                size_bytes=4000,
                duration_ms=1200000,
            ),
            create_test_session(
                session_id="uuid-004",
                file_path=f"{tmp_path}/projects/api/uuid-004.jsonl",
                summary="Debug authentication middleware issue",
                project_display_name="api-server",
                file_modified_at=now - timedelta(days=7),
                size_bytes=6000,
                duration_ms=2400000,
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        # Search for auth-related sessions (using full word that FTS5 can match)
        results, total = await db.search(SearchFilters(query="authentication"))
        assert total == 2
        session_ids = {r.session_id for r in results}
        assert "uuid-001" in session_ids
        assert "uuid-004" in session_ids

        # Search within specific project
        results, total = await db.search(
            SearchFilters(query="authentication", project="api")
        )
        assert total == 1
        assert results[0].session_id == "uuid-004"

        await db.close()

    @pytest.mark.asyncio
    async def test_ranking_real_sessions(self, tmp_path: Path) -> None:
        """Ranking produces expected order with realistic data."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        # Create sessions with different relevance characteristics
        sessions = [
            # High relevance: exact phrase, recent
            create_test_session(
                session_id="best_match",
                file_path=f"{tmp_path}/best.jsonl",
                summary="Fix authentication bug in login flow",
                project_display_name="auth-service",
                file_modified_at=now - timedelta(hours=2),
            ),
            # Medium relevance: partial match, older
            create_test_session(
                session_id="partial_match",
                file_path=f"{tmp_path}/partial.jsonl",
                summary="Update authentication tests",
                project_display_name="backend",
                file_modified_at=now - timedelta(days=10),
            ),
            # Low relevance: project name only
            create_test_session(
                session_id="project_only",
                file_path=f"{tmp_path}/project.jsonl",
                summary="Add new feature",
                project_display_name="auth-utils",
                file_modified_at=now - timedelta(days=20),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        results, _ = await db.search_ranked(SearchFilters(query="authentication bug"))

        # Best match should be first (exact phrase + recent + summary match)
        assert results[0].session.session_id == "best_match"

        # Verify ordering
        assert results[0].score > results[1].score

        await db.close()


# ---------------------------------------------------------------------------
# Aggregation query tests - get_projects
# ---------------------------------------------------------------------------


class TestGetProjects:
    """Tests for get_projects() aggregation query."""

    @pytest.mark.asyncio
    async def test_get_projects_empty(self, tmp_path: Path) -> None:
        """Returns empty list for empty DB."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        projects = await db.get_projects()
        assert projects == []

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_single(self, tmp_path: Path) -> None:
        """One project with counts."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                project_encoded="-Users-user-work-trello",
                project_display_name="trello",
                project_path="/Users/user/work/trello",
                size_bytes=1000,
            )
        )

        projects = await db.get_projects()

        assert len(projects) == 1
        assert projects[0]["project_display_name"] == "trello"
        assert projects[0]["project_encoded"] == "-Users-user-work-trello"
        assert projects[0]["project_path"] == "/Users/user/work/trello"
        assert projects[0]["session_count"] == 1
        assert projects[0]["total_size_bytes"] == 1000

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_multiple(self, tmp_path: Path) -> None:
        """Multiple projects sorted by date."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                file_modified_at=now - timedelta(days=2),
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                project_encoded="-api",
                project_display_name="api",
                project_path="/api",
                file_modified_at=now - timedelta(days=1),
            ),
            create_test_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                project_encoded="-docs",
                project_display_name="docs",
                project_path="/docs",
                file_modified_at=now - timedelta(days=3),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        projects = await db.get_projects()

        assert len(projects) == 3
        # Should be sorted by latest_modified_at DESC
        assert projects[0]["project_display_name"] == "api"  # Most recent
        assert projects[1]["project_display_name"] == "trello"
        assert projects[2]["project_display_name"] == "docs"  # Oldest

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_aggregation(self, tmp_path: Path) -> None:
        """Counts and totals correct."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                file_modified_at=now - timedelta(days=1),
                size_bytes=1000,
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                file_modified_at=now,
                size_bytes=2000,
            ),
            create_test_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                project_encoded="-api",
                project_display_name="api",
                project_path="/api",
                file_modified_at=now - timedelta(days=2),
                size_bytes=500,
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        projects = await db.get_projects()

        assert len(projects) == 2

        # trello should be first (more recent)
        trello = projects[0]
        assert trello["project_display_name"] == "trello"
        assert trello["session_count"] == 2
        assert trello["total_size_bytes"] == 3000  # 1000 + 2000

        api = projects[1]
        assert api["project_display_name"] == "api"
        assert api["session_count"] == 1
        assert api["total_size_bytes"] == 500

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_excludes_subagents(self, tmp_path: Path) -> None:
        """Subagent sessions not counted."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        sessions = [
            create_test_session(
                session_id="main",
                file_path="/path/main.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                is_subagent=False,
                size_bytes=1000,
            ),
            create_test_session(
                session_id="subagent",
                file_path="/path/subagent.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                is_subagent=True,
                size_bytes=500,
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        projects = await db.get_projects()

        assert len(projects) == 1
        assert projects[0]["session_count"] == 1  # Only main session
        assert projects[0]["total_size_bytes"] == 1000  # Only main session size

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_since_filter(self, tmp_path: Path) -> None:
        """Date filter works - since."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="recent",
                file_path="/path/recent.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                file_modified_at=now - timedelta(days=1),
            ),
            create_test_session(
                session_id="old",
                file_path="/path/old.jsonl",
                project_encoded="-api",
                project_display_name="api",
                project_path="/api",
                file_modified_at=now - timedelta(days=10),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        # Filter: since 5 days ago
        since = now - timedelta(days=5)
        projects = await db.get_projects(since=since)

        assert len(projects) == 1
        assert projects[0]["project_display_name"] == "trello"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_until_filter(self, tmp_path: Path) -> None:
        """Date filter works - until."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="recent",
                file_path="/path/recent.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                file_modified_at=now - timedelta(days=1),
            ),
            create_test_session(
                session_id="old",
                file_path="/path/old.jsonl",
                project_encoded="-api",
                project_display_name="api",
                project_path="/api",
                file_modified_at=now - timedelta(days=10),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        # Filter: until 5 days ago
        until = now - timedelta(days=5)
        projects = await db.get_projects(until=until)

        assert len(projects) == 1
        assert projects[0]["project_display_name"] == "api"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_projects_both_filters(self, tmp_path: Path) -> None:
        """Date filters work together."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        now = datetime.now(timezone.utc)

        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                project_encoded="-recent",
                project_display_name="recent",
                project_path="/recent",
                file_modified_at=now - timedelta(days=1),
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                project_encoded="-mid",
                project_display_name="mid",
                project_path="/mid",
                file_modified_at=now - timedelta(days=5),
            ),
            create_test_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                project_encoded="-old",
                project_display_name="old",
                project_path="/old",
                file_modified_at=now - timedelta(days=15),
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        # Filter: between 3 and 10 days ago
        since = now - timedelta(days=10)
        until = now - timedelta(days=3)
        projects = await db.get_projects(since=since, until=until)

        assert len(projects) == 1
        assert projects[0]["project_display_name"] == "mid"

        await db.close()


# ---------------------------------------------------------------------------
# Aggregation query tests - get_stats
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests for get_stats() aggregation query."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, tmp_path: Path) -> None:
        """Returns zeros for empty DB."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        stats = await db.get_stats()

        assert stats["total_sessions"] == 0
        assert stats["total_projects"] == 0
        assert stats["total_size_bytes"] == 0
        assert isinstance(stats["fts_available"], bool)
        # Metadata may be empty string or None
        assert stats["last_full_index"] is None or stats["last_full_index"] == ""
        assert (
            stats["last_incremental_index"] is None
            or stats["last_incremental_index"] == ""
        )

        await db.close()

    @pytest.mark.asyncio
    async def test_get_stats_populated(self, tmp_path: Path) -> None:
        """Returns correct counts."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        sessions = [
            create_test_session(
                session_id="s1",
                file_path="/path/s1.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                size_bytes=1000,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s2",
                file_path="/path/s2.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                size_bytes=2000,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s3",
                file_path="/path/s3.jsonl",
                project_encoded="-api",
                project_display_name="api",
                project_path="/api",
                size_bytes=500,
                is_subagent=False,
            ),
            create_test_session(
                session_id="s4",
                file_path="/path/s4.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                size_bytes=300,
                is_subagent=True,  # Subagent - excluded from session count
            ),
        ]
        await db.upsert_sessions_batch(sessions)

        stats = await db.get_stats()

        assert stats["total_sessions"] == 3  # Excludes subagent
        assert stats["total_projects"] == 2  # trello and api
        assert stats["total_size_bytes"] == 3800  # All sessions including subagent

        await db.close()

    @pytest.mark.asyncio
    async def test_get_stats_includes_metadata(self, tmp_path: Path) -> None:
        """FTS status and timestamps included."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        # Set some metadata
        await db._set_metadata("last_full_index", "2024-01-15T10:30:00+00:00")
        await db._set_metadata("last_incremental_index", "2024-01-16T14:00:00+00:00")

        stats = await db.get_stats()

        assert isinstance(stats["fts_available"], bool)
        assert stats["last_full_index"] == "2024-01-15T10:30:00+00:00"
        assert stats["last_incremental_index"] == "2024-01-16T14:00:00+00:00"

        await db.close()

    @pytest.mark.asyncio
    async def test_get_stats_only_subagents(self, tmp_path: Path) -> None:
        """Only subagent sessions returns zero session count but includes size."""
        db = SearchDatabase(tmp_path)
        await db.initialize()

        await db.upsert_session(
            create_test_session(
                session_id="subagent",
                file_path="/path/subagent.jsonl",
                project_encoded="-trello",
                project_display_name="trello",
                project_path="/trello",
                size_bytes=1000,
                is_subagent=True,
            )
        )

        stats = await db.get_stats()

        assert stats["total_sessions"] == 0  # No main sessions
        assert stats["total_projects"] == 1  # Still counts project
        assert stats["total_size_bytes"] == 1000  # Size is counted

        await db.close()
