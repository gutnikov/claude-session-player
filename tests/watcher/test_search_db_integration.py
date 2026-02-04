"""Full integration tests for SQLite search index.

Tests the complete workflow including:
- Full index build
- Incremental updates
- Search operations
- Service integration
- Error recovery scenarios
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from claude_session_player.watcher.indexer import (
    IndexConfig,
    SQLiteSessionIndexer,
)
from claude_session_player.watcher.search_db import (
    IndexedSession,
    SearchDatabase,
    SearchFilters,
)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def create_test_project(
    projects_dir: Path,
    name: str,
    sessions: int = 1,
    with_summaries: bool = True,
) -> Path:
    """Create a test project with session files.

    Args:
        projects_dir: Root projects directory
        name: Project name (will be encoded)
        sessions: Number of sessions to create
        with_summaries: Whether to include summary lines

    Returns:
        Path to the created project directory
    """
    encoded_name = f"-Users-test-{name.replace('-', '--')}"
    project_dir = projects_dir / encoded_name
    project_dir.mkdir(parents=True, exist_ok=True)

    for i in range(sessions):
        # Use unique session IDs that include the project name
        session_file = project_dir / f"{name}-session-{i:03d}.jsonl"
        content = ""
        if with_summaries:
            content += f'{{"type": "summary", "summary": "Session {i} for {name}"}}\n'
        content += '{"type": "user", "message": {"content": "Hello"}}\n'
        session_file.write_text(content)

    return project_dir


# ---------------------------------------------------------------------------
# Indexer Integration Tests
# ---------------------------------------------------------------------------


class TestIndexerIntegration:
    """Integration tests for SessionIndexer with SQLite."""

    @pytest.mark.asyncio
    async def test_full_index_build(
        self, tmp_path: Path
    ) -> None:
        """Full indexing from session files works correctly."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "trello", sessions=3)
        create_test_project(projects_dir, "api", sessions=2)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 5

        # Search works
        results, total = await indexer.search(SearchFilters())
        assert total == 5

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_new_file(
        self, tmp_path: Path
    ) -> None:
        """Incremental update detects new files."""
        projects_dir = tmp_path / "projects"
        project = create_test_project(projects_dir, "app", sessions=2)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Add new session
        new_session = project / "session-new.jsonl"
        new_session.write_text('{"type": "summary", "summary": "New session"}\n')

        added, updated, removed = await indexer.incremental_update()

        assert added == 1
        assert updated == 0
        assert removed == 0

        session = await indexer.get_session("session-new")
        assert session is not None
        assert session.summary == "New session"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_modified_file(
        self, tmp_path: Path
    ) -> None:
        """Incremental update detects modified files."""
        projects_dir = tmp_path / "projects"
        project = create_test_project(projects_dir, "app", sessions=2)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Modify existing session
        time.sleep(0.01)  # Ensure mtime changes
        session_file = project / "app-session-000.jsonl"
        session_file.write_text('{"type": "summary", "summary": "Updated session"}\n')

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 1
        assert removed == 0

        session = await indexer.get_session("app-session-000")
        assert session is not None
        assert session.summary == "Updated session"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_deleted_file(
        self, tmp_path: Path
    ) -> None:
        """Incremental update detects deleted files."""
        projects_dir = tmp_path / "projects"
        project = create_test_project(projects_dir, "app", sessions=3)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Delete a session
        (project / "app-session-001.jsonl").unlink()

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 0
        assert removed == 1

        session = await indexer.get_session("app-session-001")
        assert session is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_unchanged_skipped(
        self, tmp_path: Path
    ) -> None:
        """Unchanged files are skipped in incremental update."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=5)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # No changes
        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 0
        assert removed == 0

        await indexer.close()

    @pytest.mark.asyncio
    async def test_handles_corrupt_session(
        self, tmp_path: Path
    ) -> None:
        """Indexer handles corrupt files gracefully."""
        projects_dir = tmp_path / "projects"
        project = create_test_project(projects_dir, "app", sessions=1)

        # Add corrupt file
        (project / "corrupt.jsonl").write_text("not json at all")

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Should not raise
        count = await indexer.build_full_index()

        # Both files indexed (corrupt one has no summary)
        assert count == 2

        await indexer.close()

    @pytest.mark.asyncio
    async def test_handles_missing_directory(
        self, tmp_path: Path
    ) -> None:
        """Indexer handles missing directories gracefully."""
        state_dir = tmp_path / "state"
        nonexistent = tmp_path / "nonexistent"

        indexer = SQLiteSessionIndexer(
            paths=[nonexistent],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Should not raise
        count = await indexer.build_full_index()
        assert count == 0

        await indexer.close()


# ---------------------------------------------------------------------------
# Service Integration Tests
# ---------------------------------------------------------------------------


class TestServiceIntegration:
    """Tests for service-level integration scenarios."""

    @pytest.mark.asyncio
    async def test_service_startup_with_empty_index(
        self, tmp_path: Path
    ) -> None:
        """Service starts correctly with empty index."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        db = SearchDatabase(state_dir)
        await db.initialize()

        stats = await db.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_projects"] == 0

        await db.close()

    @pytest.mark.asyncio
    async def test_service_startup_with_existing_index(
        self, tmp_path: Path
    ) -> None:
        """Service starts correctly with existing index."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=3)
        state_dir = tmp_path / "state"

        # First run - build index
        indexer1 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer1.initialize()
        await indexer1.build_full_index()
        await indexer1.close()

        # Second run - restart
        indexer2 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer2.initialize()

        # Data should be available
        stats = await indexer2.get_stats()
        assert stats["total_sessions"] == 3

        await indexer2.close()

    @pytest.mark.asyncio
    async def test_service_periodic_refresh(
        self, tmp_path: Path
    ) -> None:
        """Simulates periodic index refresh."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=2)
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Simulate periodic refresh (3 cycles)
        for _ in range(3):
            added, updated, removed = await indexer.incremental_update()
            # No changes expected
            assert added == 0

        await indexer.close()

    @pytest.mark.asyncio
    async def test_service_graceful_shutdown(
        self, tmp_path: Path
    ) -> None:
        """Service shuts down gracefully."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=2)
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Graceful shutdown
        await indexer.close()

        # Verify clean shutdown
        assert not indexer._initialized
        assert indexer.db._connection is None


# ---------------------------------------------------------------------------
# End-to-End Workflow Tests
# ---------------------------------------------------------------------------


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_complete_workflow(
        self, tmp_path: Path
    ) -> None:
        """Complete workflow: build -> search -> update -> search."""
        projects_dir = tmp_path / "projects"
        project1 = create_test_project(projects_dir, "trello", sessions=3)
        project2 = create_test_project(projects_dir, "api", sessions=2)

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Build full index
        count = await indexer.build_full_index()
        assert count == 5

        # Search by project
        results, total = await indexer.search(SearchFilters(project="trello"))
        assert total == 3

        # Add new session
        (project1 / "session-new.jsonl").write_text(
            '{"type": "summary", "summary": "Authentication fix"}\n'
        )

        # Incremental update
        added, updated, removed = await indexer.incremental_update()
        assert added == 1

        # Search finds new session
        results, total = await indexer.search(SearchFilters(query="Authentication"))
        assert total == 1
        assert results[0].session_id == "session-new"

        # Delete a session
        (project2 / "api-session-000.jsonl").unlink()

        # Incremental update
        added, updated, removed = await indexer.incremental_update()
        assert removed == 1

        # Verify final count
        stats = await indexer.get_stats()
        assert stats["total_sessions"] == 5  # 3 + 2 + 1 - 1 = 5

        await indexer.close()

    @pytest.mark.asyncio
    async def test_search_workflow(
        self, tmp_path: Path
    ) -> None:
        """Search-focused workflow with various queries."""
        projects_dir = tmp_path / "projects"

        # Create projects with specific content
        auth_project = create_test_project(projects_dir, "auth-service", sessions=0)
        (auth_project / "auth-fix.jsonl").write_text(
            '{"type": "summary", "summary": "Fix authentication bug"}\n'
        )
        (auth_project / "auth-feature.jsonl").write_text(
            '{"type": "summary", "summary": "Add OAuth integration"}\n'
        )

        api_project = create_test_project(projects_dir, "api", sessions=0)
        (api_project / "api-docs.jsonl").write_text(
            '{"type": "summary", "summary": "Update API documentation"}\n'
        )

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Query by text
        results, _ = await indexer.search(SearchFilters(query="authentication"))
        assert len(results) == 1
        assert results[0].session_id == "auth-fix"

        # Query by project
        results, _ = await indexer.search(SearchFilters(project="auth"))
        assert len(results) == 2

        # Combined query
        results, _ = await indexer.search(
            SearchFilters(query="OAuth", project="auth")
        )
        assert len(results) == 1
        assert results[0].session_id == "auth-feature"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_ranking_workflow(
        self, tmp_path: Path
    ) -> None:
        """Ranking-focused workflow."""
        projects_dir = tmp_path / "projects"
        now = datetime.now(timezone.utc)

        project = create_test_project(projects_dir, "app", sessions=0)

        # Create sessions with different relevance
        # Best match: recent + exact phrase
        (project / "best.jsonl").write_text(
            '{"type": "summary", "summary": "Fix authentication bug"}\n'
        )

        # Older match
        old_file = project / "old.jsonl"
        old_file.write_text('{"type": "summary", "summary": "Authentication test"}\n')

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Ranked search
        results, _ = await indexer.search_ranked(
            SearchFilters(query="authentication bug")
        )

        # Best match should be first (has exact phrase + more recent)
        assert results[0].session.session_id == "best"

        await indexer.close()


# ---------------------------------------------------------------------------
# Error Recovery Tests
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    @pytest.mark.asyncio
    async def test_recovery_after_crash(
        self, tmp_path: Path
    ) -> None:
        """Index recovers after simulated crash."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=3)
        state_dir = tmp_path / "state"

        # First run - build index
        indexer1 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer1.initialize()
        await indexer1.build_full_index()

        # Simulate crash - don't close properly
        # Just abandon the indexer

        # New indexer starts fresh
        indexer2 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer2.initialize()

        # Index should still be usable
        stats = await indexer2.get_stats()
        assert stats["total_sessions"] == 3

        await indexer2.close()

    @pytest.mark.asyncio
    async def test_recovery_corrupt_database(
        self, tmp_path: Path
    ) -> None:
        """Recovers from corrupted database file."""
        projects_dir = tmp_path / "projects"
        create_test_project(projects_dir, "app", sessions=2)
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Create corrupt database
        db_path = state_dir / "search.db"
        db_path.write_text("corrupted data")

        db = SearchDatabase(state_dir)
        await db.safe_initialize()

        # Should have recovered
        assert await db.verify_integrity()

        await db.close()

        # Indexer should work
        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()
        assert count == 2

        await indexer.close()


# ---------------------------------------------------------------------------
# Large Dataset Tests
# ---------------------------------------------------------------------------


class TestLargeDataset:
    """Tests with larger datasets."""

    @pytest.mark.asyncio
    async def test_1000_sessions(
        self, tmp_path: Path
    ) -> None:
        """Handles 1000+ sessions correctly."""
        projects_dir = tmp_path / "projects"

        # Create 10 projects with 100 sessions each
        # NOTE: session_id must be unique across all projects (PRIMARY KEY constraint)
        for proj_num in range(10):
            project = projects_dir / f"-Users-test-project{proj_num}"
            project.mkdir(parents=True)
            for sess_num in range(100):
                (project / f"p{proj_num}-s{sess_num:03d}.jsonl").write_text(
                    f'{{"type": "summary", "summary": "Project {proj_num} Session {sess_num}"}}\n'
                )

        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 1000

        # Search still works efficiently - use project filter for project5
        results, total = await indexer.search(SearchFilters(project="project5"))
        assert total == 100  # All sessions in project5

        # Aggregation works
        projects = await indexer.get_projects()
        assert len(projects) == 10
        for p in projects:
            assert p["session_count"] == 100

        await indexer.close()
