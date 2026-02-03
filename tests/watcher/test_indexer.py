"""Tests for SessionIndexer and related functions."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_session_player.watcher.indexer import (
    IndexConfig,
    ProjectInfo,
    RateLimitError,
    SessionIndex,
    SessionIndexer,
    SessionInfo,
    decode_project_path,
    encode_project_path,
    extract_session_metadata,
    get_display_name,
    is_subagent_session,
)


# ---------------------------------------------------------------------------
# Path encoding/decoding tests
# ---------------------------------------------------------------------------


class TestDecodeProjectPath:
    """Tests for decode_project_path function."""

    def test_decode_simple_path(self) -> None:
        """Decode a simple path without hyphens."""
        encoded = "-Users-user-work-trello"
        decoded = decode_project_path(encoded)
        assert decoded == "/Users/user/work/trello"

    def test_decode_path_with_hyphen(self) -> None:
        """Decode a path with a hyphen in the project name."""
        encoded = "-Users-user-work-my--app"
        decoded = decode_project_path(encoded)
        assert decoded == "/Users/user/work/my-app"

    def test_decode_path_with_double_hyphen_in_name(self) -> None:
        """Decode a path with double hyphen in original name."""
        encoded = "-Users-user-work-foo----bar"
        decoded = decode_project_path(encoded)
        assert decoded == "/Users/user/work/foo--bar"

    def test_decode_path_with_multiple_hyphens(self) -> None:
        """Decode a path with multiple hyphens."""
        encoded = "-Users-user-work-my--cool--app"
        decoded = decode_project_path(encoded)
        assert decoded == "/Users/user/work/my-cool-app"

    def test_decode_path_not_encoded(self) -> None:
        """Non-encoded paths are returned as-is."""
        not_encoded = "some-local-dir"
        result = decode_project_path(not_encoded)
        assert result == "some-local-dir"

    def test_decode_windows_style_path(self) -> None:
        """Decode an encoded Windows-style path."""
        # Windows paths like C:\Users\user\work would encode differently
        # but still follow the hyphen rules
        encoded = "-C-Users-user-work-project"
        decoded = decode_project_path(encoded)
        assert decoded == "/C/Users/user/work/project"


class TestEncodeProjectPath:
    """Tests for encode_project_path function."""

    def test_encode_simple_path(self) -> None:
        """Encode a simple path without hyphens."""
        path = "/Users/user/work/trello"
        encoded = encode_project_path(path)
        assert encoded == "-Users-user-work-trello"

    def test_encode_path_with_hyphen(self) -> None:
        """Encode a path with a hyphen in the project name."""
        path = "/Users/user/work/my-app"
        encoded = encode_project_path(path)
        assert encoded == "-Users-user-work-my--app"

    def test_encode_path_with_double_hyphen(self) -> None:
        """Encode a path with double hyphen in original name."""
        path = "/Users/user/work/foo--bar"
        encoded = encode_project_path(path)
        assert encoded == "-Users-user-work-foo----bar"


class TestEncodeDecodeRoundtrip:
    """Tests for encode/decode round-trip consistency."""

    def test_roundtrip_simple_path(self) -> None:
        """Round-trip preserves simple path."""
        path = "/Users/user/work/trello"
        assert decode_project_path(encode_project_path(path)) == path

    def test_roundtrip_hyphenated_path(self) -> None:
        """Round-trip preserves hyphenated path."""
        path = "/Users/user/work/my-app"
        assert decode_project_path(encode_project_path(path)) == path

    def test_roundtrip_double_hyphen_path(self) -> None:
        """Round-trip preserves path with double hyphens."""
        path = "/Users/user/work/foo--bar"
        assert decode_project_path(encode_project_path(path)) == path

    def test_roundtrip_complex_path(self) -> None:
        """Round-trip preserves complex path with multiple hyphens."""
        path = "/Users/my-user/work/my-cool-app-v2"
        assert decode_project_path(encode_project_path(path)) == path


class TestGetDisplayName:
    """Tests for get_display_name function."""

    def test_display_name_simple(self) -> None:
        """Extract display name from simple path."""
        assert get_display_name("/Users/user/work/trello") == "trello"

    def test_display_name_hyphenated(self) -> None:
        """Extract display name with hyphens."""
        assert get_display_name("/Users/user/work/my-cool-app") == "my-cool-app"

    def test_display_name_trailing_slash(self) -> None:
        """Handle trailing slash (Path normalizes it)."""
        assert get_display_name("/Users/user/work/project/") == "project"

    def test_display_name_root(self) -> None:
        """Handle root path."""
        assert get_display_name("/") == ""


# ---------------------------------------------------------------------------
# Subagent detection tests
# ---------------------------------------------------------------------------


class TestIsSubagentSession:
    """Tests for is_subagent_session function."""

    def test_main_session(self) -> None:
        """Main session is not a subagent."""
        path = Path("/home/user/.claude/projects/-Users-user-work-app/session-123.jsonl")
        assert is_subagent_session(path) is False

    def test_subagent_session(self) -> None:
        """Subagent session is identified correctly."""
        path = Path(
            "/home/user/.claude/projects/-Users-user-work-app/"
            "session-123/subagents/agent-abc.jsonl"
        )
        assert is_subagent_session(path) is True

    def test_subagents_in_project_name(self) -> None:
        """'subagents' in encoded project name does NOT trigger false positive."""
        # The function checks path.parts, so 'subagents' in encoded name is safe
        path = Path("/home/user/.claude/projects/-Users-user-work-subagents/session.jsonl")
        # This is correctly NOT identified as subagent (encoded name is one component)
        assert is_subagent_session(path) is False


# ---------------------------------------------------------------------------
# Metadata extraction tests
# ---------------------------------------------------------------------------


class TestExtractSessionMetadata:
    """Tests for extract_session_metadata function."""

    def test_extract_summary_and_line_count(self, tmp_path: Path) -> None:
        """Extract summary and line count from session file."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            '{"type": "user", "message": {"content": "hello"}}',
            '{"type": "assistant", "message": {"content": "hi"}}',
            '{"type": "summary", "summary": "A test conversation"}',
        ]
        session_file.write_text("\n".join(lines) + "\n")

        summary, line_count = extract_session_metadata(session_file)
        assert summary == "A test conversation"
        assert line_count == 3

    def test_no_summary(self, tmp_path: Path) -> None:
        """Handle session without summary."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            '{"type": "user", "message": {"content": "hello"}}',
            '{"type": "assistant", "message": {"content": "hi"}}',
        ]
        session_file.write_text("\n".join(lines) + "\n")

        summary, line_count = extract_session_metadata(session_file)
        assert summary is None
        assert line_count == 2

    def test_multiple_summaries_returns_last(self, tmp_path: Path) -> None:
        """Multiple summaries return the last one (most recent)."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            '{"type": "summary", "summary": "First summary"}',
            '{"type": "user", "message": {"content": "more work"}}',
            '{"type": "summary", "summary": "Updated summary"}',
        ]
        session_file.write_text("\n".join(lines) + "\n")

        summary, line_count = extract_session_metadata(session_file)
        assert summary == "Updated summary"
        assert line_count == 3

    def test_summary_without_spaces(self, tmp_path: Path) -> None:
        """Handle summary with compact JSON (no spaces)."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"summary","summary":"Compact JSON"}\n')

        summary, line_count = extract_session_metadata(session_file)
        assert summary == "Compact JSON"
        assert line_count == 1

    def test_invalid_json_skipped(self, tmp_path: Path) -> None:
        """Invalid JSON lines are skipped."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            '{"type": "user", "message": "valid"}',
            "not valid json",
            '{"type": "summary", "summary": "Valid summary"}',
        ]
        session_file.write_text("\n".join(lines) + "\n")

        summary, line_count = extract_session_metadata(session_file)
        assert summary == "Valid summary"
        assert line_count == 3

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Handle nonexistent file gracefully."""
        session_file = tmp_path / "nonexistent.jsonl"

        summary, line_count = extract_session_metadata(session_file)
        assert summary is None
        assert line_count == 0


# ---------------------------------------------------------------------------
# Data structure tests
# ---------------------------------------------------------------------------


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_create_session_info(self, tmp_path: Path) -> None:
        """Create SessionInfo with all fields."""
        info = SessionInfo(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            file_path=tmp_path / "session.jsonl",
            summary="Test session",
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            size_bytes=1234,
            line_count=50,
            has_subagents=False,
        )
        assert info.session_id == "session-123"
        assert info.summary == "Test session"
        assert info.line_count == 50

    def test_to_dict(self, tmp_path: Path) -> None:
        """to_dict returns expected structure."""
        info = SessionInfo(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            file_path=tmp_path / "session.jsonl",
            summary="Test session",
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            size_bytes=1234,
            line_count=50,
            has_subagents=True,
        )
        result = info.to_dict()
        assert result["session_id"] == "session-123"
        assert result["summary"] == "Test session"
        assert result["has_subagents"] is True

    def test_from_dict_roundtrip(self, tmp_path: Path) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = SessionInfo(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            file_path=tmp_path / "session.jsonl",
            summary="Test session",
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            size_bytes=1234,
            line_count=50,
            has_subagents=False,
        )
        restored = SessionInfo.from_dict(original.to_dict())
        assert restored.session_id == original.session_id
        assert restored.summary == original.summary
        assert restored.file_path == original.file_path

    def test_duration_ms_lazy_calculation(self, tmp_path: Path) -> None:
        """duration_ms is calculated lazily from file."""
        session_file = tmp_path / "session.jsonl"
        lines = [
            '{"type": "user", "message": "hello"}',
            '{"type": "system", "subtype": "turn_duration", "type": "turn_duration", "duration": 5000}',
            '{"type": "turn_duration", "duration": 3000}',
        ]
        session_file.write_text("\n".join(lines) + "\n")

        info = SessionInfo(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            file_path=session_file,
            summary=None,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            size_bytes=100,
            line_count=3,
            has_subagents=False,
        )
        # Duration is calculated on first access
        assert info.duration_ms == 8000


class TestProjectInfo:
    """Tests for ProjectInfo dataclass."""

    def test_create_project_info(self) -> None:
        """Create ProjectInfo with all fields."""
        info = ProjectInfo(
            encoded_name="-Users-user-work-app",
            decoded_path="/Users/user/work/app",
            display_name="app",
            session_ids=["session-1", "session-2"],
            total_size_bytes=5000,
            latest_modified_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert info.display_name == "app"
        assert len(info.session_ids) == 2

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """to_dict/from_dict round-trip preserves data."""
        original = ProjectInfo(
            encoded_name="-Users-user-work-app",
            decoded_path="/Users/user/work/app",
            display_name="app",
            session_ids=["session-1", "session-2"],
            total_size_bytes=5000,
            latest_modified_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        restored = ProjectInfo.from_dict(original.to_dict())
        assert restored.encoded_name == original.encoded_name
        assert restored.session_ids == original.session_ids


class TestSessionIndex:
    """Tests for SessionIndex dataclass."""

    def test_create_empty_index(self) -> None:
        """Create empty SessionIndex."""
        index = SessionIndex()
        assert index.sessions == {}
        assert index.projects == {}

    def test_to_dict_from_dict_roundtrip(self, tmp_path: Path) -> None:
        """to_dict/from_dict round-trip preserves data."""
        session_info = SessionInfo(
            session_id="session-123",
            project_encoded="-Users-user-work-app",
            project_display_name="app",
            file_path=tmp_path / "session.jsonl",
            summary="Test",
            created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            modified_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            size_bytes=100,
            line_count=10,
            has_subagents=False,
        )
        original = SessionIndex(
            sessions={"session-123": session_info},
            projects={},
            created_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            last_refresh=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            refresh_duration_ms=150,
            file_mtimes={str(tmp_path / "session.jsonl"): 1705312200.0},
        )
        restored = SessionIndex.from_dict(original.to_dict())
        assert "session-123" in restored.sessions
        assert restored.refresh_duration_ms == 150


# ---------------------------------------------------------------------------
# SessionIndexer integration tests
# ---------------------------------------------------------------------------


class TestSessionIndexer:
    """Integration tests for SessionIndexer."""

    @pytest.fixture
    def projects_dir(self, tmp_path: Path) -> Path:
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

    @pytest.mark.asyncio
    async def test_full_index_build(self, projects_dir: Path, tmp_path: Path) -> None:
        """Build index from test fixtures."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(include_subagents=False),
            state_dir=state_dir,
        )

        index = await indexer.get_index()

        # Should have 3 main sessions (no subagents)
        assert len(index.sessions) == 3
        assert "session-001" in index.sessions
        assert "session-002" in index.sessions
        assert "session-003" in index.sessions
        assert "agent-abc" not in index.sessions

        # Check session details
        session1 = index.sessions["session-001"]
        assert session1.summary == "Trello session"
        assert session1.project_display_name == "trello"

        session2 = index.sessions["session-002"]
        assert session2.summary == "My app session"
        assert session2.project_display_name == "my-app"

        # Check projects
        assert len(index.projects) == 2
        assert "-Users-user-work-trello" in index.projects
        assert "-Users-user-work-my--app" in index.projects

    @pytest.mark.asyncio
    async def test_index_with_subagents(self, projects_dir: Path, tmp_path: Path) -> None:
        """Build index including subagent sessions."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(include_subagents=True),
            state_dir=state_dir,
        )

        index = await indexer.get_index()

        # Should have 4 sessions (3 main + 1 subagent)
        assert len(index.sessions) == 4
        assert "agent-abc" in index.sessions

    @pytest.mark.asyncio
    async def test_incremental_refresh_detects_changes(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Incremental refresh detects changed files."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )

        # Initial index
        index1 = await indexer.get_index()
        assert index1.sessions["session-001"].summary == "Trello session"

        # Modify a session file
        session1 = projects_dir / "-Users-user-work-trello" / "session-001.jsonl"
        # Need to wait briefly for mtime to change on some filesystems
        import time

        time.sleep(0.01)
        session1.write_text(
            '{"type": "user", "message": "hello"}\n'
            '{"type": "summary", "summary": "Updated summary"}\n'
        )

        # Force refresh
        index2 = await indexer.refresh(force=True)
        assert index2.sessions["session-001"].summary == "Updated summary"

    @pytest.mark.asyncio
    async def test_index_persistence(self, projects_dir: Path, tmp_path: Path) -> None:
        """Index is persisted and loaded on restart."""
        state_dir = tmp_path / "state"

        # Create and populate index
        indexer1 = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(persist=True),
            state_dir=state_dir,
        )
        await indexer1.get_index()

        # Verify index file exists
        index_file = state_dir / "search_index.json"
        assert index_file.exists()

        # Create new indexer (simulating restart)
        indexer2 = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(persist=True),
            state_dir=state_dir,
        )

        # Should load from cache without full rebuild
        index2 = await indexer2.get_index()
        assert len(index2.sessions) == 3

    @pytest.mark.asyncio
    async def test_get_session(self, projects_dir: Path, tmp_path: Path) -> None:
        """get_session returns correct session."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )
        await indexer.get_index()

        session = indexer.get_session("session-001")
        assert session is not None
        assert session.summary == "Trello session"

        # Nonexistent session
        assert indexer.get_session("nonexistent") is None

    @pytest.mark.asyncio
    async def test_get_project(self, projects_dir: Path, tmp_path: Path) -> None:
        """get_project returns correct project."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )
        await indexer.get_index()

        project = indexer.get_project("-Users-user-work-trello")
        assert project is not None
        assert project.display_name == "trello"

        # Nonexistent project
        assert indexer.get_project("-nonexistent") is None

    @pytest.mark.asyncio
    async def test_refresh_rate_limiting(self, projects_dir: Path, tmp_path: Path) -> None:
        """refresh is rate limited unless force=True."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )
        await indexer.get_index()

        # First refresh should succeed
        await indexer.refresh(force=True)

        # Second refresh without force should fail
        with pytest.raises(RateLimitError) as exc_info:
            await indexer.refresh(force=False)
        assert exc_info.value.retry_after > 0

        # Force refresh should still work
        await indexer.refresh(force=True)

    @pytest.mark.asyncio
    async def test_missing_directory_handled(self, tmp_path: Path) -> None:
        """Missing directories are handled gracefully."""
        state_dir = tmp_path / "state"
        nonexistent = tmp_path / "nonexistent"

        indexer = SessionIndexer(
            paths=[nonexistent],
            config=IndexConfig(persist=False),
            state_dir=state_dir,
        )

        # Should not raise, just return empty index
        index = await indexer.get_index()
        assert len(index.sessions) == 0

    @pytest.mark.asyncio
    async def test_has_subagents_detection(self, projects_dir: Path, tmp_path: Path) -> None:
        """has_subagents flag is set correctly."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )
        index = await indexer.get_index()

        # session-003 has a subagents directory
        assert index.sessions["session-003"].has_subagents is True

        # Other sessions don't
        assert index.sessions["session-001"].has_subagents is False
        assert index.sessions["session-002"].has_subagents is False

    @pytest.mark.asyncio
    async def test_deleted_files_removed_on_refresh(
        self, projects_dir: Path, tmp_path: Path
    ) -> None:
        """Deleted files are removed from index on refresh."""
        state_dir = tmp_path / "state"

        indexer = SessionIndexer(
            paths=[projects_dir],
            config=IndexConfig(),
            state_dir=state_dir,
        )

        # Initial index
        index1 = await indexer.get_index()
        assert "session-001" in index1.sessions

        # Delete a session file
        session1 = projects_dir / "-Users-user-work-trello" / "session-001.jsonl"
        session1.unlink()

        # Refresh
        index2 = await indexer.refresh(force=True)
        assert "session-001" not in index2.sessions


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_session_file(self, tmp_path: Path) -> None:
        """Handle empty session files."""
        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)

        empty_session = project / "empty.jsonl"
        empty_session.write_text("")

        indexer = SessionIndexer(
            paths=[projects],
            config=IndexConfig(persist=False),
            state_dir=tmp_path / "state",
        )
        index = await indexer.get_index()

        assert "empty" in index.sessions
        assert index.sessions["empty"].line_count == 0
        assert index.sessions["empty"].summary is None

    @pytest.mark.asyncio
    async def test_corrupt_index_cache(self, tmp_path: Path) -> None:
        """Handle corrupt index cache gracefully."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Create corrupt cache file
        index_file = state_dir / "search_index.json"
        index_file.write_text("not valid json")

        projects = tmp_path / "projects"
        projects.mkdir()

        indexer = SessionIndexer(
            paths=[projects],
            config=IndexConfig(persist=True),
            state_dir=state_dir,
        )

        # Should rebuild index despite corrupt cache
        index = await indexer.get_index()
        assert index is not None

    @pytest.mark.asyncio
    async def test_stale_index_cache(self, tmp_path: Path) -> None:
        """Stale index cache triggers rebuild."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Create stale cache (2 hours old)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        stale_index = SessionIndex(
            sessions={},
            projects={},
            created_at=old_time,
            last_refresh=old_time,
        )

        index_file = state_dir / "search_index.json"
        index_file.write_text(json.dumps(stale_index.to_dict()))

        projects = tmp_path / "projects"
        project = projects / "-Users-user-work-app"
        project.mkdir(parents=True)
        (project / "session.jsonl").write_text('{"type": "user"}\n')

        indexer = SessionIndexer(
            paths=[projects],
            config=IndexConfig(persist=True, max_index_age_hours=1.0),
            state_dir=state_dir,
        )

        # Should rebuild due to stale cache
        index = await indexer.get_index()
        assert "session" in index.sessions
