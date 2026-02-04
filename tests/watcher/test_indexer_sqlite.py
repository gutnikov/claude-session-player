"""Additional SQLite indexer tests.

Complements test_sqlite_indexer.py with additional edge cases,
batch processing tests, and error handling scenarios.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from claude_session_player.watcher.indexer import (
    IndexConfig,
    SQLiteSessionIndexer,
)
from claude_session_player.watcher.search_db import IndexedSession, SearchFilters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def large_projects_dir(tmp_path: Path) -> Path:
    """Create a projects directory with many sessions for batch testing."""
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)

    # Create multiple projects with multiple sessions
    # NOTE: session_id must be unique across all projects (PRIMARY KEY constraint)
    for proj_num in range(5):
        project = projects / f"-Users-user-work-project{proj_num}"
        project.mkdir()

        for sess_num in range(20):
            # Use unique session IDs across projects (p0-s0, p0-s1, p1-s0, etc.)
            session_file = project / f"p{proj_num}-s{sess_num}.jsonl"
            session_file.write_text(
                f'{{"type": "summary", "summary": "Project {proj_num} Session {sess_num}"}}\n'
                f'{{"type": "user", "message": {{"content": "Test"}}}}\n'
            )

    return projects


@pytest.fixture
def nested_projects_dir(tmp_path: Path) -> Path:
    """Create projects with various nesting patterns."""
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)

    # Normal project - use unique session ID
    normal = projects / "-Users-user-work-normal"
    normal.mkdir()
    (normal / "normal-session.jsonl").write_text('{"type": "user"}\n')

    # Project with deep paths (encoded) - use unique session ID
    deep = projects / "-Users-user-work-nested--path--project"
    deep.mkdir()
    (deep / "deep-session.jsonl").write_text('{"type": "summary", "summary": "Deep path"}\n')

    # Project with special chars - use unique session ID
    special = projects / "-Users-user-work-my--special--app"
    special.mkdir()
    (special / "special-session.jsonl").write_text('{"type": "summary", "summary": "Special app"}\n')

    return projects


# ---------------------------------------------------------------------------
# Batch Processing Tests
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    """Tests for batch indexing operations."""

    @pytest.mark.asyncio
    async def test_large_batch_indexing(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Handles indexing many sessions efficiently."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        # Should have 5 projects * 20 sessions = 100 sessions
        assert count == 100

        stats = await indexer.get_stats()
        assert stats["total_sessions"] == 100
        assert stats["total_projects"] == 5

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_update_large_batch(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Incremental update handles many files."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Modify half the files
        for proj_num in range(5):
            project = large_projects_dir / f"-Users-user-work-project{proj_num}"
            for sess_num in range(10):  # Modify first 10 of each project
                session_file = project / f"p{proj_num}-s{sess_num}.jsonl"
                time.sleep(0.001)  # Ensure mtime changes
                session_file.write_text(
                    f'{{"type": "summary", "summary": "Updated {proj_num}-{sess_num}"}}\n'
                )

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 50  # 5 projects * 10 modified
        assert removed == 0

        await indexer.close()

    @pytest.mark.asyncio
    async def test_batch_deletion(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Incremental update handles batch deletions."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Delete one project's sessions
        project = large_projects_dir / "-Users-user-work-project0"
        for f in project.glob("*.jsonl"):
            f.unlink()

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 0
        assert removed == 20  # All sessions from project0

        # Verify count
        stats = await indexer.get_stats()
        assert stats["total_sessions"] == 80

        await indexer.close()


# ---------------------------------------------------------------------------
# Path Handling Tests
# ---------------------------------------------------------------------------


class TestPathHandling:
    """Tests for various path scenarios."""

    @pytest.mark.asyncio
    async def test_nested_project_paths(
        self, nested_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Handles nested and special project paths."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[nested_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Verify project decoding - use one of our unique session IDs
        session = await indexer.get_session("normal-session")
        assert session is not None

        # Search should work
        results, total = await indexer.search(SearchFilters())
        assert total == 3  # 3 projects with 1 session each

        await indexer.close()

    @pytest.mark.asyncio
    async def test_symlinked_project_dir(
        self, tmp_path: Path
    ) -> None:
        """Handles symlinked project directories."""
        # Create actual project
        real_projects = tmp_path / "real_projects"
        project = real_projects / "-Users-user-work-app"
        project.mkdir(parents=True)
        (project / "session-1.jsonl").write_text('{"type": "user"}\n')

        # Create symlink
        linked_projects = tmp_path / "linked_projects"
        try:
            os.symlink(real_projects, linked_projects)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        state_dir = tmp_path / "state"
        indexer = SQLiteSessionIndexer(
            paths=[linked_projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 1

        await indexer.close()

    @pytest.mark.asyncio
    async def test_unicode_in_paths(
        self, tmp_path: Path
    ) -> None:
        """Handles unicode in project/session names."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-项目"  # Chinese for "project"
        project.mkdir(parents=True)
        (project / "session-测试.jsonl").write_text(
            '{"type": "summary", "summary": "测试会话"}\n'
        )

        state_dir = tmp_path / "state"
        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 1

        session = await indexer.get_session("session-测试")
        assert session is not None
        assert session.summary == "测试会话"

        await indexer.close()


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_permission_denied_file(
        self, tmp_path: Path
    ) -> None:
        """Handles files with permission denied errors."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)

        # Create normal file
        (project / "normal.jsonl").write_text('{"type": "user"}\n')

        # Create unreadable file (if possible)
        restricted = project / "restricted.jsonl"
        restricted.write_text('{"type": "user"}\n')

        try:
            os.chmod(restricted, 0o000)
        except OSError:
            pytest.skip("Cannot change file permissions")

        state_dir = tmp_path / "state"
        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Should not raise, just skip unreadable
        count = await indexer.build_full_index()

        # Restore permissions for cleanup
        os.chmod(restricted, 0o644)

        # At least normal file should be indexed
        assert count >= 1

        await indexer.close()

    @pytest.mark.asyncio
    async def test_corrupted_session_file(
        self, tmp_path: Path
    ) -> None:
        """Handles corrupted session files gracefully."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)

        # Valid session
        (project / "valid.jsonl").write_text('{"type": "summary", "summary": "Valid"}\n')

        # Binary garbage
        (project / "binary.jsonl").write_bytes(b"\x00\x01\x02\x03\x04")

        # Partial JSON
        (project / "partial.jsonl").write_text('{"type": "user", "message":')

        state_dir = tmp_path / "state"
        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Should not raise
        count = await indexer.build_full_index()

        # All files get indexed, corrupt ones have no summary
        assert count == 3

        valid = await indexer.get_session("valid")
        assert valid.summary == "Valid"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_disappearing_file(
        self, tmp_path: Path
    ) -> None:
        """Handles files that disappear during indexing."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)

        session_file = project / "session-1.jsonl"
        session_file.write_text('{"type": "user"}\n')

        state_dir = tmp_path / "state"
        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Delete file after indexing
        session_file.unlink()

        # Incremental should handle this
        added, updated, removed = await indexer.incremental_update()
        assert removed == 1

        await indexer.close()


# ---------------------------------------------------------------------------
# Configuration Tests
# ---------------------------------------------------------------------------


class TestIndexerConfiguration:
    """Tests for indexer configuration options."""

    @pytest.mark.asyncio
    async def test_default_config(
        self, tmp_path: Path
    ) -> None:
        """Default configuration works correctly."""
        projects = tmp_path / "projects"
        projects.mkdir()

        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=tmp_path / "state",
            config=IndexConfig(),
        )
        await indexer.initialize()

        assert indexer._initialized
        assert indexer.config.include_subagents is False
        assert indexer.config.persist is True  # True by default

        await indexer.close()

    @pytest.mark.asyncio
    async def test_custom_config(
        self, tmp_path: Path
    ) -> None:
        """Custom configuration applied correctly."""
        projects = tmp_path / "projects"
        projects.mkdir()

        indexer = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=tmp_path / "state",
            config=IndexConfig(include_subagents=True, persist=False),
        )
        await indexer.initialize()

        assert indexer.config.include_subagents is True
        assert indexer.config.persist is False

        await indexer.close()


# ---------------------------------------------------------------------------
# Search Integration Tests
# ---------------------------------------------------------------------------


class TestSearchIntegration:
    """Tests for search integration with indexer."""

    @pytest.mark.asyncio
    async def test_search_after_incremental(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Search works correctly after incremental updates."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Add a unique session
        project = large_projects_dir / "-Users-user-work-project0"
        (project / "unique-session.jsonl").write_text(
            '{"type": "summary", "summary": "Unique authentication feature"}\n'
        )

        await indexer.incremental_update()

        # Search should find it
        results, total = await indexer.search(SearchFilters(query="Unique"))
        assert total == 1
        assert results[0].session_id == "unique-session"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_project_aggregation(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Project aggregation works correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        projects = await indexer.get_projects()

        assert len(projects) == 5
        for project in projects:
            assert project["session_count"] == 20
            assert project["total_size_bytes"] > 0

        await indexer.close()


# ---------------------------------------------------------------------------
# State Persistence Tests
# ---------------------------------------------------------------------------


class TestStatePersistence:
    """Tests for index state persistence."""

    @pytest.mark.asyncio
    async def test_mtime_preserved_across_restart(
        self, tmp_path: Path
    ) -> None:
        """File mtimes preserved across indexer restart."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)
        session_file = project / "session-1.jsonl"
        session_file.write_text('{"type": "user"}\n')

        state_dir = tmp_path / "state"

        # First indexer
        indexer1 = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer1.initialize()
        await indexer1.build_full_index()
        await indexer1.close()

        # Second indexer (restart)
        indexer2 = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer2.initialize()

        # Incremental should detect no changes
        added, updated, removed = await indexer2.incremental_update()
        assert added == 0
        assert updated == 0
        assert removed == 0

        await indexer2.close()

    @pytest.mark.asyncio
    async def test_metadata_timestamps_persist(
        self, tmp_path: Path
    ) -> None:
        """Index metadata timestamps persist."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)
        (project / "session-1.jsonl").write_text('{"type": "user"}\n')

        state_dir = tmp_path / "state"

        # First indexer
        indexer1 = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer1.initialize()
        await indexer1.build_full_index()

        stats1 = await indexer1.get_stats()
        last_full_index = stats1["last_full_index"]
        assert last_full_index is not None

        await indexer1.close()

        # Second indexer
        indexer2 = SQLiteSessionIndexer(
            paths=[projects],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer2.initialize()

        stats2 = await indexer2.get_stats()
        # Timestamp should be preserved
        assert stats2["last_full_index"] == last_full_index

        await indexer2.close()


# ---------------------------------------------------------------------------
# Concurrent Access Tests
# ---------------------------------------------------------------------------


class TestConcurrentAccess:
    """Tests for concurrent database access."""

    @pytest.mark.asyncio
    async def test_multiple_readers(
        self, large_projects_dir: Path, tmp_path: Path
    ) -> None:
        """Multiple readers can access index simultaneously."""
        state_dir = tmp_path / "state"

        # Build index
        indexer = SQLiteSessionIndexer(
            paths=[large_projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Create multiple search queries in parallel
        import asyncio

        queries = [
            indexer.search(SearchFilters(query=f"Project {i}"))
            for i in range(5)
        ]

        results = await asyncio.gather(*queries)

        # All should succeed
        for sessions, total in results:
            assert total >= 1

        await indexer.close()
