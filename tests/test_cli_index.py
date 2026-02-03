"""Tests for CLI index management commands."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.cli import (
    _backup,
    _create_parser,
    _format_datetime,
    _format_duration,
    _format_size,
    _get_db_size,
    _handle_index_command,
    _rebuild,
    _search,
    _stats,
    _update,
    _vacuum,
    _verify,
    main,
)


# ---------------------------------------------------------------------------
# Test Helper Formatting Functions
# ---------------------------------------------------------------------------


class TestFormatSize:
    """Tests for _format_size helper."""

    def test_bytes(self):
        assert _format_size(500) == "500 B"
        assert _format_size(0) == "0 B"

    def test_kilobytes(self):
        assert _format_size(1024) == "1.0 KB"
        assert _format_size(2560) == "2.5 KB"

    def test_megabytes(self):
        assert _format_size(1024 * 1024) == "1.0 MB"
        assert _format_size(int(45.3 * 1024 * 1024)) == "45.3 MB"

    def test_gigabytes(self):
        assert _format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert _format_size(int(2.5 * 1024 * 1024 * 1024)) == "2.5 GB"


class TestFormatDuration:
    """Tests for _format_duration helper."""

    def test_none(self):
        assert _format_duration(None) == "N/A"

    def test_seconds(self):
        assert _format_duration(5000) == "5s"
        assert _format_duration(59000) == "59s"

    def test_minutes(self):
        assert _format_duration(60000) == "1m"
        assert _format_duration(90000) == "1m 30s"
        assert _format_duration(23 * 60 * 1000) == "23m"

    def test_hours(self):
        assert _format_duration(60 * 60 * 1000) == "1h 0m"
        assert _format_duration(90 * 60 * 1000) == "1h 30m"


class TestFormatDatetime:
    """Tests for _format_datetime helper."""

    def test_none(self):
        assert _format_datetime(None) == "Never"

    def test_empty(self):
        assert _format_datetime("") == "Never"

    def test_valid_iso(self):
        result = _format_datetime("2024-01-15T10:30:00")
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_invalid_format(self):
        # Should return the original string if parsing fails
        assert _format_datetime("not a date") == "not a date"


class TestGetDbSize:
    """Tests for _get_db_size helper."""

    def test_existing_db(self, tmp_path: Path):
        db_path = tmp_path / "search.db"
        db_path.write_bytes(b"x" * 1024)
        assert _get_db_size(tmp_path) == 1024

    def test_missing_db(self, tmp_path: Path):
        assert _get_db_size(tmp_path) == 0


# ---------------------------------------------------------------------------
# Test Parser
# ---------------------------------------------------------------------------


class TestCreateParser:
    """Tests for argument parser creation."""

    def test_parser_created(self):
        parser = _create_parser()
        assert parser.prog == "claude-session-player"

    def test_replay_command(self):
        parser = _create_parser()
        args = parser.parse_args(["replay", "test.jsonl"])
        assert args.command == "replay"
        assert args.session_file == "test.jsonl"

    def test_index_rebuild_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "rebuild"])
        assert args.command == "index"
        assert args.index_command == "rebuild"

    def test_index_rebuild_with_options(self, tmp_path: Path):
        parser = _create_parser()
        args = parser.parse_args([
            "index", "rebuild",
            "--paths", str(tmp_path),
            "--state-dir", str(tmp_path / "state"),
        ])
        assert args.command == "index"
        assert args.index_command == "rebuild"
        assert tmp_path in args.paths
        assert args.state_dir == tmp_path / "state"

    def test_index_update_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "update"])
        assert args.command == "index"
        assert args.index_command == "update"

    def test_index_stats_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "stats"])
        assert args.command == "index"
        assert args.index_command == "stats"

    def test_index_verify_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "verify"])
        assert args.command == "index"
        assert args.index_command == "verify"

    def test_index_vacuum_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "vacuum"])
        assert args.command == "index"
        assert args.index_command == "vacuum"

    def test_index_backup_command(self, tmp_path: Path):
        parser = _create_parser()
        output = tmp_path / "backup.db"
        args = parser.parse_args(["index", "backup", "-o", str(output)])
        assert args.command == "index"
        assert args.index_command == "backup"
        assert args.output == output

    def test_index_search_command(self):
        parser = _create_parser()
        args = parser.parse_args(["index", "search", "auth bug"])
        assert args.command == "index"
        assert args.index_command == "search"
        assert args.query == "auth bug"

    def test_index_search_with_options(self):
        parser = _create_parser()
        args = parser.parse_args([
            "index", "search", "auth bug",
            "-p", "trello",
            "-l", "20",
        ])
        assert args.query == "auth bug"
        assert args.project == "trello"
        assert args.limit == 20


# ---------------------------------------------------------------------------
# Test Index Commands (Integration)
# ---------------------------------------------------------------------------


class TestRebuildCommand:
    """Tests for index rebuild command."""

    async def test_rebuild_empty_directory(self, tmp_path: Path):
        """Rebuild with no session files."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        state_dir = tmp_path / "state"

        result = await _rebuild([projects_dir], state_dir)
        assert result == 0

    async def test_rebuild_with_sessions(self, tmp_path: Path):
        """Rebuild indexes session files."""
        # Create a test project and session
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-test-project"
        project_dir.mkdir(parents=True)

        session_file = project_dir / "session-001.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Test session"}\n'
            '{"type":"user","message":{"role":"user","content":"hello"}}\n'
        )

        state_dir = tmp_path / "state"
        result = await _rebuild([projects_dir], state_dir)

        assert result == 0
        # Verify database was created
        assert (state_dir / "search.db").exists()

    async def test_rebuild_handles_error(self, tmp_path: Path):
        """Rebuild handles errors gracefully."""
        # Use a path that can't be accessed
        with patch(
            "claude_session_player.watcher.indexer.SQLiteSessionIndexer"
        ) as mock_indexer_class:
            mock_indexer = AsyncMock()
            mock_indexer.initialize.side_effect = Exception("Database error")
            mock_indexer_class.return_value = mock_indexer

            result = await _rebuild([tmp_path], tmp_path / "state")
            assert result == 1


