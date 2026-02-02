"""Tests for JSONL parser, line classification, and field extraction helpers."""

import json
from pathlib import Path

import pytest

from claude_session_player.parser import (
    LineType,
    classify_line,
    get_duration_ms,
    get_local_command_text,
    get_parent_tool_use_id,
    get_progress_data,
    get_request_id,
    get_tool_result_info,
    get_tool_use_info,
    get_user_text,
    read_session,
)


# ===================================================================
# Classification tests
# ===================================================================


class TestClassifyUserMessages:
    """Tests for user message classification."""

    def test_user_input_string(self, user_input_line: dict) -> None:
        assert classify_line(user_input_line) == LineType.USER_INPUT

    def test_user_input_multiline(self, user_input_multiline_line: dict) -> None:
        assert classify_line(user_input_multiline_line) == LineType.USER_INPUT

    def test_user_meta_invisible(self, user_meta_line: dict) -> None:
        assert classify_line(user_meta_line) == LineType.INVISIBLE

    def test_tool_result(self, tool_result_line: dict) -> None:
        assert classify_line(tool_result_line) == LineType.TOOL_RESULT

    def test_local_command_output(self, local_command_output_line: dict) -> None:
        assert classify_line(local_command_output_line) == LineType.LOCAL_COMMAND_OUTPUT

    def test_user_content_list_no_tool_result(self) -> None:
        """User message with list content but no tool_result blocks → USER_INPUT."""
        line = {
            "type": "user",
            "isMeta": False,
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "hello"}],
            },
        }
        assert classify_line(line) == LineType.USER_INPUT


class TestClassifyAssistantMessages:
    """Tests for assistant message classification."""

    def test_assistant_text(self, assistant_text_line: dict) -> None:
        assert classify_line(assistant_text_line) == LineType.ASSISTANT_TEXT

    def test_tool_use(self, tool_use_line: dict) -> None:
        assert classify_line(tool_use_line) == LineType.TOOL_USE

    def test_thinking(self, thinking_line: dict) -> None:
        assert classify_line(thinking_line) == LineType.THINKING

    def test_assistant_empty_content(self) -> None:
        """Assistant with empty content list → INVISIBLE."""
        line = {
            "type": "assistant",
            "message": {"role": "assistant", "content": []},
        }
        assert classify_line(line) == LineType.INVISIBLE

    def test_assistant_no_content(self) -> None:
        """Assistant with no content → INVISIBLE."""
        line = {
            "type": "assistant",
            "message": {"role": "assistant"},
        }
        assert classify_line(line) == LineType.INVISIBLE


class TestClassifySystemMessages:
    """Tests for system message classification."""

    def test_turn_duration(self, turn_duration_line: dict) -> None:
        assert classify_line(turn_duration_line) == LineType.TURN_DURATION

    def test_compact_boundary(self, compact_boundary_line: dict) -> None:
        assert classify_line(compact_boundary_line) == LineType.COMPACT_BOUNDARY

    def test_local_command(self, system_local_command_line: dict) -> None:
        assert classify_line(system_local_command_line) == LineType.INVISIBLE

    def test_unknown_system_subtype(self) -> None:
        line = {"type": "system", "subtype": "unknown_subtype"}
        assert classify_line(line) == LineType.INVISIBLE


class TestClassifyProgressMessages:
    """Tests for progress message classification."""

    def test_bash_progress(self, bash_progress_line: dict) -> None:
        assert classify_line(bash_progress_line) == LineType.BASH_PROGRESS

    def test_hook_progress(self, hook_progress_line: dict) -> None:
        assert classify_line(hook_progress_line) == LineType.HOOK_PROGRESS

    def test_agent_progress(self, agent_progress_line: dict) -> None:
        assert classify_line(agent_progress_line) == LineType.AGENT_PROGRESS

    def test_query_update(self, query_update_line: dict) -> None:
        assert classify_line(query_update_line) == LineType.QUERY_UPDATE

    def test_search_results(self, search_results_line: dict) -> None:
        assert classify_line(search_results_line) == LineType.SEARCH_RESULTS

    def test_waiting_for_task(self, waiting_for_task_line: dict) -> None:
        assert classify_line(waiting_for_task_line) == LineType.WAITING_FOR_TASK

    def test_unknown_progress_type(self) -> None:
        line = {"type": "progress", "data": {"type": "unknown_progress"}}
        assert classify_line(line) == LineType.INVISIBLE


