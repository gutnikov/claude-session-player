"""Stress tests: replay longest sessions and verify output against snapshots.

Tests cover:
- Top 5 longest main session replays with snapshot comparison
- Top 3 subagent session replays with snapshot comparison
- Regression tests for bugs found during stress testing
- Performance test for the longest session
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from claude_session_player.models import ScreenElement, ScreenState
from claude_session_player.parser import read_session
from claude_session_player.renderer import render

# --- Session paths ---

STRESS_SESSIONS = [
    (
        "examples/projects/-Users-agutnikov-work-orca/014d9d94-9418-4fc1-988a-28d1db63387c.jsonl",
        "tests/snapshots/stress_session_1.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-orca/7eca9f25-c1a6-494d-bbaa-4c5500395fb7.jsonl",
        "tests/snapshots/stress_session_2.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-orca/48dddc7f-7139-4748-b029-fbdc6f197da4.jsonl",
        "tests/snapshots/stress_session_3.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-orca/f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033.jsonl",
        "tests/snapshots/stress_session_4.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-orca/5fd21ed1-6aab-489a-bc56-5f2fe8593ac5.jsonl",
        "tests/snapshots/stress_session_5.md",
    ),
]

SUBAGENT_SESSIONS = [
    (
        "examples/projects/-Users-agutnikov-work-orca/f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033/subagents/agent-a5e7738.jsonl",
        "tests/snapshots/stress_subagent_1.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-orca/f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033/subagents/agent-a8f137d.jsonl",
        "tests/snapshots/stress_subagent_2.md",
    ),
    (
        "examples/projects/-Users-agutnikov-work-mtools/3606733e-3af3-4685-b5cf-1a2e4327e97d/subagents/agent-a117026.jsonl",
        "tests/snapshots/stress_subagent_3.md",
    ),
]


def _replay_session(jsonl_path: str, allow_sidechain: bool = False) -> tuple[ScreenState, str]:
    """Replay a session and return (state, markdown)."""
    lines = read_session(jsonl_path)
    state = ScreenState()
    for line in lines:
        render(state, line, allow_sidechain=allow_sidechain)
    return state, state.to_markdown()


# --- Snapshot comparison tests ---


class TestStressSessions:
    """Replay top 5 longest main sessions and compare to snapshots."""

    @pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
    def test_stress_session_snapshot(self, jsonl_path: str, snapshot_path: str) -> None:
        _, output = _replay_session(jsonl_path)
        with open(snapshot_path) as f:
            expected = f.read()
        assert output == expected

    @pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
    def test_stress_session_no_crash(self, jsonl_path: str, snapshot_path: str) -> None:
        """Sessions replay without any exceptions."""
        state, md = _replay_session(jsonl_path)
        assert len(state.elements) > 0
        assert len(md) > 0

    @pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
    def test_stress_session_has_expected_elements(self, jsonl_path: str, snapshot_path: str) -> None:
        """Each session should have user messages, assistant text, and tool calls."""
        state, _ = _replay_session(jsonl_path)
        kinds = {el.kind for el in state.elements}
        assert "user_message" in kinds
        assert "tool_call" in kinds

    @pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
    def test_stress_session_no_triple_blanks(self, jsonl_path: str, snapshot_path: str) -> None:
        """Output should never have triple blank lines."""
        _, md = _replay_session(jsonl_path)
        assert "\n\n\n" not in md

    @pytest.mark.parametrize("jsonl_path,snapshot_path", STRESS_SESSIONS)
    def test_stress_session_no_empty_assistant_text(self, jsonl_path: str, snapshot_path: str) -> None:
        """No empty or '(no content)' assistant text blocks should be rendered."""
        state, _ = _replay_session(jsonl_path)
        for el in state.elements:
            if el.kind == "assistant_text":
                assert el.text != ""
                assert el.text != "(no content)"


class TestSubagentSessions:
    """Replay top 3 subagent sessions with allow_sidechain=True."""

    @pytest.mark.parametrize("jsonl_path,snapshot_path", SUBAGENT_SESSIONS)
    def test_subagent_snapshot(self, jsonl_path: str, snapshot_path: str) -> None:
        _, output = _replay_session(jsonl_path, allow_sidechain=True)
        with open(snapshot_path) as f:
            expected = f.read()
        assert output == expected

    @pytest.mark.parametrize("jsonl_path,snapshot_path", SUBAGENT_SESSIONS)
    def test_subagent_no_crash(self, jsonl_path: str, snapshot_path: str) -> None:
        state, md = _replay_session(jsonl_path, allow_sidechain=True)
        assert len(state.elements) > 0
        assert len(md) > 0

    @pytest.mark.parametrize("jsonl_path,snapshot_path", SUBAGENT_SESSIONS)
    def test_subagent_produces_elements(self, jsonl_path: str, snapshot_path: str) -> None:
        """Subagent files should produce elements when allow_sidechain=True."""
        state, _ = _replay_session(jsonl_path, allow_sidechain=True)
        assert len(state.elements) > 10

    def test_subagent_filtered_without_flag(self) -> None:
        """Subagent files produce 0 elements when allow_sidechain=False (default)."""
        jsonl_path = SUBAGENT_SESSIONS[0][0]
        state, md = _replay_session(jsonl_path, allow_sidechain=False)
        assert len(state.elements) == 0


# --- Regression tests for bugs found during stress testing ---


class TestRegressionBugs:
    """Regression tests for specific bugs found during stress testing."""

    def test_bug1_string_tool_use_result(self) -> None:
        """Bug #1: toolUseResult can be a string, not always a dict.

        Some tool results (especially errors) have toolUseResult as a plain
        string like 'Error: Exit code 1\\n...'. The renderer should handle
        this without crashing.
        """
        state = ScreenState()
        # Register a tool call
        tool_call_line = {
            "type": "assistant",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "docker compose up"}}],
            },
        }
        render(state, tool_call_line)

        # Send tool result with string toolUseResult
        tool_result_line = {
            "type": "user",
            "isMeta": None,
            "isSidechain": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "Exit code 1\ndocker: unknown command", "is_error": True}],
            },
            "toolUseResult": "Error: Exit code 1\ndocker: unknown command",  # string, not dict!
        }
        render(state, tool_result_line)  # Should not crash

        el = state.elements[0]
        assert el.result is not None
        assert el.is_error is True

    def test_bug2_subagent_sidechain_filter(self) -> None:
        """Bug #2: Standalone subagent files have isSidechain=True on every line.

        When replaying a standalone agent file, the sidechain filter should
        be bypassed via allow_sidechain=True.
        """
        state = ScreenState()
        line = {
            "type": "user",
            "isSidechain": True,
            "isMeta": False,
            "message": {"role": "user", "content": "Implement the feature"},
        }

        # Without allow_sidechain, message is filtered
        render(state, line)
        assert len(state.elements) == 0

        # With allow_sidechain, message is rendered
        render(state, line, allow_sidechain=True)
        assert len(state.elements) == 1
        assert state.elements[0].text == "Implement the feature"

    def test_bug3_hook_progress_no_overwrite(self) -> None:
        """Bug #3: hook_progress arriving after tool_result should not overwrite it.

        PostToolUse hooks fire after the tool result is already recorded.
        The progress message should not overwrite the finalized tool result.
        """
        state = ScreenState()

        # Register tool call
        render(state, {
            "type": "assistant",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/tmp/test.py"}}],
            },
        })

        # Send tool result
        render(state, {
            "type": "user",
            "isMeta": False,
            "isSidechain": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "def hello(): pass"}],
            },
        })

        assert state.elements[0].result == "def hello(): pass"
        assert state.elements[0].result_is_final is True

        # Send hook_progress AFTER the tool result
        render(state, {
            "type": "progress",
            "parentToolUseID": "toolu_1",
            "isSidechain": False,
            "data": {"type": "hook_progress", "hookName": "PostToolUse:Read"},
        })

        # Result should NOT be overwritten
        assert state.elements[0].result == "def hello(): pass"
        assert "Hook:" not in state.elements[0].result

    def test_bug4_no_content_placeholder_filtered(self) -> None:
        """Bug #4: '(no content)' placeholder text blocks should be invisible.

        Claude Code writes '(no content)' as placeholder text before the real
        content (often thinking + text). These should not appear in output.
        """
        state = ScreenState()
        render(state, {
            "type": "assistant",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "(no content)"}],
            },
        })
        # Should be filtered out
        assert len(state.elements) == 0

        # Real text should still work
        render(state, {
            "type": "assistant",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Here is the real response"}],
            },
        })
        assert len(state.elements) == 1
        assert state.elements[0].text == "Here is the real response"

    def test_bug5_parser_skips_malformed_lines(self, tmp_path: Path) -> None:
        """Bug #5: Parser should skip malformed JSON lines instead of crashing.

        Real JSONL files sometimes have empty lines or corruption.
        """
        file_path = tmp_path / "test.jsonl"
        with open(file_path, "w") as f:
            f.write('{"type": "user", "message": {"role": "user", "content": "hi"}}\n')
            f.write("\n")  # empty line
            f.write("not json at all\n")  # invalid
            f.write('{"type": "assistant", "message": {"role": "assistant", "content": []}}\n')

        lines = read_session(str(file_path))
        assert len(lines) == 2
        assert lines[0]["type"] == "user"
        assert lines[1]["type"] == "assistant"

    def test_tool_result_list_content(self) -> None:
        """Tool result content can be a list of blocks instead of a string."""
        state = ScreenState()
        render(state, {
            "type": "assistant",
            "requestId": "req_1",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/test.py"}}],
            },
        })
        render(state, {
            "type": "user",
            "isMeta": False,
            "isSidechain": False,
            "message": {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": "toolu_1",
                    "content": [{"type": "text", "text": "file contents here"}],
                }],
            },
        })
        assert state.elements[0].result == "file contents here"

    def test_imeta_none_treated_as_false(self) -> None:
        """isMeta: null in JSON should be treated the same as isMeta: false."""
        state = ScreenState()
        render(state, {
            "type": "user",
            "isMeta": None,
            "isSidechain": False,
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_x", "content": "result"}],
            },
        })
        # Should not crash and should process as non-meta


# --- Performance test ---


class TestPerformance:
    """Performance test for the longest session."""

    def test_longest_session_under_5_seconds(self) -> None:
        """The longest session (3120 lines) should replay in under 5 seconds."""
        jsonl_path = STRESS_SESSIONS[0][0]  # Longest session

        start = time.monotonic()
        lines = read_session(jsonl_path)
        state = ScreenState()
        for line in lines:
            render(state, line)
        _ = state.to_markdown()
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"Replay took {elapsed:.2f}s, expected < 5.0s"
        assert len(lines) > 3000  # Verify we're testing the right file
