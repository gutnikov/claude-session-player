"""Shared test fixtures for Claude Session Player."""

import pytest


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
    """Bash progress with fullOutput field (per issue spec)."""
    return {
        "type": "progress",
        "data": {
            "type": "bash_progress",
            "output": "",
            "fullOutput": "Building...\nStep 1/12: FROM python:3.11-slim",
            "elapsedTimeSeconds": 2,
            "totalLines": 0,
        },
        "toolUseID": "bash-progress-0",
        "parentToolUseID": "toolu_001",
    }


@pytest.fixture
def hook_progress_line() -> dict:
    """Hook progress with hookName and hookEvent fields."""
    return {
        "type": "progress",
        "data": {
            "type": "hook_progress",
            "hookEvent": "PostToolUse",
            "hookName": "PostToolUse:Read",
            "command": "callback",
        },
        "parentToolUseID": "toolu_002",
        "toolUseID": "toolu_002",
    }


@pytest.fixture
def agent_progress_line() -> dict:
    """Agent progress (fixed text output)."""
    return {
        "type": "progress",
        "data": {
            "type": "agent_progress",
        },
        "toolUseID": "agent-progress-0",
        "parentToolUseID": "toolu_003",
    }


@pytest.fixture
def query_update_line() -> dict:
    """WebSearch query update progress."""
    return {
        "type": "progress",
        "data": {
            "type": "query_update",
            "query": "Claude Code hooks feature 2026",
        },
        "parentToolUseID": "toolu_004",
    }


@pytest.fixture
def search_results_line() -> dict:
    """WebSearch results received progress."""
    return {
        "type": "progress",
        "data": {
            "type": "search_results_received",
            "resultCount": 10,
            "query": "Claude Code hooks feature 2026",
        },
        "parentToolUseID": "toolu_004",
    }


@pytest.fixture
def waiting_for_task_line() -> dict:
    """Waiting for task progress with taskDescription."""
    return {
        "type": "progress",
        "data": {
            "type": "waiting_for_task",
            "taskDescription": "Debug socat bridge from inside Docker container",
            "taskType": "local_bash",
        },
        "parentToolUseID": "toolu_005",
    }


@pytest.fixture
def waiting_for_task_no_parent_line() -> dict:
    """Waiting for task without parentToolUseID (standalone)."""
    return {
        "type": "progress",
        "data": {
            "type": "waiting_for_task",
            "taskDescription": "Explore codebase structure",
            "taskType": "local_bash",
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


# ---------------------------------------------------------------------------
# Issue 09 fixtures: isSidechain messages, Task tool results
# ---------------------------------------------------------------------------


@pytest.fixture
def sidechain_user_line() -> dict:
    """User message with isSidechain=true (should be INVISIBLE)."""
    return {
        "type": "user",
        "isSidechain": True,
        "isMeta": False,
        "uuid": "side-001",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {"role": "user", "content": "sidechain user message"},
    }


@pytest.fixture
def sidechain_assistant_line() -> dict:
    """Assistant message with isSidechain=true (should be INVISIBLE)."""
    return {
        "type": "assistant",
        "isSidechain": True,
        "uuid": "side-002",
        "parentUuid": "side-001",
        "requestId": "req_side_001",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "sidechain response"}],
        },
    }


@pytest.fixture
def task_tool_use_line() -> dict:
    """Task tool_use for sub-agent."""
    return {
        "type": "assistant",
        "uuid": "task-001",
        "parentUuid": "aaa-111",
        "requestId": "req_task_001",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_task_001",
                    "name": "Task",
                    "input": {"description": "Explore codebase structure"},
                }
            ],
        },
    }


@pytest.fixture
def task_tool_result_line() -> dict:
    """Task tool result with toolUseResult structure."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "task-result-001",
        "parentUuid": "task-001",
        "sessionId": "sess-001",
        "toolUseResult": {
            "status": "completed",
            "agentId": "ab97f57",
            "content": [{"type": "text", "text": "There are still 114 errors remaining."}],
            "totalDurationMs": 785728,
            "totalTokens": 126186,
            "totalToolUseCount": 77,
        },
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_task_001",
                    "content": "Fallback content if toolUseResult not used",
                    "is_error": False,
                }
            ],
        },
    }


@pytest.fixture
def user_list_content_line() -> dict:
    """User message with list content (not string)."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "user-list-001",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "implement this feature"}],
        },
    }


@pytest.fixture
def tool_result_list_content_line() -> dict:
    """Tool result with list content (not string)."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "result-list-001",
        "parentUuid": "bbb-222",
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": [
                        {"type": "text", "text": "line 1 of result"},
                        {"type": "text", "text": "line 2 of result"},
                    ],
                    "is_error": False,
                }
            ],
        },
    }


@pytest.fixture
def tool_result_null_content_line() -> dict:
    """Tool result with null content."""
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "result-null-001",
        "parentUuid": "bbb-222",
        "sessionId": "sess-001",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": None,
                    "is_error": False,
                }
            ],
        },
    }