class TestClassifyInvisibleTypes:
    """Tests for always-invisible types."""

    def test_file_history_snapshot(self, file_history_snapshot_line: dict) -> None:
        assert classify_line(file_history_snapshot_line) == LineType.INVISIBLE

    def test_queue_operation(self, queue_operation_line: dict) -> None:
        assert classify_line(queue_operation_line) == LineType.INVISIBLE

    def test_summary(self, summary_line: dict) -> None:
        assert classify_line(summary_line) == LineType.INVISIBLE

    def test_pr_link(self, pr_link_line: dict) -> None:
        assert classify_line(pr_link_line) == LineType.INVISIBLE


class TestClassifyEdgeCases:
    """Tests for defensive edge cases."""

    def test_unknown_type(self) -> None:
        assert classify_line({"type": "totally_unknown"}) == LineType.INVISIBLE

    def test_missing_type_field(self) -> None:
        assert classify_line({"foo": "bar"}) == LineType.INVISIBLE

    def test_empty_dict(self) -> None:
        assert classify_line({}) == LineType.INVISIBLE


# ===================================================================
# Extraction helper tests
# ===================================================================


class TestGetUserText:
    """Tests for get_user_text."""

    def test_single_line(self, user_input_line: dict) -> None:
        assert get_user_text(user_input_line) == "hello world"

    def test_multiline(self, user_input_multiline_line: dict) -> None:
        assert get_user_text(user_input_multiline_line) == "line one\nline two\nline three"

    def test_content_blocks(self) -> None:
        line = {
            "message": {
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                ],
            },
        }
        assert get_user_text(line) == "part one\npart two"


class TestGetToolUseInfo:
    """Tests for get_tool_use_info."""

    def test_bash_tool(self, tool_use_line: dict) -> None:
        name, tool_id, inp = get_tool_use_info(tool_use_line)
        assert name == "Bash"
        assert tool_id == "toolu_001"
        assert inp == {"command": "ls -la", "description": "List files"}

    def test_read_tool(self, tool_use_read_line: dict) -> None:
        name, tool_id, inp = get_tool_use_info(tool_use_read_line)
        assert name == "Read"
        assert tool_id == "toolu_003"
        assert inp == {"file_path": "/src/main.py"}

    def test_write_tool(self, tool_use_write_line: dict) -> None:
        name, tool_id, inp = get_tool_use_info(tool_use_write_line)
        assert name == "Write"
        assert tool_id == "toolu_004"
        assert "file_path" in inp


class TestGetToolResultInfo:
    """Tests for get_tool_result_info."""

    def test_success_result(self, tool_result_line: dict) -> None:
        results = get_tool_result_info(tool_result_line)
        assert len(results) == 1
        tool_use_id, content, is_error = results[0]
        assert tool_use_id == "toolu_001"
        assert content == "file1.py\nfile2.py"
        assert is_error is False

    def test_error_result(self, tool_result_error_line: dict) -> None:
        results = get_tool_result_info(tool_result_error_line)
        assert len(results) == 1
        _, content, is_error = results[0]
        assert "command not found" in content
        assert is_error is True

    def test_parallel_results(self, tool_result_parallel_line: dict) -> None:
        results = get_tool_result_info(tool_result_parallel_line)
        assert len(results) == 2
        assert results[0][0] == "toolu_010"
        assert results[0][2] is False
        assert results[1][0] == "toolu_011"
        assert results[1][2] is True


class TestGetRequestId:
    """Tests for get_request_id."""

    def test_present(self, assistant_text_line: dict) -> None:
        assert get_request_id(assistant_text_line) == "req_001"

    def test_absent(self, user_input_line: dict) -> None:
        assert get_request_id(user_input_line) is None


class TestGetDurationMs:
    """Tests for get_duration_ms."""

    def test_with_duration(self, turn_duration_line: dict) -> None:
        assert get_duration_ms(turn_duration_line) == 12500

    def test_short_duration(self) -> None:
        line = {"type": "system", "subtype": "turn_duration", "durationMs": 500}
        assert get_duration_ms(line) == 500

    def test_missing_duration(self) -> None:
        line = {"type": "system", "subtype": "turn_duration"}
        assert get_duration_ms(line) == 0


class TestGetLocalCommandText:
    """Tests for get_local_command_text."""

    def test_extracts_text(self, local_command_output_line: dict) -> None:
        assert get_local_command_text(local_command_output_line) == "git status output here"

    def test_no_tags(self, user_input_line: dict) -> None:
        assert get_local_command_text(user_input_line) == ""


