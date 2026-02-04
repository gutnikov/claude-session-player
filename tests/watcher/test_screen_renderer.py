"""Tests for the ScreenRenderer component."""

from __future__ import annotations

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    Question,
    QuestionContent,
    QuestionOption,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.screen_renderer import (
    PRESET_DIMENSIONS,
    Dimensions,
    Preset,
    ScreenRenderer,
    render_events,
)


class TestScreenRendererBasics:
    """Test basic rendering functionality."""

    def test_empty_events(self):
        """Test rendering with no events."""
        renderer = ScreenRenderer()
        result = render_events([], preset=Preset.DESKTOP)

        # Should produce a frame with empty content
        lines = result.split("\n")
        dims = PRESET_DIMENSIONS[Preset.DESKTOP]
        assert len(lines) == dims.rows
        assert all(len(line) == dims.cols for line in lines)

    def test_preset_desktop_dimensions(self):
        """Test desktop preset produces correct dimensions."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello"),
                )
            )
        ]
        result = render_events(events, preset=Preset.DESKTOP)

        lines = result.split("\n")
        dims = PRESET_DIMENSIONS[Preset.DESKTOP]
        assert len(lines) == dims.rows
        assert all(len(line) == dims.cols for line in lines)

    def test_preset_mobile_dimensions(self):
        """Test mobile preset produces correct dimensions."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello"),
                )
            )
        ]
        result = render_events(events, preset=Preset.MOBILE)

        lines = result.split("\n")
        dims = PRESET_DIMENSIONS[Preset.MOBILE]
        assert len(lines) == dims.rows
        assert all(len(line) == dims.cols for line in lines)

    def test_custom_dimensions(self):
        """Test custom dimensions override preset."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello"),
                )
            )
        ]
        result = render_events(events, rows=10, cols=30)

        lines = result.split("\n")
        assert len(lines) == 10
        assert all(len(line) == 30 for line in lines)

    def test_requires_preset_or_dimensions(self):
        """Test that either preset or dimensions must be provided."""
        renderer = ScreenRenderer()
        with pytest.raises(ValueError, match="Must provide either preset or rows/cols"):
            renderer.render([])


class TestBlockTypeRendering:
    """Test rendering of different block types."""

    def test_user_block(self):
        """Test USER block rendering."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello world"),
                )
            )
        ]
        result = render_events(events, rows=5, cols=30)

        assert "> Hello world" in result

    def test_user_block_multiline(self):
        """Test USER block with multiple lines."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello\nworld"),
                )
            )
        ]
        result = render_events(events, rows=5, cols=30)

        assert "> Hello" in result
        assert "  world" in result

    def test_user_block_empty(self):
        """Test USER block with empty text."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text=""),
                )
            )
        ]
        result = render_events(events, rows=5, cols=30)

        # Should show just the prompt
        lines = result.split("\n")
        content_lines = [l for l in lines if ">" in l and "│" in l]
        assert len(content_lines) >= 1

    def test_assistant_block(self):
        """Test ASSISTANT block rendering."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Hello from Claude"),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Hello from Claude" in result

    def test_assistant_block_multiline(self):
        """Test ASSISTANT block with multiple lines."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Line one\nLine two"),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Line one" in result
        assert "  Line two" in result

    def test_tool_call_block_no_result(self):
        """Test TOOL_CALL block without result."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Bash",
                        tool_use_id="tu_1",
                        label="ls -la",
                    ),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Bash(ls -la)" in result

    def test_tool_call_block_with_result(self):
        """Test TOOL_CALL block with result."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Bash",
                        tool_use_id="tu_1",
                        label="ls",
                        result="file1.txt\nfile2.txt",
                    ),
                )
            )
        ]
        result = render_events(events, rows=8, cols=40)

        assert "* Bash(ls)" in result
        assert "  > file1.txt" in result
        assert "    file2.txt" in result

    def test_tool_call_block_with_error(self):
        """Test TOOL_CALL block with error result."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Bash",
                        tool_use_id="tu_1",
                        label="bad_cmd",
                        result="command not found",
                        is_error=True,
                    ),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Bash(bad_cmd)" in result
        assert "  X command not found" in result

    def test_tool_call_block_with_progress(self):
        """Test TOOL_CALL block with progress text."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Task",
                        tool_use_id="tu_1",
                        label="build",
                        progress_text="50% complete",
                    ),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Task(build)" in result
        assert "  > 50% complete" in result

    def test_thinking_block(self):
        """Test THINKING block rendering."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.THINKING,
                    content=ThinkingContent(),
                )
            )
        ]
        result = render_events(events, rows=5, cols=30)

        assert "* Thinking..." in result

    def test_duration_block(self):
        """Test DURATION block rendering."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.DURATION,
                    content=DurationContent(duration_ms=5000),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Crunched for 5s" in result

    def test_system_block(self):
        """Test SYSTEM block rendering."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.SYSTEM,
                    content=SystemContent(text="Context compacted"),
                )
            )
        ]
        result = render_events(events, rows=5, cols=40)

        assert "Context compacted" in result

    def test_question_block_pending(self):
        """Test QUESTION block rendering with pending question."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.QUESTION,
                    content=QuestionContent(
                        tool_use_id="tu_1",
                        questions=[
                            Question(
                                question="Which option?",
                                header="Choice",
                                options=[
                                    QuestionOption(label="Option A", description="A"),
                                    QuestionOption(label="Option B", description="B"),
                                ],
                            )
                        ],
                    ),
                )
            )
        ]
        result = render_events(events, rows=10, cols=50)

        assert "* Question: Choice" in result
        assert "  | Which option?" in result
        assert "  | [ ] Option A" in result
        assert "  | [ ] Option B" in result
        assert "  > (awaiting response)" in result

    def test_question_block_answered(self):
        """Test QUESTION block rendering with answered question."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.QUESTION,
                    content=QuestionContent(
                        tool_use_id="tu_1",
                        questions=[
                            Question(
                                question="Which option?",
                                header="Choice",
                                options=[
                                    QuestionOption(label="Option A", description="A"),
                                    QuestionOption(label="Option B", description="B"),
                                ],
                            )
                        ],
                        answers={"Which option?": "Option A"},
                    ),
                )
            )
        ]
        result = render_events(events, rows=10, cols=50)

        assert "* Question: Choice" in result
        assert "  | Which option?" in result
        assert "  > [x] Option A" in result
        assert "[ ] Option" not in result


class TestEventProcessing:
    """Test event processing logic."""

    def test_update_block(self):
        """Test UpdateBlock event updates content."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Bash",
                        tool_use_id="tu_1",
                        label="ls",
                    ),
                )
            ),
            UpdateBlock(
                block_id="1",
                content=ToolCallContent(
                    tool_name="Bash",
                    tool_use_id="tu_1",
                    label="ls",
                    result="file.txt",
                ),
            ),
        ]
        result = render_events(events, rows=5, cols=40)

        assert "* Bash(ls)" in result
        assert "  > file.txt" in result

    def test_clear_all(self):
        """Test ClearAll event clears all blocks."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Hello"),
                )
            ),
            ClearAll(),
            AddBlock(
                Block(
                    id="2",
                    type=BlockType.USER,
                    content=UserContent(text="After clear"),
                )
            ),
        ]
        result = render_events(events, rows=5, cols=40)

        assert "Hello" not in result
        assert "> After clear" in result

    def test_multiple_blocks(self):
        """Test rendering multiple blocks."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="Question"),
                )
            ),
            AddBlock(
                Block(
                    id="2",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Answer"),
                )
            ),
        ]
        result = render_events(events, rows=8, cols=40)

        assert "> Question" in result
        assert "* Answer" in result


