"""Shared test fixtures for watcher module tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import pytest

from claude_session_player.watcher.search_db import IndexedSession, SearchDatabase


# ---------------------------------------------------------------------------
# Session factory fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_session() -> Callable[..., IndexedSession]:
    """Factory for creating test sessions.

    Usage:
        session = sample_session()  # Default values
        session = sample_session(session_id="custom", summary="Custom summary")
    """

    def _create(
        session_id: str = "test-session",
        project_encoded: str = "-test-project",
        project_display_name: str = "test-project",
        project_path: str = "/test/project",
        summary: str | None = "Test summary",
        file_path: str | None = None,
        file_created_at: datetime | None = None,
        file_modified_at: datetime | None = None,
        indexed_at: datetime | None = None,
        size_bytes: int = 1000,
        line_count: int = 50,
        duration_ms: int | None = 60000,
        has_subagents: bool = False,
        is_subagent: bool = False,
    ) -> IndexedSession:
        now = datetime.now(timezone.utc)
        return IndexedSession(
            session_id=session_id,
            project_encoded=project_encoded,
            project_display_name=project_display_name,
            project_path=project_path,
            summary=summary,
            file_path=file_path or f"/test/{project_display_name}/{session_id}.jsonl",
            file_created_at=file_created_at or now - timedelta(hours=1),
            file_modified_at=file_modified_at or now,
            indexed_at=indexed_at or now,
            size_bytes=size_bytes,
            line_count=line_count,
            duration_ms=duration_ms,
            has_subagents=has_subagents,
            is_subagent=is_subagent,
        )

    return _create


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Temporary state directory for test database."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
async def search_db(temp_state_dir: Path) -> SearchDatabase:
    """Initialized SearchDatabase.

    Use this for tests that need a clean database.
    """
    db = SearchDatabase(temp_state_dir)
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def search_db_no_fts(temp_state_dir: Path) -> SearchDatabase:
    """SearchDatabase with FTS5 disabled.

    Use this for testing LIKE fallback behavior.
    """
    db = SearchDatabase(temp_state_dir)
    db._fts_available = False
    await db.initialize()
    yield db
    await db.close()


# ---------------------------------------------------------------------------
# Project directory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_projects_dir(tmp_path: Path) -> Path:
    """Temporary projects directory for test sessions."""
    projects = tmp_path / "projects"
    projects.mkdir()
    return projects


def create_test_project(
    projects_dir: Path,
    name: str,
    sessions: int = 1,
    with_subagents: bool = False,
) -> Path:
    """Create a test project with session files.

    Args:
        projects_dir: Root projects directory
        name: Project display name (will be encoded)
        sessions: Number of sessions to create
        with_subagents: Whether to create a subagent directory

    Returns:
        Path to the created project directory
    """
    # Encode project name (simple encoding for tests)
    encoded_name = f"-test-{name.replace('-', '--')}"
    project_dir = projects_dir / encoded_name
    project_dir.mkdir(parents=True, exist_ok=True)

    for i in range(sessions):
        # Use unique session IDs that include the project name
        session_file = project_dir / f"{name}-session-{i}.jsonl"
        session_file.write_text(
            f'{{"type": "summary", "summary": "Session {i} for {name}"}}\n'
            f'{{"type": "user", "message": {{"content": "Hello"}}}}\n'
        )

    if with_subagents:
        subagents_dir = project_dir / f"{name}-session-0" / "subagents"
        subagents_dir.mkdir(parents=True)
        subagent_file = subagents_dir / "subagent-0.jsonl"
        subagent_file.write_text(
            '{"type": "user", "message": {"content": "Subagent"}}\n'
        )

    return project_dir


def add_session_to_project(
    project_dir: Path,
    session_id: str,
    summary: str | None = None,
) -> Path:
    """Add a session file to an existing project.

    Args:
        project_dir: Project directory path
        session_id: Session ID (file stem)
        summary: Optional summary text

    Returns:
        Path to the created session file
    """
    session_file = project_dir / f"{session_id}.jsonl"
    content = ""
    if summary:
        content += f'{{"type": "summary", "summary": "{summary}"}}\n'
    content += '{"type": "user", "message": {"content": "Test"}}\n'
    session_file.write_text(content)
    return session_file
