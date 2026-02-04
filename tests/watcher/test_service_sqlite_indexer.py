"""Tests for SQLite indexer integration in WatcherService."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.config import (
    BackupConfig,
    ConfigManager,
    DatabaseConfig,
    IndexConfig,
)
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.indexer import SQLiteSessionIndexer
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEManager


# --- Fixtures ---


@pytest.fixture
def temp_config_path(tmp_path: Path) -> Path:
    """Create a temporary config file path."""
    return tmp_path / "config.yaml"


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def db_state_dir(tmp_path: Path) -> Path:
    """Create a temporary database state directory."""
    db_dir = tmp_path / "db_state"
    db_dir.mkdir()
    return db_dir


@pytest.fixture
def backup_dir(tmp_path: Path) -> Path:
    """Create a temporary backup directory."""
    backup = tmp_path / "backups"
    backup.mkdir()
    return backup


# --- TestSQLiteIndexerInitialization ---


class TestSQLiteIndexerInitialization:
    """Tests for SQLite indexer initialization in WatcherService."""

    def test_sqlite_indexer_created_on_service_init(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """SQLite indexer is created when service is created."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.sqlite_indexer is not None

    def test_sqlite_indexer_uses_database_config(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """SQLite indexer uses database config for state_dir."""
        # Create config with custom database settings
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(state_dir=str(db_state_dir))
        config_manager.set_database_config(db_config)
        config_manager.save([])  # Save to persist the database config

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            config_manager=config_manager,  # Use the config manager we set up
        )

        # The indexer should use the db_state_dir from config
        assert service.sqlite_indexer.state_dir == db_state_dir

    def test_both_indexers_created(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Both legacy and SQLite indexers are created."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.indexer is not None
        assert service.sqlite_indexer is not None


# --- TestServiceBuildIndex ---


class TestServiceBuildIndex:
    """Tests for index building during service startup."""

    async def test_index_built_on_first_start(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Index is built on first start when empty."""
        # Create config with database settings
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(state_dir=str(db_state_dir))
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={"total_sessions": 0, "total_projects": 0})
        mock_indexer.build_full_index = AsyncMock(return_value=5)
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9001,
        )

        try:
            await service.start()

            # Check that initialize was called
            mock_indexer.initialize.assert_called_once()

            # Check that build_full_index was called since total_sessions was 0
            mock_indexer.build_full_index.assert_called_once()
        finally:
            await service.stop()

    async def test_index_skipped_when_populated(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Index build is skipped when database already has sessions."""
        # Create config with database settings
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(state_dir=str(db_state_dir))
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer with existing sessions
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 100,
            "total_projects": 5,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9002,
        )

        try:
            await service.start()

            # Check that build_full_index was NOT called
            mock_indexer.build_full_index.assert_not_called()
        finally:
            await service.stop()


# --- TestPeriodicRefresh ---


class TestPeriodicRefresh:
    """Tests for periodic refresh task."""

    async def test_refresh_task_started(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Refresh task is started when service starts."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9003,
        )

        try:
            await service.start()

            assert service._refresh_task is not None
            assert not service._refresh_task.done()
        finally:
            await service.stop()

    async def test_refresh_task_cancelled_on_stop(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Refresh task is cancelled when service stops."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9004,
        )

        await service.start()
        refresh_task = service._refresh_task
        assert refresh_task is not None

        await service.stop()

        assert service._refresh_task is None
        assert refresh_task.cancelled() or refresh_task.done()


# --- TestPeriodicCheckpoint ---


class TestPeriodicCheckpoint:
    """Tests for periodic WAL checkpoint task."""

    async def test_checkpoint_task_started_when_configured(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Checkpoint task is started when checkpoint_interval > 0."""
        # Create config with checkpoint enabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            checkpoint_interval=300,
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9005,
        )

        try:
            await service.start()

            assert service._checkpoint_task is not None
            assert not service._checkpoint_task.done()
        finally:
            await service.stop()

    async def test_checkpoint_task_not_started_when_disabled(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Checkpoint task is not started when checkpoint_interval is 0."""
        # Create config with checkpoint disabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            checkpoint_interval=0,  # Disabled
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9006,
        )

        try:
            await service.start()

            assert service._checkpoint_task is None
        finally:
            await service.stop()

    async def test_checkpoint_task_cancelled_on_stop(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Checkpoint task is cancelled when service stops."""
        # Create config with checkpoint enabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            checkpoint_interval=300,
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9007,
        )

        await service.start()
        checkpoint_task = service._checkpoint_task
        assert checkpoint_task is not None

        await service.stop()

        assert service._checkpoint_task is None
        assert checkpoint_task.cancelled() or checkpoint_task.done()


# --- TestPeriodicBackup ---


class TestPeriodicBackup:
    """Tests for periodic backup task."""

    async def test_backup_task_started_when_enabled(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path, backup_dir: Path
    ) -> None:
        """Backup task is started when backup is enabled."""
        # Create config with backup enabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            backup=BackupConfig(enabled=True, path=str(backup_dir), keep_count=3),
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db.backup = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9008,
        )

        try:
            await service.start()

            assert service._backup_task is not None
            assert not service._backup_task.done()
        finally:
            await service.stop()

    async def test_backup_task_not_started_when_disabled(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Backup task is not started when backup is disabled."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9009,
        )

        try:
            await service.start()

            # Backup is disabled by default
            assert service._backup_task is None
        finally:
            await service.stop()


# --- TestBackupCreation ---


class TestBackupCreation:
    """Tests for backup file creation."""

    async def test_create_backup_creates_file(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path, backup_dir: Path
    ) -> None:
        """_create_backup creates a backup file."""
        # Create config with backup enabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            backup=BackupConfig(enabled=True, path=str(backup_dir), keep_count=3),
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db.backup = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9010,
        )

        # Call _create_backup directly (without starting service)
        # We need to load config first
        service.config_manager.load()

        await service._create_backup()

        # Check backup was called
        mock_indexer.db.backup.assert_called_once()

        # Check backup path contains timestamp
        call_args = mock_indexer.db.backup.call_args
        backup_path = call_args[0][0]
        assert "search_" in str(backup_path)
        assert backup_path.parent == backup_dir

    async def test_create_backup_rotates_old_backups(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path, backup_dir: Path
    ) -> None:
        """_create_backup rotates old backup files."""
        # Create some old backup files
        for i in range(5):
            (backup_dir / f"search_2024010{i}_120000.db").write_text("old backup")

        assert len(list(backup_dir.glob("search_*.db"))) == 5

        # Create config with backup enabled (keep 3)
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            backup=BackupConfig(enabled=True, path=str(backup_dir), keep_count=3),
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db.backup = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9011,
        )

        # Load config
        service.config_manager.load()

        await service._create_backup()

        # Should have kept 3 old ones (deleted 2), plus new one = 4 but we keep only 3
        # Actually the logic is: after creating new backup, keep at most keep_count
        # The glob will find all, including the new "virtual" one (since we mock backup)
        # Let's check that old files were deleted
        remaining = list(backup_dir.glob("search_*.db"))
        assert len(remaining) == 3


# --- TestGracefulShutdown ---


class TestGracefulShutdown:
    """Tests for graceful shutdown with SQLite indexer."""

    async def test_final_checkpoint_on_stop(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Final checkpoint is called when service stops."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9012,
        )

        await service.start()
        await service.stop()

        # Final checkpoint should be called
        mock_indexer.db.checkpoint.assert_called()

    async def test_indexer_closed_on_stop(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """SQLite indexer is closed when service stops."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9013,
        )

        await service.start()
        await service.stop()

        # Close should be called
        mock_indexer.close.assert_called_once()


# --- TestHealthCheckWithIndex ---


class TestHealthCheckWithIndex:
    """Tests for health check endpoint with index stats."""

    async def test_health_includes_sqlite_index_stats(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Health check includes SQLite index statistics."""
        from aiohttp.test_utils import make_mocked_request

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 100,
            "total_projects": 5,
            "fts_available": True,
            "last_incremental_index": "2024-01-15T10:30:00+00:00",
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9014,
        )

        try:
            await service.start()

            # Create mock request
            request = make_mocked_request("GET", "/health")

            # Call health handler
            response = await service.api.handle_health(request)

            # Parse response
            import json
            body = json.loads(response.body)

            assert body["status"] == "healthy"
            assert body["sessions_indexed"] == 100
            assert body["projects_indexed"] == 5
            assert "index" in body
            assert body["index"]["sessions"] == 100
            assert body["index"]["projects"] == 5
            assert body["index"]["fts_enabled"] is True
        finally:
            await service.stop()


# --- TestErrorRecovery ---


class TestErrorRecovery:
    """Tests for error recovery during index operations."""

    async def test_handle_index_error_recovers_from_corruption(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Index error handler attempts recovery from corruption."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db._recover_database = AsyncMock()
        mock_indexer.build_full_index = AsyncMock(return_value=50)
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9015,
        )

        # Simulate corruption error
        error = Exception("database disk image is malformed (corrupt)")
        await service._handle_index_error(error)

        # Recovery should be attempted
        mock_indexer.db._recover_database.assert_called_once()
        mock_indexer.build_full_index.assert_called_once()

    async def test_handle_index_error_logs_non_corruption(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Index error handler logs but doesn't recover for non-corruption errors."""
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db._recover_database = AsyncMock()
        mock_indexer.build_full_index = AsyncMock(return_value=50)
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9016,
        )

        # Simulate non-corruption error
        error = Exception("connection timeout")
        await service._handle_index_error(error)

        # Recovery should NOT be attempted
        mock_indexer.db._recover_database.assert_not_called()


# --- TestVacuumOnStartup ---


class TestVacuumOnStartup:
    """Tests for vacuum on startup."""

    async def test_vacuum_runs_when_configured(
        self, temp_config_path: Path, temp_state_dir: Path, db_state_dir: Path
    ) -> None:
        """Vacuum runs on startup when configured."""
        # Create config with vacuum enabled
        config_manager = ConfigManager(temp_config_path)
        db_config = DatabaseConfig(
            state_dir=str(db_state_dir),
            vacuum_on_startup=True,
        )
        config_manager.set_database_config(db_config)
        config_manager.save([])

        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9017,
        )

        try:
            await service.start()

            # Vacuum should be called
            mock_indexer.db.vacuum.assert_called_once()
        finally:
            await service.stop()

    async def test_vacuum_skipped_when_not_configured(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Vacuum is skipped when not configured."""
        # Default config has vacuum_on_startup=False
        # Create mock SQLite indexer
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 10,
            "total_projects": 2,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9018,
        )

        try:
            await service.start()

            # Vacuum should NOT be called
            mock_indexer.db.vacuum.assert_not_called()
        finally:
            await service.stop()


# --- TestServiceSurvivesIndexError ---


class TestServiceSurvivesIndexError:
    """Integration tests for service surviving index errors."""

    async def test_service_starts_despite_index_error(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service still starts even if index initialization fails."""
        # Create mock SQLite indexer that fails on initialize
        mock_indexer = AsyncMock(spec=SQLiteSessionIndexer)
        mock_indexer.initialize = AsyncMock(side_effect=Exception("DB init failed"))
        mock_indexer.get_stats = AsyncMock(return_value={
            "total_sessions": 0,
            "total_projects": 0,
        })
        mock_indexer.db = MagicMock()
        mock_indexer.db.vacuum = AsyncMock()
        mock_indexer.db.checkpoint = AsyncMock()
        mock_indexer.db._recover_database = AsyncMock()
        mock_indexer.build_full_index = AsyncMock(return_value=0)
        mock_indexer.close = AsyncMock()

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            sqlite_indexer=mock_indexer,
            port=9019,
        )

        try:
            await service.start()

            # Service should still be running
            assert service.is_running
        finally:
            await service.stop()
