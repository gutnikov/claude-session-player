"""Tests for SQLiteSessionIndexer - SearchDatabase-backed session indexer."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_session_player.watcher.indexer import (
    IndexConfig,
    SQLiteSessionIndexer,
    decode_project_path,
    extract_session_metadata,
)
from claude_session_player.watcher.search_db import IndexedSession, SearchFilters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    """Create a mock projects directory with sessions."""
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)

    # Create project 1: simple project
    project1 = projects / "-Users-user-work-trello"
    project1.mkdir()

    session1 = project1 / "session-001.jsonl"
    session1.write_text(
        '{"type": "user", "message": "hello"}\n'
        '{"type": "summary", "summary": "Trello session"}\n'
    )

    # Create project 2: hyphenated project name
    project2 = projects / "-Users-user-work-my--app"
    project2.mkdir()

    session2 = project2 / "session-002.jsonl"
    session2.write_text(
        '{"type": "user", "message": "start"}\n'
        '{"type": "summary", "summary": "My app session"}\n'
    )

    # Create session with subagents
    session3 = project2 / "session-003.jsonl"
    session3.write_text('{"type": "user", "message": "main session"}\n')

    subagents_dir = project2 / "session-003" / "subagents"
    subagents_dir.mkdir(parents=True)
    subagent = subagents_dir / "agent-abc.jsonl"
    subagent.write_text('{"type": "user", "message": "subagent session"}\n')

    return projects


@pytest.fixture
async def indexer(tmp_path: Path) -> SQLiteSessionIndexer:
    """Create an initialized SQLiteSessionIndexer."""
    state_dir = tmp_path / "state"
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    idx = SQLiteSessionIndexer(
        paths=[projects_dir],
        state_dir=state_dir,
        config=IndexConfig(persist=True),
    )
    await idx.initialize()
    yield idx
    await idx.close()


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestSQLiteSessionIndexerInitialization:
    """Tests for SQLiteSessionIndexer initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_database(self, tmp_path: Path) -> None:
        """Database is created on initialize."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        assert (state_dir / "search.db").exists()
        assert indexer._initialized is True

        await indexer.close()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path: Path) -> None:
        """Initialize can be called multiple times safely."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.initialize()  # Should not raise

        assert indexer._initialized is True

        await indexer.close()

    @pytest.mark.asyncio
    async def test_close_and_reinitialize(self, tmp_path: Path) -> None:
        """Can close and reinitialize."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()
        await indexer.close()

        assert indexer._initialized is False

        await indexer.initialize()
        assert indexer._initialized is True

        await indexer.close()


# ---------------------------------------------------------------------------
# Full index build tests
# ---------------------------------------------------------------------------


class TestBuildFullIndex:
    """Tests for build_full_index method."""

    @pytest.mark.asyncio
    async def test_build_full_index_empty(self, tmp_path: Path) -> None:
        """Handles empty directory."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        assert count == 0

        await indexer.close()

    @pytest.mark.asyncio
    async def test_build_full_index_sessions(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Indexes session files correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        # Should have 3 main sessions (no subagents)
        assert count == 3

        # Verify sessions are in database
        session = await indexer.get_session("session-001")
        assert session is not None
        assert session.summary == "Trello session"
        assert session.project_display_name == "trello"

        session2 = await indexer.get_session("session-002")
        assert session2 is not None
        assert session2.summary == "My app session"
        assert session2.project_display_name == "my-app"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_build_full_index_skips_hidden(self, tmp_path: Path) -> None:
        """Ignores hidden files and directories."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        # Create visible project
        project = projects_dir / "-Users-user-work-app"
        project.mkdir()
        (project / "visible.jsonl").write_text('{"type": "user"}\n')

        # Create hidden file
        (project / ".hidden.jsonl").write_text('{"type": "user"}\n')

        # Create hidden project directory
        hidden_project = projects_dir / ".hidden-project"
        hidden_project.mkdir()
        (hidden_project / "session.jsonl").write_text('{"type": "user"}\n')

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        # Only visible session should be indexed
        assert count == 1
        assert await indexer.get_session("visible") is not None
        assert await indexer.get_session(".hidden") is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_build_full_index_skips_temp(self, tmp_path: Path) -> None:
        """Ignores .tmp files."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        project = projects_dir / "-Users-user-work-app"
        project.mkdir(parents=True)

        (project / "session.jsonl").write_text('{"type": "user"}\n')
        (project / "session.tmp").write_text('{"type": "user"}\n')

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        assert count == 1

        await indexer.close()

    @pytest.mark.asyncio
    async def test_build_full_index_handles_corrupt(self, tmp_path: Path) -> None:
        """Skips corrupt files gracefully."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        project = projects_dir / "-Users-user-work-app"
        project.mkdir(parents=True)

        # Valid session
        (project / "valid.jsonl").write_text('{"type": "user"}\n')

        # Corrupt session (JSON parse error won't stop indexing)
        (project / "corrupt.jsonl").write_text("not json\n")

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        # Both files are "indexed" - corrupt one just has no summary
        assert count == 2
        valid = await indexer.get_session("valid")
        assert valid is not None

        corrupt = await indexer.get_session("corrupt")
        assert corrupt is not None
        assert corrupt.summary is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_build_full_index_clears_previous(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Full index build clears previous data."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()

        # First build
        count1 = await indexer.build_full_index()
        assert count1 == 3

        # Delete a session file
        (projects_dir / "-Users-user-work-trello" / "session-001.jsonl").unlink()

        # Second build should only have 2 sessions
        count2 = await indexer.build_full_index()
        assert count2 == 2
        assert await indexer.get_session("session-001") is None

        await indexer.close()


# ---------------------------------------------------------------------------
# Incremental update tests
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    """Tests for incremental_update method."""

    @pytest.mark.asyncio
    async def test_incremental_detects_new(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """New files are added."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Add a new session
        project = projects_dir / "-Users-user-work-trello"
        (project / "session-new.jsonl").write_text(
            '{"type": "summary", "summary": "New session"}\n'
        )

        added, updated, removed = await indexer.incremental_update()

        assert added == 1
        assert updated == 0
        assert removed == 0

        new_session = await indexer.get_session("session-new")
        assert new_session is not None
        assert new_session.summary == "New session"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_detects_modified(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Modified files are updated."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        session = await indexer.get_session("session-001")
        assert session is not None
        assert session.summary == "Trello session"

        # Modify session file
        time.sleep(0.01)  # Ensure mtime changes
        session_file = projects_dir / "-Users-user-work-trello" / "session-001.jsonl"
        session_file.write_text('{"type": "summary", "summary": "Updated summary"}\n')

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 1
        assert removed == 0

        updated_session = await indexer.get_session("session-001")
        assert updated_session is not None
        assert updated_session.summary == "Updated summary"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_detects_deleted(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Deleted files are removed."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Delete a session file
        session_file = projects_dir / "-Users-user-work-trello" / "session-001.jsonl"
        session_file.unlink()

        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 0
        assert removed == 1

        assert await indexer.get_session("session-001") is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_incremental_unchanged_skipped(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Unchanged files are not re-read."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # No changes - incremental should be fast and return zeros
        added, updated, removed = await indexer.incremental_update()

        assert added == 0
        assert updated == 0
        assert removed == 0

        await indexer.close()


# ---------------------------------------------------------------------------
# Search delegation tests
# ---------------------------------------------------------------------------


class TestSearchDelegation:
    """Tests for search method delegation."""

    @pytest.mark.asyncio
    async def test_search_delegation(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Search calls DB correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # Search by query
        results, total = await indexer.search(SearchFilters(query="Trello"))
        assert total >= 1
        assert any(r.session_id == "session-001" for r in results)

        await indexer.close()

    @pytest.mark.asyncio
    async def test_search_ranked_delegation(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """search_ranked works correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        results, total = await indexer.search_ranked(SearchFilters(query="session"))
        assert total >= 1
        # Results should have scores
        assert all(hasattr(r, "score") for r in results)

        await indexer.close()

    @pytest.mark.asyncio
    async def test_get_projects_delegation(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """get_projects works correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        projects = await indexer.get_projects()

        assert len(projects) == 2
        project_names = {p["project_display_name"] for p in projects}
        assert "trello" in project_names
        assert "my-app" in project_names

        await indexer.close()

    @pytest.mark.asyncio
    async def test_get_stats_delegation(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """get_stats works correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        stats = await indexer.get_stats()

        assert stats["total_sessions"] == 3
        assert stats["total_projects"] == 2
        assert "fts_available" in stats

        await indexer.close()


# ---------------------------------------------------------------------------
# Subagent handling tests
# ---------------------------------------------------------------------------


class TestSubagentHandling:
    """Tests for subagent session handling."""

    @pytest.mark.asyncio
    async def test_subagents_excluded_default(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Subagents not indexed by default."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 3  # Only main sessions
        assert await indexer.get_session("agent-abc") is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_subagents_included_config(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Subagents indexed when configured."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=True),
        )
        await indexer.initialize()
        count = await indexer.build_full_index()

        assert count == 4  # 3 main + 1 subagent
        subagent = await indexer.get_session("agent-abc")
        assert subagent is not None
        assert subagent.is_subagent is True

        await indexer.close()

    @pytest.mark.asyncio
    async def test_has_subagents_flag(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """has_subagents flag is set correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        # session-003 has a subagents directory
        session3 = await indexer.get_session("session-003")
        assert session3 is not None
        assert session3.has_subagents is True

        # Other sessions don't
        session1 = await indexer.get_session("session-001")
        assert session1 is not None
        assert session1.has_subagents is False

        await indexer.close()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration tests for SQLiteSessionIndexer."""

    @pytest.mark.asyncio
    async def test_full_workflow(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Initialize -> build -> search -> close workflow."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )

        # Initialize
        await indexer.initialize()
        assert indexer._initialized

        # Build index
        count = await indexer.build_full_index()
        assert count == 3

        # Search
        results, total = await indexer.search(SearchFilters())
        assert total == 3

        # Get stats
        stats = await indexer.get_stats()
        assert stats["total_sessions"] == 3

        # Close
        await indexer.close()
        assert not indexer._initialized

    @pytest.mark.asyncio
    async def test_incremental_after_full(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Incremental after full build works correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()

        # Full build
        count = await indexer.build_full_index()
        assert count == 3

        # Add new session
        project = projects_dir / "-Users-user-work-trello"
        time.sleep(0.01)
        (project / "session-new.jsonl").write_text('{"type": "user"}\n')

        # Incremental update
        added, updated, removed = await indexer.incremental_update()
        assert added == 1

        # Total should now be 4
        stats = await indexer.get_stats()
        assert stats["total_sessions"] == 4

        await indexer.close()

    @pytest.mark.asyncio
    async def test_persistence_across_restart(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Index survives restart."""
        state_dir = tmp_path / "state"

        # Create and populate index
        indexer1 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer1.initialize()
        await indexer1.build_full_index()
        await indexer1.close()

        # Verify database file exists
        assert (state_dir / "search.db").exists()

        # Create new indexer (simulating restart)
        indexer2 = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer2.initialize()

        # Data should still be there
        stats = await indexer2.get_stats()
        assert stats["total_sessions"] == 3

        session = await indexer2.get_session("session-001")
        assert session is not None
        assert session.summary == "Trello session"

        await indexer2.close()

    @pytest.mark.asyncio
    async def test_auto_initialize_on_build(self, tmp_path: Path) -> None:
        """build_full_index auto-initializes if needed."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )

        # Don't call initialize explicitly
        count = await indexer.build_full_index()

        assert count == 0
        assert indexer._initialized

        await indexer.close()

    @pytest.mark.asyncio
    async def test_auto_initialize_on_incremental(self, tmp_path: Path) -> None:
        """incremental_update auto-initializes if needed."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )

        # Don't call initialize explicitly
        added, updated, removed = await indexer.incremental_update()

        assert indexer._initialized

        await indexer.close()


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_missing_directory_handled(self, tmp_path: Path) -> None:
        """Missing directories are handled gracefully."""
        state_dir = tmp_path / "state"
        nonexistent = tmp_path / "nonexistent"

        indexer = SQLiteSessionIndexer(
            paths=[nonexistent],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        # Should not raise, just return 0
        count = await indexer.build_full_index()
        assert count == 0

        await indexer.close()

    @pytest.mark.asyncio
    async def test_empty_session_file(self, tmp_path: Path) -> None:
        """Handle empty session files."""
        state_dir = tmp_path / "state"
        projects_dir = tmp_path / "projects"
        project = projects_dir / "-Users-user-work-app"
        project.mkdir(parents=True)

        (project / "empty.jsonl").write_text("")

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        assert count == 1
        session = await indexer.get_session("empty")
        assert session is not None
        assert session.line_count == 0
        assert session.summary is None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_multiple_paths(self, tmp_path: Path) -> None:
        """Handles multiple paths correctly."""
        state_dir = tmp_path / "state"

        # Create two project directories
        path1 = tmp_path / "path1"
        project1 = path1 / "-Users-user-work-app1"
        project1.mkdir(parents=True)
        (project1 / "session1.jsonl").write_text('{"type": "user"}\n')

        path2 = tmp_path / "path2"
        project2 = path2 / "-Users-user-work-app2"
        project2.mkdir(parents=True)
        (project2 / "session2.jsonl").write_text('{"type": "user"}\n')

        indexer = SQLiteSessionIndexer(
            paths=[path1, path2],
            state_dir=state_dir,
            config=IndexConfig(),
        )
        await indexer.initialize()

        count = await indexer.build_full_index()

        assert count == 2
        assert await indexer.get_session("session1") is not None
        assert await indexer.get_session("session2") is not None

        await indexer.close()

    @pytest.mark.asyncio
    async def test_project_path_decoding(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Project paths are decoded correctly."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()
        await indexer.build_full_index()

        session = await indexer.get_session("session-002")
        assert session is not None
        assert session.project_display_name == "my-app"
        assert session.project_path == "/Users/user/work/my-app"
        assert session.project_encoded == "-Users-user-work-my--app"

        await indexer.close()

    @pytest.mark.asyncio
    async def test_metadata_timestamps_set(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Metadata timestamps are set after indexing."""
        state_dir = tmp_path / "state"

        indexer = SQLiteSessionIndexer(
            paths=[projects_dir],
            state_dir=state_dir,
            config=IndexConfig(include_subagents=False),
        )
        await indexer.initialize()

        await indexer.build_full_index()

        stats = await indexer.get_stats()
        assert stats["last_full_index"] is not None

        await indexer.incremental_update()

        stats = await indexer.get_stats()
        assert stats["last_incremental_index"] is not None

        await indexer.close()
