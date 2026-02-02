"""Shared test fixtures for Claude session player tests."""

from __future__ import annotations

import pytest

from claude_session_player.models import ScreenState


@pytest.fixture
def state() -> ScreenState:
    """Fresh empty screen state."""
    return ScreenState()


# --- User message fixtures ---


@pytest.fixture
def user_input_line() -> dict:
    """Direct user input message."""
    return {
        "type": "user",
        "uuid": "aaa-111",
        "parentUuid": None,
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": False,
        "message": {
            "role": "user",
            "content": "implement the backtest engine",
        },
    }


@pytest.fixture
def user_multiline_input_line() -> dict:
    """Direct user input with multiple lines."""
    return {
        "type": "user",
        "uuid": "aaa-112",
        "parentUuid": None,
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": False,
        "message": {
            "role": "user",
            "content": "implement the engine\nwith these features\nand this behavior",
        },
    }


@pytest.fixture
def user_meta_line() -> dict:
    """Skill expansion (isMeta=true) - invisible."""
    return {
        "type": "user",
        "uuid": "aaa-200",
        "parentUuid": "aaa-111",
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": True,
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "# Expanded skill prompt..."}],
        },
    }


@pytest.fixture
def user_tool_result_line() -> dict:
    """Tool result user message."""
    return {
        "type": "user",
        "uuid": "ccc-333",
        "parentUuid": "bbb-222",
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": False,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": "# My Project\n\nA CLI tool for managing widgets.",
                }
            ],
        },
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": "/home/user/project/README.md",
                "content": "# My Project\n\nA CLI tool for managing widgets.",
                "numLines": 3,
            },
        },
    }


@pytest.fixture
def user_tool_result_error_line() -> dict:
    """Tool result with error."""
    return {
        "type": "user",
        "uuid": "ccc-334",
        "parentUuid": "bbb-222",
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": False,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_002",
                    "content": "File not found: /nonexistent.txt",
                    "is_error": True,
                }
            ],
        },
    }


@pytest.fixture
def user_local_command_stdout_line() -> dict:
    """User message with local command stdout."""
    return {
        "type": "user",
        "uuid": "aaa-300",
        "parentUuid": None,
        "sessionId": "sess-001",
        "isSidechain": False,
        "isMeta": False,
        "message": {
            "role": "user",
            "content": "<local-command-stdout>git status output here</local-command-stdout>",
        },
    }


# --- Assistant message fixtures ---


@pytest.fixture
def assistant_text_line() -> dict:
    """Assistant text block."""
    return {
        "type": "assistant",
        "uuid": "bbb-100",
        "parentUuid": "aaa-111",
        "sessionId": "sess-001",
        "requestId": "req_001",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "I'll implement the backtest engine.",
                }
            ],
        },
    }


@pytest.fixture
def assistant_tool_use_read_line() -> dict:
    """Assistant tool_use block for Read."""
    return {
        "type": "assistant",
        "uuid": "bbb-222",
        "parentUuid": "aaa-111",
        "sessionId": "sess-001",
        "requestId": "req_001",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "Read",
                    "input": {"file_path": "/home/user/project/README.md"},
                }
            ],
        },
    }


@pytest.fixture
def assistant_tool_use_bash_line() -> dict:
    """Assistant tool_use block for Bash."""
    return {
        "type": "assistant",
        "uuid": "bbb-223",
        "parentUuid": "aaa-111",
        "sessionId": "sess-001",
        "requestId": "req_002",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_002",
                    "name": "Bash",
                    "input": {
                        "command": "ls -la",
                        "description": "List files in current directory",
                    },
                }
            ],
        },
    }


@pytest.fixture
def assistant_thinking_line() -> dict:
    """Assistant thinking block."""
    return {
        "type": "assistant",
        "uuid": "bbb-300",
        "parentUuid": "aaa-111",
        "sessionId": "sess-001",
        "requestId": "req_001",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "Let me think about this...",
                    "signature": "abc123",
                }
            ],
        },
    }