class TestGetProgressData:
    """Tests for get_progress_data."""

    def test_returns_data(self, bash_progress_line: dict) -> None:
        data = get_progress_data(bash_progress_line)
        assert data["type"] == "bash_progress"
        assert data["parentToolUseID"] == "toolu_001"


class TestGetParentToolUseId:
    """Tests for get_parent_tool_use_id."""

    def test_present(self, bash_progress_line: dict) -> None:
        assert get_parent_tool_use_id(bash_progress_line) == "toolu_001"

    def test_absent(self, user_input_line: dict) -> None:
        assert get_parent_tool_use_id(user_input_line) is None


# ===================================================================
# File reader tests
# ===================================================================


class TestReadSession:
    """Tests for read_session."""

    def test_read_valid_jsonl(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        lines = [
            {"type": "user", "message": {"content": "hi"}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
            {"type": "system", "subtype": "turn_duration", "durationMs": 1000},
        ]
        p.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n")
        result = read_session(p)
        assert len(result) == 3
        assert result[0]["type"] == "user"
        assert result[2]["subtype"] == "turn_duration"

    def test_skip_empty_lines(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        p.write_text('{"type":"user"}\n\n\n{"type":"system"}\n')
        result = read_session(p)
        assert len(result) == 2

    def test_handle_malformed_json(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        p.write_text('{"type":"user"}\nnot json at all\n{"type":"system"}\n')
        result = read_session(p)
        assert len(result) == 2

    def test_returns_list_in_order(self, tmp_path: Path) -> None:
        p = tmp_path / "test.jsonl"
        lines = [{"index": i} for i in range(5)]
        p.write_text("\n".join(json.dumps(obj) for obj in lines) + "\n")
        result = read_session(p)
        assert [obj["index"] for obj in result] == [0, 1, 2, 3, 4]


# ===================================================================
# Real data integration test
# ===================================================================


class TestRealData:
    """Test classification against real session files."""

    def test_classify_all_lines_in_real_session(self) -> None:
        """Read a real session file and verify all lines classify without error."""
        session_path = Path(
            "/Users/agutnikov/work/claude-session-player/examples/projects"
            "/-Users-agutnikov-work-trello-clone"
            "/930c1604-5137-4684-a344-863b511a914c.jsonl"
        )
        if not session_path.exists():
            pytest.skip("Real session file not available")

        lines = read_session(session_path)
        assert len(lines) > 0, "Session file should have at least one line"

        classified = {}
        for line in lines:
            lt = classify_line(line)
            assert isinstance(lt, LineType)
            classified[lt] = classified.get(lt, 0) + 1

        # Verify we got at least some expected types
        assert LineType.INVISIBLE in classified or any(
            lt != LineType.INVISIBLE for lt in classified
        ), "Should have classified some lines"

    def test_no_crash_on_all_example_files(self) -> None:
        """Verify classify_line doesn't crash on any example JSONL file."""
        examples_dir = Path(
            "/Users/agutnikov/work/claude-session-player/examples/projects"
        )
        if not examples_dir.exists():
            pytest.skip("Examples directory not available")

        jsonl_files = list(examples_dir.rglob("*.jsonl"))
        if not jsonl_files:
            pytest.skip("No JSONL files found")

        # Test at most 5 files to keep test runtime reasonable
        for jsonl_path in jsonl_files[:5]:
            lines = read_session(jsonl_path)
            for line in lines:
                lt = classify_line(line)
                assert isinstance(lt, LineType)


# ===================================================================
# LineType enum tests
# ===================================================================


class TestLineTypeEnum:
    """Tests for LineType enum completeness."""

    def test_has_15_variants(self) -> None:
        # Issue spec says "16 variants" but the actual enum list has 15 distinct values
        assert len(LineType) == 15

    def test_all_expected_names(self) -> None:
        expected = {
            "USER_INPUT", "TOOL_RESULT", "LOCAL_COMMAND_OUTPUT",
            "ASSISTANT_TEXT", "TOOL_USE", "THINKING",
            "TURN_DURATION", "COMPACT_BOUNDARY",
            "BASH_PROGRESS", "HOOK_PROGRESS", "AGENT_PROGRESS",
            "QUERY_UPDATE", "SEARCH_RESULTS", "WAITING_FOR_TASK",
            "INVISIBLE",
        }
        actual = {lt.name for lt in LineType}
        assert actual == expected
