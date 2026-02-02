"""Tests for the render function dispatch logic."""

from __future__ import annotations

from claude_session_player.models import ScreenState, ScreenElement
from claude_session_player.renderer import render


class TestRenderReturnsState:
    """Verify render returns the same mutated state object."""

    def test_returns_same_instance(self, state: ScreenState, user_input_line: dict) -> None:
        result = render(state, user_input_line)
        assert result is state

    def test_empty_line_returns_state(self, state: ScreenState) -> None:
        result = render(state, {})
        assert result is state


class TestUserMessages:
    """Test user message handling."""

    def test_direct_input(self, state: ScreenState, user_input_line: dict) -> None:
        render(state, user_input_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "user_message"
        assert el.text == "implement the backtest engine"

    def test_multiline_input(self, state: ScreenState, user_multiline_input_line: dict) -> None:
        render(state, user_multiline_input_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "user_message"
        assert "implement the engine" in el.text
        assert "with these features" in el.text

    def test_meta_invisible(self, state: ScreenState, user_meta_line: dict) -> None:
        render(state, user_meta_line)
        assert len(state.elements) == 0

    def test_local_command_stdout(self, state: ScreenState, user_local_command_stdout_line: dict) -> None:
        render(state, user_local_command_stdout_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "system_output"
        assert el.text == "git status output here"

    def test_sidechain_invisible(self, state: ScreenState, sidechain_line: dict) -> None:
        render(state, sidechain_line)
        assert len(state.elements) == 0

    def test_user_content_as_text_blocks(self, state: ScreenState) -> None:
        """User message with content as list of text blocks (not tool results)."""
        line = {
            "type": "user",
            "uuid": "u1",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": "World"},
                ],
            },
        }
        render(state, line)
        assert len(state.elements) == 1
        assert state.elements[0].kind == "user_message"
        assert "Hello" in state.elements[0].text
        assert "World" in state.elements[0].text


class TestToolResults:
    """Test tool result matching and rendering."""

    def test_tool_result_matches_tool_call(
        self,
        state: ScreenState,
        assistant_tool_use_read_line: dict,
        user_tool_result_line: dict,
    ) -> None:
        render(state, assistant_tool_use_read_line)
        assert len(state.elements) == 1
        assert state.elements[0].result is None

        render(state, user_tool_result_line)
        # Element count stays at 1 (result updates existing element)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.result is not None
        assert "My Project" in el.result
        assert el.is_error is False

    def test_tool_result_error(
        self,
        state: ScreenState,
        assistant_tool_use_bash_line: dict,
        user_tool_result_error_line: dict,
    ) -> None:
        render(state, assistant_tool_use_bash_line)
        render(state, user_tool_result_error_line)
        el = state.elements[0]
        assert el.is_error is True
        assert "File not found" in el.result

    def test_tool_result_with_list_content(self, state: ScreenState) -> None:
        """Tool result where content is a list of blocks, not a string."""
        # First create the tool call
        tool_use_line = {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_x",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_list", "name": "Read", "input": {"file_path": "/f.txt"}},
                ],
            },
        }
        render(state, tool_use_line)

        # Tool result with list content
        result_line = {
            "type": "user",
            "uuid": "u2",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_list",
                        "content": [
                            {"type": "text", "text": "File contents here"},
                        ],
                    }
                ],
            },
        }
        render(state, result_line)
        assert state.elements[0].result == "File contents here"

    def test_bash_tool_prefers_stdout(self, state: ScreenState) -> None:
        """Bash tool result should prefer toolUseResult.stdout."""
        tool_use_line = {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_x",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_bash",
                        "name": "Bash",
                        "input": {"command": "echo hi"},
                    },
                ],
            },
        }
        render(state, tool_use_line)

        result_line = {
            "type": "user",
            "uuid": "u2",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_bash",
                        "content": "verbose output for model",
                    }
                ],
            },
            "toolUseResult": {
                "stdout": "hi\n",
                "stderr": "",
                "interrupted": False,
            },
        }
        render(state, result_line)
        assert state.elements[0].result == "hi\n"

    def test_task_tool_result_truncated(self, state: ScreenState) -> None:
        """Task tool result should use first 80 chars of content[0].text."""
        tool_use_line = {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_x",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_task",
                        "name": "Task",
                        "input": {"description": "Do the thing"},
                    },
                ],
            },
        }
        render(state, tool_use_line)

        long_text = "A" * 100
        result_line = {
            "type": "user",
            "uuid": "u2",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_task",
                        "content": "model sees this",
                    }
                ],
            },
            "toolUseResult": {
                "status": "completed",
                "content": [{"type": "text", "text": long_text}],
            },
        }
        render(state, result_line)
        result = state.elements[0].result
        assert len(result) == 80
        assert result.endswith("\u2026")