# --- System message fixtures ---


@pytest.fixture
def system_turn_duration_line() -> dict:
    """System turn_duration message."""
    return {
        "type": "system",
        "uuid": "eee-555",
        "parentUuid": "ddd-444",
        "sessionId": "sess-001",
        "subtype": "turn_duration",
        "durationMs": 5500,
        "isSidechain": False,
        "isMeta": False,
    }


@pytest.fixture
def system_turn_duration_long_line() -> dict:
    """System turn_duration message (>= 60s)."""
    return {
        "type": "system",
        "uuid": "eee-556",
        "parentUuid": "ddd-444",
        "sessionId": "sess-001",
        "subtype": "turn_duration",
        "durationMs": 88947,
        "isSidechain": False,
        "isMeta": False,
    }


@pytest.fixture
def system_compact_boundary_line() -> dict:
    """System compact_boundary message."""
    return {
        "type": "system",
        "uuid": "fff-666",
        "parentUuid": None,
        "sessionId": "sess-001",
        "subtype": "compact_boundary",
        "content": "Conversation compacted",
        "isSidechain": False,
        "isMeta": False,
        "logicalParentUuid": "eee-555",
        "compactMetadata": {"trigger": "auto", "preTokens": 167503},
    }


# --- Progress message fixtures ---


@pytest.fixture
def progress_bash_line() -> dict:
    """Bash progress message."""
    return {
        "type": "progress",
        "data": {
            "type": "bash_progress",
            "output": "Step 1/12 : FROM python:3.11-slim",
        },
        "toolUseID": "bash-progress-0",
        "parentToolUseID": "toolu_002",
    }


@pytest.fixture
def progress_agent_line() -> dict:
    """Agent progress message."""
    return {
        "type": "progress",
        "data": {
            "type": "agent_progress",
            "message": {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": "Working..."}]},
            },
        },
        "toolUseID": "agent-progress-0",
        "parentToolUseID": "toolu_task_001",
    }


@pytest.fixture
def progress_hook_line() -> dict:
    """Hook progress message."""
    return {
        "type": "progress",
        "data": {
            "type": "hook_progress",
            "hookEvent": "SessionStart",
            "hookName": "SessionStart:startup",
            "command": "echo hello",
        },
    }


@pytest.fixture
def progress_query_update_line() -> dict:
    """WebSearch query update progress."""
    return {
        "type": "progress",
        "data": {
            "type": "query_update",
            "query": "Claude Code hooks feature 2026",
        },
        "toolUseID": "ws-progress-0",
        "parentToolUseID": "toolu_ws_001",
    }


@pytest.fixture
def progress_search_results_line() -> dict:
    """WebSearch results received progress."""
    return {
        "type": "progress",
        "data": {
            "type": "search_results_received",
            "resultCount": 10,
            "query": "Claude Code hooks feature 2026",
        },
        "toolUseID": "ws-progress-1",
        "parentToolUseID": "toolu_ws_001",
    }


# --- Invisible message fixtures ---


@pytest.fixture
def summary_line() -> dict:
    """Summary message (invisible)."""
    return {
        "type": "summary",
        "summary": "Backtest engine implementation",
        "leafUuid": "old-uuid",
    }


@pytest.fixture
def file_history_snapshot_line() -> dict:
    """File history snapshot (invisible)."""
    return {
        "type": "file-history-snapshot",
        "messageId": "aaa-111",
        "snapshot": {
            "messageId": "aaa-111",
            "trackedFileBackups": {},
            "timestamp": "2026-01-03T10:00:00.000Z",
        },
        "isSnapshotUpdate": False,
    }


@pytest.fixture
def sidechain_line() -> dict:
    """Sidechain message (invisible in main session)."""
    return {
        "type": "user",
        "uuid": "side-001",
        "parentUuid": None,
        "sessionId": "sess-001",
        "isSidechain": True,
        "isMeta": False,
        "agentId": "ab97f57",
        "message": {
            "role": "user",
            "content": "Sub-agent task prompt",
        },
    }
