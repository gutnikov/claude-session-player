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


# ---------------------------------------------------------------------------
# Question JSONL fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def question_jsonl_line() -> dict:
    """Single AskUserQuestion tool_use with 3 options.

    Returns a JSONL line representing an AskUserQuestion tool call
    with tool_use_id "toolu_q123" and 3 options.
    """
    return {
        "type": "assistant",
        "requestId": "req-123",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_q123",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "Which approach should I use?",
                                "header": "Implementation Strategy",
                                "options": [
                                    {"label": "Option A", "description": "Use pattern A"},
                                    {"label": "Option B", "description": "Use pattern B"},
                                    {"label": "Option C", "description": "Use pattern C"},
                                ],
                            }
                        ]
                    },
                }
            ]
        },
    }


@pytest.fixture
def question_answer_jsonl_line() -> dict:
    """User's answer to an AskUserQuestion with toolUseResult.answers.

    Returns a JSONL line representing a tool_result with answers.
    """
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_q123",
                    "content": "Selected: Option B",
                }
            ]
        },
        "toolUseResult": {
            "answers": {
                "Which approach should I use?": "Option B",
            }
        },
    }


@pytest.fixture
def multi_question_jsonl_line() -> dict:
    """AskUserQuestion with 2 questions.

    Returns a JSONL line representing an AskUserQuestion tool call
    with 2 separate questions.
    """
    return {
        "type": "assistant",
        "requestId": "req-multi",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_multi",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "Which language?",
                                "header": "Language Selection",
                                "options": [
                                    {"label": "Python", "description": "Use Python"},
                                    {"label": "TypeScript", "description": "Use TypeScript"},
                                ],
                            },
                            {
                                "question": "Which framework?",
                                "header": "Framework Selection",
                                "options": [
                                    {"label": "FastAPI", "description": "Use FastAPI"},
                                    {"label": "Flask", "description": "Use Flask"},
                                ],
                            },
                        ]
                    },
                }
            ]
        },
    }


@pytest.fixture
def many_options_jsonl_line() -> dict:
    """AskUserQuestion with 8 options (triggers truncation at 5).

    Returns a JSONL line representing an AskUserQuestion tool call
    with 8 options to test truncation behavior.
    """
    return {
        "type": "assistant",
        "requestId": "req-many",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_many",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "Which file to edit?",
                                "header": "File Selection",
                                "options": [
                                    {"label": "file1.py", "description": "First file"},
                                    {"label": "file2.py", "description": "Second file"},
                                    {"label": "file3.py", "description": "Third file"},
                                    {"label": "file4.py", "description": "Fourth file"},
                                    {"label": "file5.py", "description": "Fifth file"},
                                    {"label": "file6.py", "description": "Sixth file"},
                                    {"label": "file7.py", "description": "Seventh file"},
                                    {"label": "file8.py", "description": "Eighth file"},
                                ],
                            }
                        ]
                    },
                }
            ]
        },
    }