class TestAssistantMessages:
    """Test assistant message handling."""

    def test_text_block(self, state: ScreenState, assistant_text_line: dict) -> None:
        render(state, assistant_text_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "assistant_text"
        assert el.text == "I'll implement the backtest engine."
        assert el.request_id == "req_001"

    def test_tool_use_block(self, state: ScreenState, assistant_tool_use_read_line: dict) -> None:
        render(state, assistant_tool_use_read_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "tool_call"
        assert el.tool_name == "Read"
        assert el.label == "README.md"
        assert el.tool_use_id == "toolu_001"
        assert "toolu_001" in state.tool_calls

    def test_thinking_block(self, state: ScreenState, assistant_thinking_line: dict) -> None:
        render(state, assistant_thinking_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "thinking"
        assert el.request_id == "req_001"

    def test_request_id_tracking(self, state: ScreenState, assistant_text_line: dict) -> None:
        render(state, assistant_text_line)
        assert state.current_request_id == "req_001"

    def test_empty_text_block(self, state: ScreenState) -> None:
        """Empty text in assistant block should be filtered out (not crash)."""
        line = {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_x",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": ""}],
            },
        }
        render(state, line)
        # Empty text blocks are filtered out
        assert len(state.elements) == 0

    def test_no_content_text_block(self, state: ScreenState) -> None:
        """'(no content)' placeholder text blocks should be filtered out."""
        line = {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_x",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "(no content)"}],
            },
        }
        render(state, line)
        assert len(state.elements) == 0


class TestSystemMessages:
    """Test system message handling."""

    def test_turn_duration_short(self, state: ScreenState, system_turn_duration_line: dict) -> None:
        render(state, system_turn_duration_line)
        assert len(state.elements) == 1
        el = state.elements[0]
        assert el.kind == "turn_duration"
        assert el.duration_ms == 5500

    def test_turn_duration_long(self, state: ScreenState, system_turn_duration_long_line: dict) -> None:
        render(state, system_turn_duration_long_line)
        el = state.elements[0]
        assert el.duration_ms == 88947

    def test_compact_boundary_clears_state(self, state: ScreenState) -> None:
        # Build up some state
        render(state, {
            "type": "user",
            "uuid": "u1",
            "isSidechain": False,
            "isMeta": False,
            "message": {"role": "user", "content": "hello"},
        })
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/f"}}],
            },
        })
        assert len(state.elements) == 2
        assert len(state.tool_calls) == 1

        # Compact boundary
        render(state, {
            "type": "system",
            "subtype": "compact_boundary",
            "parentUuid": None,
            "isSidechain": False,
        })
        assert len(state.elements) == 0
        assert len(state.tool_calls) == 0
        assert state.current_request_id is None

    def test_local_command_invisible(self, state: ScreenState) -> None:
        render(state, {
            "type": "system",
            "subtype": "local_command",
            "content": "<command-name>agents</command-name>",
            "isSidechain": False,
        })
        assert len(state.elements) == 0