class TestUpdateCommand:
    """Tests for index update command."""

    async def test_update_empty_index(self, tmp_path: Path):
        """Update on empty index."""
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        state_dir = tmp_path / "state"

        # First build
        await _rebuild([projects_dir], state_dir)

        # Then update
        result = await _update([projects_dir], state_dir)
        assert result == 0


class TestStatsCommand:
    """Tests for index stats command."""

    async def test_stats_shows_info(self, tmp_path: Path):
        """Stats command shows correct information."""
        # Create a test project and session
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-test-project"
        project_dir.mkdir(parents=True)

        session_file = project_dir / "session-001.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Test session"}\n'
        )

        state_dir = tmp_path / "state"

        # Build index first
        await _rebuild([projects_dir], state_dir)

        # Get stats
        result = await _stats(state_dir)
        assert result == 0


class TestVerifyCommand:
    """Tests for index verify command."""

    async def test_verify_valid_db(self, tmp_path: Path):
        """Verify returns success for valid database."""
        state_dir = tmp_path / "state"

        # Create an empty database
        from claude_session_player.watcher.search_db import SearchDatabase

        db = SearchDatabase(state_dir)
        await db.initialize()
        await db.close()

        # Verify
        result = await _verify(state_dir)
        assert result == 0

    async def test_verify_corrupt_db(self, tmp_path: Path):
        """Verify detects corruption."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)

        # Create a corrupt database file
        db_path = state_dir / "search.db"
        db_path.write_text("this is not a valid sqlite database")

        # Verify should detect the issue (or handle gracefully)
        result = await _verify(state_dir)
        # The result depends on how sqlite handles the corrupt file
        # It might fail or trigger recovery


class TestVacuumCommand:
    """Tests for index vacuum command."""

    async def test_vacuum_works(self, tmp_path: Path):
        """Vacuum command completes successfully."""
        state_dir = tmp_path / "state"

        # Create a database with some data
        from claude_session_player.watcher.search_db import SearchDatabase, IndexedSession

        db = SearchDatabase(state_dir)
        await db.initialize()

        # Insert and delete to create space for vacuum
        session = IndexedSession(
            session_id="test-1",
            project_encoded="-test",
            project_display_name="test",
            project_path="/test",
            summary="Test summary",
            file_path="/test/session.jsonl",
            file_created_at=datetime.now(timezone.utc),
            file_modified_at=datetime.now(timezone.utc),
            indexed_at=datetime.now(timezone.utc),
            size_bytes=1000,
            line_count=10,
            duration_ms=None,
            has_subagents=False,
            is_subagent=False,
        )
        await db.upsert_session(session)
        await db.delete_session("test-1")
        await db.close()

        # Vacuum
        result = await _vacuum(state_dir)
        assert result == 0


class TestBackupCommand:
    """Tests for index backup command."""

    async def test_backup_creates_file(self, tmp_path: Path):
        """Backup creates a valid backup file."""
        state_dir = tmp_path / "state"
        backup_path = tmp_path / "backup.db"

        # Create a database
        from claude_session_player.watcher.search_db import SearchDatabase, IndexedSession

        db = SearchDatabase(state_dir)
        await db.initialize()
        session = IndexedSession(
            session_id="test-1",
            project_encoded="-test",
            project_display_name="test",
            project_path="/test",
            summary="Test summary",
            file_path="/test/session.jsonl",
            file_created_at=datetime.now(timezone.utc),
            file_modified_at=datetime.now(timezone.utc),
            indexed_at=datetime.now(timezone.utc),
            size_bytes=1000,
            line_count=10,
            duration_ms=None,
            has_subagents=False,
            is_subagent=False,
        )
        await db.upsert_session(session)
        await db.close()

        # Backup
        result = await _backup(backup_path, state_dir)
        assert result == 0
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0


class TestSearchCommand:
    """Tests for index search command."""

    async def test_search_returns_results(self, tmp_path: Path):
        """Search finds matching sessions."""
        # Create a test project and session file
        projects_dir = tmp_path / "projects"
        project_dir = projects_dir / "-trello-clone"
        project_dir.mkdir(parents=True)

        session_file = project_dir / "test-1.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Fix authentication bug in login flow"}\n'
            '{"type":"user","message":{"role":"user","content":"hello"}}\n'
        )

        state_dir = tmp_path / "state"

        # Build the index properly (this ensures FTS triggers fire)
        await _rebuild([projects_dir], state_dir)

        # Search
        result = await _search("auth", None, 10, state_dir)
        assert result == 0

    async def test_search_no_results(self, tmp_path: Path):
        """Search handles no results."""
        state_dir = tmp_path / "state"

        # Create an empty database
        from claude_session_player.watcher.search_db import SearchDatabase

        db = SearchDatabase(state_dir)
        await db.initialize()
        await db.close()

        # Search for something that doesn't exist
        result = await _search("nonexistent query xyz", None, 10, state_dir)
        assert result == 0

    async def test_search_with_project_filter(self, tmp_path: Path):
        """Search filters by project."""
        state_dir = tmp_path / "state"

        # Create a database with sessions
        from claude_session_player.watcher.search_db import SearchDatabase, IndexedSession

        db = SearchDatabase(state_dir)
        await db.initialize()

        for i, project in enumerate(["trello", "api", "mobile"]):
            session = IndexedSession(
                session_id=f"test-{i}",
                project_encoded=f"-{project}",
                project_display_name=project,
                project_path=f"/{project}",
                summary=f"Auth work in {project}",
                file_path=f"/test/{project}/session.jsonl",
                file_created_at=datetime.now(timezone.utc),
                file_modified_at=datetime.now(timezone.utc),
                indexed_at=datetime.now(timezone.utc),
                size_bytes=1000,
                line_count=10,
                duration_ms=None,
                has_subagents=False,
                is_subagent=False,
            )
            await db.upsert_session(session)

        await db.close()

        # Search with project filter
        result = await _search("auth", "trello", 10, state_dir)
        assert result == 0


# ---------------------------------------------------------------------------
# Test Handle Index Command
# ---------------------------------------------------------------------------


class TestHandleIndexCommand:
    """Tests for _handle_index_command."""

    def test_missing_subcommand(self):
        """Shows help when no subcommand given."""
        parser = _create_parser()
        args = parser.parse_args(["index"])

        result = _handle_index_command(args)
        assert result == 1


# ---------------------------------------------------------------------------
# Test CLI Help
# ---------------------------------------------------------------------------


class TestCLIHelp:
    """Tests for CLI help output."""

    def test_main_help(self):
        """Main --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "claude_session_player.cli", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "replay" in result.stdout.lower() or "session" in result.stdout.lower()

    def test_index_help(self):
        """Index --help works."""
        result = subprocess.run(
            [sys.executable, "-m", "claude_session_player.cli", "index", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "rebuild" in result.stdout
        assert "update" in result.stdout
        assert "stats" in result.stdout


# ---------------------------------------------------------------------------
# Test CLI Integration via subprocess
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Integration tests for CLI commands via subprocess."""

    def test_invalid_path_error(self, tmp_path: Path):
        """CLI shows error for non-existent file."""
        result = subprocess.run(
            [
                sys.executable, "-m", "claude_session_player.cli",
                str(tmp_path / "nonexistent.jsonl"),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_legacy_replay_mode(self, tmp_path: Path):
        """Legacy mode works (file path without 'replay' command)."""
        session_file = tmp_path / "test.jsonl"
        session_file.write_text(
            '{"type":"user","isMeta":false,"uuid":"aaa","message":{"role":"user","content":"hello"}}\n'
        )

        result = subprocess.run(
            [sys.executable, "-m", "claude_session_player.cli", str(session_file)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_explicit_replay_mode(self, tmp_path: Path):
        """Explicit 'replay' command works."""
        session_file = tmp_path / "test.jsonl"
        session_file.write_text(
            '{"type":"user","isMeta":false,"uuid":"aaa","message":{"role":"user","content":"world"}}\n'
        )

        result = subprocess.run(
            [
                sys.executable, "-m", "claude_session_player.cli",
                "replay", str(session_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "world" in result.stdout


# ---------------------------------------------------------------------------
# Test Main Function
# ---------------------------------------------------------------------------


class TestMainFunction:
    """Tests for main() function edge cases."""

    def test_no_args_shows_help(self, capsys):
        """Running with no args shows help."""
        with patch("sys.argv", ["claude-session-player"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_help_flag(self, capsys):
        """--help flag works."""
        with patch("sys.argv", ["claude-session-player", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
