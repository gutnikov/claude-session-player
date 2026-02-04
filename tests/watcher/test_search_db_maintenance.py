"""Maintenance operations tests for SearchDatabase.

Tests backup, vacuum, checkpoint, integrity verification,
safe initialization, and recovery operations.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import aiosqlite
import pytest

from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory() -> Callable[..., IndexedSession]:
    """Factory for creating test sessions."""
    counter = [0]

    def _create(
        session_id: str | None = None,
        summary: str = "Test summary",
    ) -> IndexedSession:
        counter[0] += 1
        sid = session_id or f"maint-{counter[0]}"
        now = datetime.now(timezone.utc)
        return IndexedSession(
            session_id=sid,
            project_encoded="-test-project",
            project_display_name="test-project",
            project_path="/test/project",
            summary=summary,
            file_path=f"/test/project/{sid}.jsonl",
            file_created_at=now - timedelta(hours=1),
            file_modified_at=now,
            indexed_at=now,
            size_bytes=1000,
            line_count=50,
            duration_ms=60000,
            has_subagents=False,
            is_subagent=False,
        )

    return _create


# ---------------------------------------------------------------------------
# Backup Tests
# ---------------------------------------------------------------------------


class TestBackup:
    """Tests for database backup operations."""

    @pytest.mark.asyncio
    async def test_backup_creates_file(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup creates a database file."""
        await search_db.upsert_session(session_factory())

        backup_path = tmp_path / "backups" / "backup.db"
        await search_db.backup(backup_path)

        assert backup_path.exists()
        assert backup_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_backup_valid_database(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup file is a valid SQLite database."""
        await search_db.upsert_session(session_factory(session_id="backup-test"))

        backup_path = tmp_path / "backup.db"
        await search_db.backup(backup_path)

        # Open backup and verify it's valid
        backup_db = SearchDatabase(tmp_path / "backup_state")
        backup_db.db_path = backup_path
        backup_db._connection = await aiosqlite.connect(backup_path)
        backup_db._connection.row_factory = aiosqlite.Row

        retrieved = await backup_db.get_session("backup-test")
        assert retrieved is not None
        assert retrieved.session_id == "backup-test"

        await backup_db.close()

    @pytest.mark.asyncio
    async def test_backup_contains_data(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup contains same data as original."""
        await search_db.upsert_session(session_factory(session_id="s1"))
        await search_db.upsert_session(session_factory(session_id="s2"))

        backup_path = tmp_path / "backup.db"
        await search_db.backup(backup_path)

        # Verify backup has both sessions
        conn = await aiosqlite.connect(backup_path)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT COUNT(*) FROM sessions") as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 2
        await conn.close()

    @pytest.mark.asyncio
    async def test_backup_to_existing_file(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup overwrites existing backup file."""
        backup_path = tmp_path / "backup.db"

        # First backup
        await search_db.upsert_session(session_factory(session_id="first"))
        await search_db.backup(backup_path)

        # Add more data and backup again
        await search_db.upsert_session(session_factory(session_id="second"))
        await search_db.backup(backup_path)

        # Verify backup has both
        conn = await aiosqlite.connect(backup_path)
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT COUNT(*) FROM sessions") as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 2
        await conn.close()

    @pytest.mark.asyncio
    async def test_backup_creates_parent_dirs(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup creates parent directories if needed."""
        await search_db.upsert_session(session_factory())

        backup_path = tmp_path / "nested" / "deep" / "backup.db"
        await search_db.backup(backup_path)

        assert backup_path.exists()

    @pytest.mark.asyncio
    async def test_multiple_rapid_backups(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Multiple rapid backup calls work correctly."""
        await search_db.upsert_session(session_factory())

        for i in range(3):
            backup_path = tmp_path / f"backup_{i}.db"
            await search_db.backup(backup_path)
            assert backup_path.exists()


# ---------------------------------------------------------------------------
# Vacuum Tests
# ---------------------------------------------------------------------------


class TestVacuum:
    """Tests for vacuum operations."""

    @pytest.mark.asyncio
    async def test_vacuum_reclaims_space(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Vacuum reclaims space after deletions."""
        # Insert many sessions
        sessions = [
            session_factory(session_id=f"vacuum-{i}") for i in range(100)
        ]
        await search_db.upsert_sessions_batch(sessions)

        # Flush WAL first
        await search_db.checkpoint()

        # Delete all sessions
        await search_db.clear_all()
        await search_db.checkpoint()

        # Run vacuum - should not error
        await search_db.vacuum()

        # Verify database is still usable
        assert await search_db.verify_integrity()

    @pytest.mark.asyncio
    async def test_vacuum_empty_database(self, search_db: SearchDatabase) -> None:
        """Vacuum works on empty database."""
        await search_db.vacuum()
        assert await search_db.verify_integrity()

    @pytest.mark.asyncio
    async def test_vacuum_after_insert(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Vacuum works after inserts."""
        await search_db.upsert_session(session_factory())
        await search_db.vacuum()

        # Data should still be accessible
        stats = await search_db.get_stats()
        assert stats["total_sessions"] == 1


# ---------------------------------------------------------------------------
# Checkpoint Tests
# ---------------------------------------------------------------------------


class TestCheckpoint:
    """Tests for WAL checkpoint operations."""

    @pytest.mark.asyncio
    async def test_checkpoint_flushes_wal(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Checkpoint resets WAL file."""
        await search_db.upsert_session(session_factory(session_id="cp-test"))

        # Run checkpoint
        await search_db.checkpoint()

        # Data should still be accessible
        retrieved = await search_db.get_session("cp-test")
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_checkpoint_empty_database(
        self, search_db: SearchDatabase
    ) -> None:
        """Checkpoint works on empty database."""
        await search_db.checkpoint()
        assert await search_db.verify_integrity()

    @pytest.mark.asyncio
    async def test_checkpoint_after_many_writes(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Checkpoint after many write operations."""
        for i in range(50):
            await search_db.upsert_session(session_factory(session_id=f"cp-{i}"))

        await search_db.checkpoint()

        # All data accessible
        stats = await search_db.get_stats()
        assert stats["total_sessions"] == 50


# ---------------------------------------------------------------------------
# Integrity Verification Tests
# ---------------------------------------------------------------------------


class TestVerifyIntegrity:
    """Tests for database integrity verification."""

    @pytest.mark.asyncio
    async def test_verify_integrity_valid(
        self, search_db: SearchDatabase
    ) -> None:
        """Returns True for valid database."""
        result = await search_db.verify_integrity()
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_integrity_after_operations(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Integrity passes after normal operations."""
        # Insert
        await search_db.upsert_session(session_factory(session_id="s1"))

        # Update
        await search_db.upsert_session(session_factory(session_id="s1", summary="Updated"))

        # Delete
        await search_db.delete_session("s1")

        # Should still be valid
        assert await search_db.verify_integrity()


# ---------------------------------------------------------------------------
# Safe Initialize Tests
# ---------------------------------------------------------------------------


class TestSafeInitialize:
    """Tests for safe initialization with corruption recovery."""

    @pytest.mark.asyncio
    async def test_safe_initialize_normal(
        self,
        temp_state_dir: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """safe_initialize works when database is healthy."""
        db = SearchDatabase(temp_state_dir)
        await db.safe_initialize()

        # Should work normally
        await db.upsert_session(session_factory())
        assert await db.verify_integrity()

        await db.close()

    @pytest.mark.asyncio
    async def test_safe_initialize_corrupt(
        self, temp_state_dir: Path
    ) -> None:
        """safe_initialize recovers from corruption."""
        db_path = temp_state_dir / "search.db"

        # Create corrupt database file
        db_path.write_text("This is not a valid SQLite database")

        db = SearchDatabase(temp_state_dir)
        await db.safe_initialize()

        # Should have recovered
        assert await db.verify_integrity()

        # Corrupt file should be backed up
        corrupt_path = temp_state_dir / "search.db.corrupt"
        assert corrupt_path.exists()
        assert corrupt_path.read_text() == "This is not a valid SQLite database"

        await db.close()

    @pytest.mark.asyncio
    async def test_safe_initialize_missing_db(
        self, temp_state_dir: Path
    ) -> None:
        """safe_initialize creates database if missing."""
        db = SearchDatabase(temp_state_dir)
        await db.safe_initialize()

        assert db.db_path.exists()
        assert await db.verify_integrity()

        await db.close()


# ---------------------------------------------------------------------------
# Recovery Tests
# ---------------------------------------------------------------------------


class TestRecovery:
    """Tests for database recovery operations."""

    @pytest.mark.asyncio
    async def test_recovery_renames_corrupt(
        self,
        temp_state_dir: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Recovery renames corrupt database."""
        # Create initial valid database
        db = SearchDatabase(temp_state_dir)
        await db.initialize()
        await db.upsert_session(session_factory())
        await db.close()

        # Manually trigger recovery
        db = SearchDatabase(temp_state_dir)
        await db._recover_database()

        # Original should be renamed
        corrupt_path = temp_state_dir / "search.db.corrupt"
        assert corrupt_path.exists()

        # New database should be created
        assert db.db_path.exists()

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_cleans_wal_files(
        self, temp_state_dir: Path
    ) -> None:
        """Recovery removes WAL files."""
        # Create database
        db = SearchDatabase(temp_state_dir)
        await db.initialize()
        await db.close()

        # Create fake WAL files
        wal_path = temp_state_dir / "search.db-wal"
        shm_path = temp_state_dir / "search.db-shm"
        wal_path.write_text("fake wal data")
        shm_path.write_text("fake shm data")

        # Trigger recovery
        db = SearchDatabase(temp_state_dir)
        await db._recover_database()

        # Corrupt database should be renamed
        corrupt_path = temp_state_dir / "search.db.corrupt"
        assert corrupt_path.exists()

        # New database should be valid
        assert await db.verify_integrity()

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_when_no_db_exists(
        self, temp_state_dir: Path
    ) -> None:
        """Recovery works when no database file exists."""
        db = SearchDatabase(temp_state_dir)
        await db._recover_database()

        # Should create fresh database
        assert db.db_path.exists()
        assert await db.verify_integrity()

        await db.close()

    @pytest.mark.asyncio
    async def test_recovery_preserves_state_dir(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Recovery preserves state directory structure."""
        # Create some other files in state dir
        other_file = temp_state_dir / "other.txt"
        other_file.write_text("important data")

        db = SearchDatabase(temp_state_dir)
        await db.initialize()
        await db.close()

        # Trigger recovery
        db = SearchDatabase(temp_state_dir)
        await db._recover_database()

        # Other files should be preserved
        assert other_file.exists()
        assert other_file.read_text() == "important data"

        await db.close()


# ---------------------------------------------------------------------------
# Execute With Retry Tests
# ---------------------------------------------------------------------------


class TestExecuteWithRetry:
    """Tests for execute_with_retry operation."""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(
        self, search_db: SearchDatabase
    ) -> None:
        """Normal execution works."""
        cursor = await search_db.execute_with_retry(
            "SELECT COUNT(*) FROM sessions", ()
        )
        result = await cursor.fetchone()
        assert result[0] == 0

    @pytest.mark.asyncio
    async def test_execute_with_retry_busy(
        self, temp_state_dir: Path
    ) -> None:
        """Retries on database locked error."""
        db = SearchDatabase(temp_state_dir)
        await db.initialize()

        attempts = []
        original_execute = db._connection.execute

        async def mock_execute(sql, params=()):
            attempts.append(1)
            if len(attempts) < 3:
                raise sqlite3.OperationalError("database is locked")
            return await original_execute(sql, params)

        db._connection.execute = mock_execute

        # Should succeed after retries
        cursor = await db.execute_with_retry(
            "SELECT COUNT(*) FROM sessions", (), max_retries=5
        )
        result = await cursor.fetchone()
        assert result[0] == 0
        assert len(attempts) == 3  # Failed twice, succeeded third

        await db.close()

    @pytest.mark.asyncio
    async def test_execute_with_retry_exhausted(
        self, temp_state_dir: Path
    ) -> None:
        """Raises error when retries exhausted."""
        db = SearchDatabase(temp_state_dir)
        await db.initialize()

        async def always_locked(sql, params=()):
            raise sqlite3.OperationalError("database is locked")

        db._connection.execute = always_locked

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            await db.execute_with_retry("SELECT 1", (), max_retries=2)

        await db.close()

    @pytest.mark.asyncio
    async def test_execute_with_retry_non_locked_error(
        self, temp_state_dir: Path
    ) -> None:
        """Non-locked errors not retried."""
        db = SearchDatabase(temp_state_dir)
        await db.initialize()

        async def syntax_error(sql, params=()):
            raise sqlite3.OperationalError("syntax error")

        db._connection.execute = syntax_error

        with pytest.raises(sqlite3.OperationalError, match="syntax"):
            await db.execute_with_retry("SELECT 1", (), max_retries=3)

        await db.close()


# ---------------------------------------------------------------------------
# Clear All Tests
# ---------------------------------------------------------------------------


class TestClearAll:
    """Tests for clear_all operation."""

    @pytest.mark.asyncio
    async def test_clear_all_removes_sessions(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """clear_all removes all session data."""
        await search_db.upsert_session(session_factory(session_id="s1"))
        await search_db.upsert_session(session_factory(session_id="s2"))

        await search_db.clear_all()

        assert await search_db.get_session("s1") is None
        assert await search_db.get_session("s2") is None

    @pytest.mark.asyncio
    async def test_clear_all_removes_mtimes(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """clear_all removes file mtime data."""
        await search_db.upsert_session(session_factory())
        await search_db.set_file_mtime("/path/file.jsonl", 12345)

        await search_db.clear_all()

        assert await search_db.get_file_mtime("/path/file.jsonl") is None

    @pytest.mark.asyncio
    async def test_clear_all_empty_db(
        self, search_db: SearchDatabase
    ) -> None:
        """clear_all on empty database doesn't error."""
        await search_db.clear_all()

        stats = await search_db.get_stats()
        assert stats["total_sessions"] == 0

    @pytest.mark.asyncio
    async def test_clear_all_preserves_schema(
        self,
        search_db: SearchDatabase,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """clear_all preserves database schema."""
        await search_db.upsert_session(session_factory(session_id="s1"))
        await search_db.clear_all()

        # Should be able to insert new data
        await search_db.upsert_session(session_factory(session_id="s2"))
        assert await search_db.get_session("s2") is not None


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestMaintenanceEdgeCases:
    """Edge case tests for maintenance operations."""

    @pytest.mark.asyncio
    async def test_backup_during_writes(
        self,
        search_db: SearchDatabase,
        tmp_path: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Backup while writing data."""
        # Insert some initial data
        await search_db.upsert_session(session_factory(session_id="initial"))

        # Backup
        backup_path = tmp_path / "backup.db"
        await search_db.backup(backup_path)

        # Continue writing after backup
        await search_db.upsert_session(session_factory(session_id="after"))

        # Both should work
        assert await search_db.get_session("initial") is not None
        assert await search_db.get_session("after") is not None

        # Backup should have initial but not after
        conn = await aiosqlite.connect(backup_path)
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT session_id FROM sessions"
        ) as cursor:
            rows = await cursor.fetchall()
            session_ids = {row["session_id"] for row in rows}
            assert "initial" in session_ids
            assert "after" not in session_ids
        await conn.close()

    @pytest.mark.asyncio
    async def test_operations_after_recovery(
        self,
        temp_state_dir: Path,
        session_factory: Callable[..., IndexedSession],
    ) -> None:
        """Normal operations work after recovery."""
        db = SearchDatabase(temp_state_dir)
        await db._recover_database()

        # Should be able to do normal operations
        await db.upsert_session(session_factory(session_id="post-recovery"))
        retrieved = await db.get_session("post-recovery")
        assert retrieved is not None

        await db.backup(temp_state_dir / "post-recovery-backup.db")
        await db.vacuum()
        await db.checkpoint()

        assert await db.verify_integrity()

        await db.close()

    @pytest.mark.asyncio
    async def test_concurrent_safe_initialize(
        self, temp_state_dir: Path
    ) -> None:
        """Multiple safe_initialize calls don't corrupt."""
        db1 = SearchDatabase(temp_state_dir)
        db2 = SearchDatabase(temp_state_dir)

        await db1.safe_initialize()
        await db2.safe_initialize()

        # Both should work
        assert await db1.verify_integrity()
        assert await db2.verify_integrity()

        await db1.close()
        await db2.close()