class TestProgressMessages:
    """Test progress message handling."""

    def test_bash_progress_updates_tool(self, state: ScreenState) -> None:
        # Create a bash tool call first
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_bash_1", "name": "Bash", "input": {"command": "make"}},
                ],
            },
        })

        # Send bash progress
        render(state, {
            "type": "progress",
            "data": {"type": "bash_progress", "output": "Building..."},
            "toolUseID": "bp-0",
            "parentToolUseID": "toolu_bash_1",
        })

        assert state.elements[0].result == "Building..."

    def test_agent_progress(self, state: ScreenState) -> None:
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_task_1", "name": "Task", "input": {"description": "Do stuff"}},
                ],
            },
        })

        render(state, {
            "type": "progress",
            "data": {"type": "agent_progress"},
            "toolUseID": "ap-0",
            "parentToolUseID": "toolu_task_1",
        })

        assert state.elements[0].result == "Agent: working\u2026"

    def test_hook_progress_no_parent(self, state: ScreenState, progress_hook_line: dict) -> None:
        """Hook progress without matching parent should not crash."""
        render(state, progress_hook_line)
        assert len(state.elements) == 0

    def test_query_update_progress(self, state: ScreenState) -> None:
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_ws_1", "name": "WebSearch", "input": {"query": "test"}},
                ],
            },
        })

        render(state, {
            "type": "progress",
            "data": {"type": "query_update", "query": "Claude hooks 2026"},
            "toolUseID": "qp-0",
            "parentToolUseID": "toolu_ws_1",
        })
        assert state.elements[0].result == "Searching: Claude hooks 2026"

    def test_search_results_received(self, state: ScreenState) -> None:
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_ws_2", "name": "WebSearch", "input": {"query": "test"}},
                ],
            },
        })

        render(state, {
            "type": "progress",
            "data": {"type": "search_results_received", "resultCount": 10},
            "toolUseID": "sp-0",
            "parentToolUseID": "toolu_ws_2",
        })
        assert state.elements[0].result == "10 results"

    def test_waiting_for_task(self, state: ScreenState) -> None:
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_t1", "name": "Bash", "input": {"command": "sleep 10"}},
                ],
            },
        })

        render(state, {
            "type": "progress",
            "data": {"type": "waiting_for_task", "taskDescription": "Debug socat bridge"},
            "toolUseID": "wt-0",
            "parentToolUseID": "toolu_t1",
        })
        assert state.elements[0].result == "Waiting: Debug socat bridge"

    def test_progress_no_matching_parent_ignored(self, state: ScreenState) -> None:
        """Progress with non-existent parentToolUseID should be silently ignored."""
        render(state, {
            "type": "progress",
            "data": {"type": "bash_progress", "output": "something"},
            "toolUseID": "bp-0",
            "parentToolUseID": "nonexistent_tool_id",
        })
        assert len(state.elements) == 0


class TestInvisibleMessages:
    """Test that invisible message types don't affect state."""

    def test_summary_invisible(self, state: ScreenState, summary_line: dict) -> None:
        render(state, summary_line)
        assert len(state.elements) == 0

    def test_file_history_invisible(self, state: ScreenState, file_history_snapshot_line: dict) -> None:
        render(state, file_history_snapshot_line)
        assert len(state.elements) == 0

    def test_queue_operation_invisible(self, state: ScreenState) -> None:
        render(state, {"type": "queue-operation", "operation": "dequeue"})
        assert len(state.elements) == 0

    def test_pr_link_invisible(self, state: ScreenState) -> None:
        render(state, {"type": "pr-link", "prNumber": 3, "prUrl": "https://github.com/x/y/pull/3"})
        assert len(state.elements) == 0


class TestParallelToolCalls:
    """Test parallel tool calls with same requestId."""

    def test_multiple_tools_same_request(self, state: ScreenState) -> None:
        # Two tool_use blocks with same requestId (separate JSONL lines)
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_parallel",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_p1", "name": "Read", "input": {"file_path": "/a.txt"}},
                ],
            },
        })
        render(state, {
            "type": "assistant",
            "uuid": "a2",
            "requestId": "req_parallel",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_p2", "name": "Glob", "input": {"pattern": "**/*.py"}},
                ],
            },
        })

        assert len(state.elements) == 2
        assert state.elements[0].tool_name == "Read"
        assert state.elements[1].tool_name == "Glob"
        assert "toolu_p1" in state.tool_calls
        assert "toolu_p2" in state.tool_calls

        # Results come in as separate user messages
        render(state, {
            "type": "user",
            "uuid": "u1",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_p1", "content": "file a content"}],
            },
        })
        render(state, {
            "type": "user",
            "uuid": "u2",
            "isSidechain": False,
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_p2", "content": "found 5 files"}],
            },
        })

        assert state.elements[0].result == "file a content"
        assert state.elements[1].result == "found 5 files"


class TestContentBlockMerging:
    """Test that assistant blocks with same requestId are grouped."""

    def test_same_request_id_grouped(self, state: ScreenState) -> None:
        render(state, {
            "type": "assistant",
            "uuid": "a1",
            "requestId": "req_merge",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "hmm", "signature": "sig"}],
            },
        })
        render(state, {
            "type": "assistant",
            "uuid": "a2",
            "requestId": "req_merge",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Here is my response."}],
            },
        })

        assert len(state.elements) == 2
        assert state.elements[0].request_id == "req_merge"
        assert state.elements[1].request_id == "req_merge"
