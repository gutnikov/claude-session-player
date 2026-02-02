"""Shared test fixtures for Claude Session Player."""

import pytest

from claude_session_player.models import ScreenState


@pytest.fixture
def empty_state() -> ScreenState:
    """Return a fresh, empty ScreenState."""
    return ScreenState()


# ---------------------------------------------------------------------------
# Issue 02 fixtures: JSONL line dicts for each message type
# ---------------------------------------------------------------------------


@pytest.fixture
def user_input_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-111",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {"role": "user", "content": "hello world"},
    }


@pytest.fixture
def user_input_multiline_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-112",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {"role": "user", "content": "line one\nline two\nline three"},
    }


@pytest.fixture
def user_meta_line() -> dict:
    return {
        "type": "user",
        "isMeta": True,
        "uuid": "aaa-200",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {"role": "user", "content": "skill expansion text"},
    }


@pytest.fixture
def tool_result_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-300",
        "parentUuid": "bbb-222",
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": "file1.py\nfile2.py",
                    "is_error": False,
                }
            ],
        },
    }


@pytest.fixture
def tool_result_error_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-301",
        "parentUuid": "bbb-223",
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_002",
                    "content": "command not found: foo",
                    "is_error": True,
                }
            ],
        },
    }


@pytest.fixture
def tool_result_parallel_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-302",
        "parentUuid": "bbb-224",
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_010",
                    "content": "result A",
                    "is_error": False,
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_011",
                    "content": "result B",
                    "is_error": True,
                },
            ],
        },
    }


@pytest.fixture
def local_command_output_line() -> dict:
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-400",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": "<local-command-stdout>git status output here</local-command-stdout>",
        },
    }


@pytest.fixture
def assistant_text_line() -> dict:
    return {
        "type": "assistant",
        "uuid": "bbb-111",
        "parentUuid": "aaa-111",
        "requestId": "req_001",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Here is my response."}],
        },
    }


@pytest.fixture
def tool_use_line() -> dict:
    return {
        "type": "assistant",
        "uuid": "bbb-222",
        "parentUuid": "aaa-111",
        "requestId": "req_001",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "Bash",
                    "input": {"command": "ls -la", "description": "List files"},
                }
            ],
        },
    }


@pytest.fixture
def tool_use_read_line() -> dict:
    return {
        "type": "assistant",
        "uuid": "bbb-223",
        "parentUuid": "aaa-111",
        "requestId": "req_001",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_003",
                    "name": "Read",
                    "input": {"file_path": "/src/main.py"},
                }
            ],
        },
    }


@pytest.fixture
def tool_use_write_line() -> dict:
    return {
        "type": "assistant",
        "uuid": "bbb-224",
        "parentUuid": "aaa-111",
        "requestId": "req_002",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_004",
                    "name": "Write",
                    "input": {"file_path": "/src/config.py", "content": "x = 1"},
                }
            ],
        },
    }


@pytest.fixture
def thinking_line() -> dict:
    return {
        "type": "assistant",
        "uuid": "bbb-333",
        "parentUuid": "aaa-111",
        "requestId": "req_001",
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "Let me think about this..."}],
        },
    }


@pytest.fixture
def turn_duration_line() -> dict:
    return {
        "type": "system",
        "subtype": "turn_duration",
        "durationMs": 12500,
        "sessionId": "sess-001",
    }


@pytest.fixture
def compact_boundary_line() -> dict:
    return {
        "type": "system",
        "subtype": "compact_boundary",
        "sessionId": "sess-001",
    }


@pytest.fixture
def system_local_command_line() -> dict:
    return {
        "type": "system",
        "subtype": "local_command",
        "sessionId": "sess-001",
    }


@pytest.fixture
def bash_progress_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "bash_progress",
            "parentToolUseID": "toolu_001",
            "toolUseID": "bash-progress-0",
            "content": "running...",
        },
    }


@pytest.fixture
def hook_progress_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "hook_progress",
            "parentToolUseID": "toolu_002",
            "toolUseID": "hook-progress-0",
            "hookName": "pre-commit",
        },
    }


@pytest.fixture
def agent_progress_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "agent_progress",
            "parentToolUseID": "toolu_003",
            "toolUseID": "agent-progress-0",
            "content": "working...",
        },
    }


@pytest.fixture
def query_update_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "query_update",
            "parentToolUseID": "toolu_004",
            "toolUseID": "query-update-0",
            "query": "Claude hooks 2026",
        },
    }


@pytest.fixture
def search_results_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "search_results_received",
            "parentToolUseID": "toolu_004",
            "toolUseID": "search-results-0",
            "resultCount": 5,
        },
    }


@pytest.fixture
def waiting_for_task_line() -> dict:
    return {
        "type": "progress",
        "data": {
            "type": "waiting_for_task",
            "parentToolUseID": "toolu_005",
            "toolUseID": "waiting-0",
            "taskDescription": "Explore codebase",
        },
    }


@pytest.fixture
def file_history_snapshot_line() -> dict:
    return {
        "type": "file-history-snapshot",
        "messageId": "msg-001",
        "snapshot": {"trackedFileBackups": {}},
    }


@pytest.fixture
def queue_operation_line() -> dict:
    return {"type": "queue-operation", "operation": "enqueue"}


@pytest.fixture
def summary_line() -> dict:
    return {
        "type": "summary",
        "summary": "This is a conversation summary.",
        "sessionId": "sess-001",
    }


@pytest.fixture
def pr_link_line() -> dict:
    return {"type": "pr-link", "url": "https://github.com/org/repo/pull/1"}
