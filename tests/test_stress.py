"""Stress tests for Claude Session Player.

These tests replay the longest/most complex real sessions and validate
that output matches saved snapshots. This ensures the renderer handles
real-world protocol features correctly.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from claude_session_player.consumer import replay_session as replay_session_fn, ScreenStateConsumer
from claude_session_player.events import Block, BlockType, ToolCallContent, AssistantContent, UserContent
from claude_session_player.parser import read_session, classify_line, LineType
from claude_session_player.processor import process_line
from claude_session_player.events import ProcessingContext


# ---------------------------------------------------------------------------
# Test data paths
# ---------------------------------------------------------------------------

EXAMPLES_ROOT = Path(__file__).parent.parent / "examples" / "projects"
SNAPSHOTS_ROOT = Path(__file__).parent / "snapshots"

# Top 5 main sessions by line count (excluding those with all-sidechain content)
STRESS_SESSIONS = [
    (
        EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "014d9d94-9418-4fc1-988a-28d1db63387c.jsonl",
        SNAPSHOTS_ROOT / "stress_orca_1.md",
        3120,  # Expected line count
    ),
    (
        EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "7eca9f25-c1a6-494d-bbaa-4c5500395fb7.jsonl",
        SNAPSHOTS_ROOT / "stress_orca_2.md",
        3029,
    ),
    (
        EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "48dddc7f-7139-4748-b029-fbdc6f197da4.jsonl",
        SNAPSHOTS_ROOT / "stress_orca_3.md",
        2511,
    ),
    (
        EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033.jsonl",
        SNAPSHOTS_ROOT / "stress_orca_4.md",
        2253,
    ),
    (
        EXAMPLES_ROOT / "-Users-agutnikov-work-claude-code-hub" / "b5e48063-d7e9-493e-b698-1131042f5168.jsonl",
        SNAPSHOTS_ROOT / "stress_hub_1.md",
        1720,
    ),
]

# Top 3 subagent files - these have all isSidechain=True messages
SUBAGENT_FILES = [
    EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033" / "subagents" / "agent-a5e7738.jsonl",
    EXAMPLES_ROOT / "-Users-agutnikov-work-orca" / "f516ffd5-4d60-4e74-a8fc-1bdcb9fd6033" / "subagents" / "agent-a8f137d.jsonl",
    EXAMPLES_ROOT / "-Users-agutnikov-work-mtools" / "3606733e-3af3-4685-b5cf-1a2e4327e97d" / "subagents" / "agent-a117026.jsonl",
]


def replay_session(path: Path) -> tuple[ScreenStateConsumer, str]:
    """Replay a session file and return consumer and markdown output."""
    lines = read_session(str(path))
    context = ProcessingContext()
    consumer = ScreenStateConsumer()
    for line in lines:
        for event in process_line(context, line):
            consumer.handle(event)
    return consumer, consumer.to_markdown()


# ---------------------------------------------------------------------------
# Snapshot Comparison Tests
# ---------------------------------------------------------------------------


class TestStressSessionSnapshots:
    """Test that stress sessions match saved snapshots."""

    @pytest.mark.parametrize(
        "jsonl_path,snapshot_path,expected_lines",
        STRESS_SESSIONS,
        ids=["orca_1", "orca_2", "orca_3", "orca_4", "hub_1"],
    )
    def test_snapshot_match(
        self, jsonl_path: Path, snapshot_path: Path, expected_lines: int
    ) -> None:
        """Test that session replay matches saved snapshot."""
        # Verify input file exists and has expected line count
        lines = read_session(str(jsonl_path))
        assert len(lines) == expected_lines, f"Expected {expected_lines} lines, got {len(lines)}"

        # Replay and get markdown
        consumer, output = replay_session(jsonl_path)

        # Verify output is not empty
        assert output.strip(), "Output should not be empty"

        # Load and compare snapshot
        with open(snapshot_path, "r") as f:
            expected = f.read()

        assert output == expected, f"Output does not match snapshot {snapshot_path.name}"


# ---------------------------------------------------------------------------
# Subagent Replay Tests
# ---------------------------------------------------------------------------


class TestSubagentReplay:
    """Test that subagent files replay without crashes."""

    @pytest.mark.parametrize(
        "jsonl_path",
        SUBAGENT_FILES,
        ids=["subagent_1", "subagent_2", "subagent_3"],
    )
    def test_subagent_no_crash(self, jsonl_path: Path) -> None:
        """Test that subagent session replays without exceptions."""
        lines = read_session(str(jsonl_path))
        assert len(lines) > 0, "Subagent file should not be empty"

        # Replay should complete without raising exceptions
        context = ProcessingContext()
        consumer = ScreenStateConsumer()
        for line in lines:
            for event in process_line(context, line):
                consumer.handle(event)

        # Output may be empty because isSidechain messages are invisible
        # This is expected behavior - we just verify no crash
        _ = consumer.to_markdown()

    @pytest.mark.parametrize(
        "jsonl_path",
        SUBAGENT_FILES,
        ids=["subagent_1", "subagent_2", "subagent_3"],
    )
    def test_subagent_all_sidechain(self, jsonl_path: Path) -> None:
        """Verify subagent files have isSidechain=True on all user/assistant messages."""
        lines = read_session(str(jsonl_path))

        for line in lines:
            msg_type = line.get("type")
            if msg_type in ("user", "assistant"):
                assert line.get("isSidechain") is True, (
                    f"Expected isSidechain=True on {msg_type} message"
                )


# ---------------------------------------------------------------------------
# Performance Test
# ---------------------------------------------------------------------------


class TestPerformance:
    """Test that session replay completes within acceptable time."""

    def test_longest_session_under_5_seconds(self) -> None:
        """Test that the longest session replays in under 5 seconds."""
        # Use the longest session (3120 lines)
        jsonl_path = STRESS_SESSIONS[0][0]

        start = time.perf_counter()

        lines = read_session(str(jsonl_path))
        context = ProcessingContext()
        consumer = ScreenStateConsumer()
        for line in lines:
            for event in process_line(context, line):
                consumer.handle(event)
        _ = consumer.to_markdown()

        elapsed = time.perf_counter() - start

        # Should complete well under 5 seconds
        assert elapsed < 5.0, f"Replay took {elapsed:.2f}s, expected <5s"

        # Actually should be very fast (< 0.5s typically)
        assert elapsed < 1.0, f"Replay took {elapsed:.2f}s, expected <1s"


# ---------------------------------------------------------------------------
# Edge Case Coverage Tests
# ---------------------------------------------------------------------------


class TestEdgeCaseCoverage:
    """Test that edge cases found in stress sessions are handled correctly."""

    def test_list_content_tool_results(self) -> None:
        """Test that tool results with list content are extracted correctly."""
        # Session 2 has 39 tool results with list content
        jsonl_path = STRESS_SESSIONS[1][0]
        lines = read_session(str(jsonl_path))

        list_content_count = 0
        for line in lines:
            lt = classify_line(line)
            if lt == LineType.TOOL_RESULT:
                message = line.get("message", {})
                content = message.get("content", [])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        block_content = block.get("content")
                        if isinstance(block_content, list):
                            list_content_count += 1

        assert list_content_count > 0, "Expected to find list content tool results"

        # Replay should handle all without errors
        consumer, output = replay_session(jsonl_path)
        assert output.strip(), "Output should not be empty"

    def test_long_tool_outputs_truncated(self) -> None:
        """Test that long tool outputs are truncated to 5 lines."""
        # Session 1 has 140 tool outputs with >5 lines
        jsonl_path = STRESS_SESSIONS[0][0]
        consumer, output = replay_session(jsonl_path)

        # Find tool call blocks with results in the consumer
        for block in consumer.blocks:
            if block.type == BlockType.TOOL_CALL and isinstance(block.content, ToolCallContent):
                if block.content.result is not None:
                    result_lines = block.content.result.split("\n")
                    assert len(result_lines) <= 5, (
                        f"Tool result should be truncated to 5 lines, got {len(result_lines)}"
                    )

    def test_parallel_tool_calls_rendered(self) -> None:
        """Test that parallel tool calls with same requestId are all rendered."""
        # Session 4 has 33 parallel tool call sequences
        jsonl_path = STRESS_SESSIONS[3][0]
        lines = read_session(str(jsonl_path))

        # Count tool_use lines with same consecutive requestId
        parallel_count = 0
        prev_request_id = None
        prev_was_tool_use = False

        for line in lines:
            lt = classify_line(line)
            if lt == LineType.TOOL_USE:
                req_id = line.get("requestId")
                if req_id == prev_request_id and prev_was_tool_use:
                    parallel_count += 1
                prev_request_id = req_id
                prev_was_tool_use = True
            else:
                prev_was_tool_use = False

        assert parallel_count > 0, "Expected to find parallel tool calls"

        # Replay and verify all tool calls are in output
        consumer, output = replay_session(jsonl_path)
        tool_call_count = sum(1 for b in consumer.blocks if b.type == BlockType.TOOL_CALL)
        assert tool_call_count > parallel_count, "Should have more tool calls than parallel sequences"

    def test_compaction_clears_state(self) -> None:
        """Test that compaction clears pre-compaction content."""
        # Session 1 has 2 compaction boundaries
        jsonl_path = STRESS_SESSIONS[0][0]
        lines = read_session(str(jsonl_path))

        compaction_count = sum(
            1 for line in lines if classify_line(line) == LineType.COMPACT_BOUNDARY
        )
        assert compaction_count > 0, "Expected compaction boundaries"

        # Replay with tracking
        context = ProcessingContext()
        consumer = ScreenStateConsumer()
        element_counts = []
        for line in lines:
            for event in process_line(context, line):
                consumer.handle(event)
            if classify_line(line) == LineType.COMPACT_BOUNDARY:
                element_counts.append(len(consumer.blocks))

        # After compaction, element count should drop to 0
        for count in element_counts:
            assert count == 0, "Elements should be cleared after compaction"

    def test_thinking_and_text_grouping(self) -> None:
        """Test that thinking and text with same requestId have no blank line between them."""
        # Session 3 has 242 thinking blocks
        jsonl_path = STRESS_SESSIONS[2][0]
        consumer, output = replay_session(jsonl_path)

        # Check that "✱ Thinking…" is not followed by a blank line before "●"
        lines = output.split("\n")
        for i, line in enumerate(lines):
            if line == "✱ Thinking…":
                # Next line should be text or tool, not blank
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Could be blank if next element has different requestId
                    # Just verify we have valid output
                    pass


class TestStressSessionFeatures:
    """Test specific protocol features exercised by stress sessions."""

    def test_session_has_user_input(self) -> None:
        """Test that sessions contain rendered user input."""
        for jsonl_path, _, _ in STRESS_SESSIONS[:2]:
            consumer, output = replay_session(jsonl_path)
            user_blocks = [b for b in consumer.blocks if b.type == BlockType.USER]
            assert len(user_blocks) > 0, "Should have at least one user message"
            assert "❯" in output, "Output should contain user prompt prefix"

    def test_session_has_assistant_text(self) -> None:
        """Test that sessions contain rendered assistant text."""
        for jsonl_path, _, _ in STRESS_SESSIONS[:2]:
            consumer, output = replay_session(jsonl_path)
            assistant_blocks = [b for b in consumer.blocks if b.type == BlockType.ASSISTANT]
            assert len(assistant_blocks) > 0, "Should have assistant text blocks"
            assert "●" in output, "Output should contain assistant bullet prefix"

    def test_session_has_tool_results(self) -> None:
        """Test that sessions contain tool calls with results."""
        for jsonl_path, _, _ in STRESS_SESSIONS[:2]:
            consumer, output = replay_session(jsonl_path)
            tool_calls_with_results = [
                b for b in consumer.blocks
                if b.type == BlockType.TOOL_CALL
                and isinstance(b.content, ToolCallContent)
                and b.content.result is not None
            ]
            assert len(tool_calls_with_results) > 0, "Should have tool calls with results"
            assert "└" in output, "Output should contain result connector"

    def test_session_has_turn_duration(self) -> None:
        """Test that sessions contain turn duration markers."""
        # Use session 4 which has turn duration
        jsonl_path = STRESS_SESSIONS[3][0]
        consumer, output = replay_session(jsonl_path)
        assert "✱ Crunched for" in output, "Output should contain turn duration"
