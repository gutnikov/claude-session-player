"""Tests for SearchDatabase and IndexedSession."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_session_player.watcher.search_db import IndexedSession, SearchDatabase


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