class TestViewportBehavior:
    """Test viewport and scrolling behavior."""

    def test_viewport_shows_recent_content(self):
        """Test that viewport shows most recent content."""
        # Create many blocks that won't all fit
        events = []
        for i in range(20):
            events.append(
                AddBlock(
                    Block(
                        id=str(i),
                        type=BlockType.ASSISTANT,
                        content=AssistantContent(text=f"Message {i}"),
                    )
                )
            )

        # Small viewport
        result = render_events(events, rows=5, cols=30)

        # Should see recent messages, not early ones
        assert "Message 19" in result
        assert "Message 0" not in result

    def test_long_line_truncation(self):
        """Test that long lines are truncated with ellipsis."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.USER,
                    content=UserContent(text="A" * 100),
                )
            )
        ]
        result = render_events(events, rows=5, cols=30)

        lines = result.split("\n")
        # All lines should be exactly cols wide
        assert all(len(line) == 30 for line in lines)
        # Should contain ellipsis for truncated content
        assert "…" in result


class TestBoxDrawingFrame:
    """Test box-drawing border frame."""

    def test_frame_corners(self):
        """Test frame has correct corners."""
        result = render_events([], rows=5, cols=20)
        lines = result.split("\n")

        assert lines[0][0] == "┌"
        assert lines[0][-1] == "┐"
        assert lines[-1][0] == "└"
        assert lines[-1][-1] == "┘"

    def test_frame_borders(self):
        """Test frame has correct borders."""
        result = render_events([], rows=5, cols=20)
        lines = result.split("\n")

        # Top and bottom borders
        assert all(c == "─" for c in lines[0][1:-1])
        assert all(c == "─" for c in lines[-1][1:-1])

        # Side borders
        for i in range(1, len(lines) - 1):
            assert lines[i][0] == "│"
            assert lines[i][-1] == "│"


class TestRequestIdGrouping:
    """Test request_id grouping behavior."""

    def test_same_request_id_no_blank_line(self):
        """Test blocks with same request_id have no blank line between."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Part 1"),
                    request_id="req_1",
                )
            ),
            AddBlock(
                Block(
                    id="2",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Bash",
                        tool_use_id="tu_1",
                        label="ls",
                    ),
                    request_id="req_1",
                )
            ),
        ]
        result = render_events(events, rows=10, cols=40)

        # Find the lines with content
        lines = result.split("\n")
        content_lines = []
        for line in lines:
            if "│" in line:
                inner = line[1:-1].strip()
                if inner:
                    content_lines.append(inner)

        # Should have "* Part 1" followed by "* Bash(ls)" without blank line
        part1_idx = next(
            i for i, l in enumerate(content_lines) if "Part 1" in l
        )
        bash_idx = next(
            i for i, l in enumerate(content_lines) if "Bash" in l
        )
        assert bash_idx == part1_idx + 1

    def test_different_request_id_blank_line(self):
        """Test blocks with different request_id have blank line between."""
        events = [
            AddBlock(
                Block(
                    id="1",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Part 1"),
                    request_id="req_1",
                )
            ),
            AddBlock(
                Block(
                    id="2",
                    type=BlockType.ASSISTANT,
                    content=AssistantContent(text="Part 2"),
                    request_id="req_2",
                )
            ),
        ]
        result = render_events(events, rows=10, cols=40)

        # Find the lines with content
        lines = result.split("\n")
        content_lines = []
        for line in lines:
            if "│" in line:
                inner = line[1:-1]
                content_lines.append(inner.strip() if inner.strip() else "")

        # Should have blank line between parts
        part1_idx = next(
            i for i, l in enumerate(content_lines) if "Part 1" in l
        )
        part2_idx = next(
            i for i, l in enumerate(content_lines) if "Part 2" in l
        )
        # There should be at least one blank line between them
        assert part2_idx > part1_idx + 1
        assert any(
            content_lines[i] == ""
            for i in range(part1_idx + 1, part2_idx)
        )


class TestCharacterLimits:
    """Test character count limits for messaging platforms."""

    def test_desktop_under_limit(self):
        """Test desktop render is under 3400 characters."""
        # Create a full session
        events = []
        for i in range(50):
            events.append(
                AddBlock(
                    Block(
                        id=str(i),
                        type=BlockType.ASSISTANT,
                        content=AssistantContent(text=f"Message {i}: " + "x" * 50),
                    )
                )
            )

        result = render_events(events, preset=Preset.DESKTOP)
        assert len(result) <= 3400

    def test_mobile_under_limit(self):
        """Test mobile render is under 1600 characters."""
        # Create a full session
        events = []
        for i in range(50):
            events.append(
                AddBlock(
                    Block(
                        id=str(i),
                        type=BlockType.ASSISTANT,
                        content=AssistantContent(text=f"Message {i}: " + "x" * 50),
                    )
                )
            )

        result = render_events(events, preset=Preset.MOBILE)
        assert len(result) <= 1600
