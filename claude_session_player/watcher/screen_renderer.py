"""Screen renderer: renders events to terminal-style text output.

This module provides the ScreenRenderer class that takes events and produces
a terminal-style preformatted text output, constrained to configurable dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..events import (
    AddBlock,
    AssistantContent,
    Block,
    ClearAll,
    DurationContent,
    Event,
    QuestionContent,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from ..formatter import format_duration


class Preset(Enum):
    """Predefined screen dimensions."""

    DESKTOP = "desktop"
    MOBILE = "mobile"


@dataclass
class Dimensions:
    """Screen dimensions for rendering."""

    rows: int
    cols: int


# Preset dimensions
PRESET_DIMENSIONS: dict[Preset, Dimensions] = {
    Preset.DESKTOP: Dimensions(rows=40, cols=80),
    Preset.MOBILE: Dimensions(rows=25, cols=60),
}


class ScreenRenderer:
    """Renders session events to terminal-style text output.

    The renderer takes a list of events and produces a string that looks like
    terminal output, constrained to configurable dimensions with box-drawing
    borders.
    """

    # Box drawing characters
    TOP_LEFT = "┌"
    TOP_RIGHT = "┐"
    BOTTOM_LEFT = "└"
    BOTTOM_RIGHT = "┘"
    HORIZONTAL = "─"
    VERTICAL = "│"

    def render(
        self,
        events: list[Event],
        preset: Preset | None = None,
        rows: int | None = None,
        cols: int | None = None,
    ) -> str:
        """Render events to terminal-style text output.

        Args:
            events: List of events to render.
            preset: Predefined dimensions (DESKTOP or MOBILE).
            rows: Number of rows (overrides preset).
            cols: Number of columns (overrides preset).

        Returns:
            Terminal-style text output with box-drawing borders.

        Raises:
            ValueError: If neither preset nor rows/cols are provided.
        """
        # Determine dimensions
        if rows is not None and cols is not None:
            dims = Dimensions(rows=rows, cols=cols)
        elif preset is not None:
            dims = PRESET_DIMENSIONS[preset]
        else:
            raise ValueError("Must provide either preset or rows/cols")

        # Build blocks from events
        blocks = self._build_blocks(events)

        # Render blocks to lines
        content_lines = self._render_blocks_to_lines(blocks)

        # Apply viewport (show last N lines that fit)
        # Account for top and bottom borders
        available_rows = dims.rows - 2
        viewport_lines = content_lines[-available_rows:] if content_lines else []

        # Wrap/truncate lines to fit column width
        # Account for left and right borders
        inner_width = dims.cols - 2
        wrapped_lines = self._wrap_lines(viewport_lines, inner_width)

        # Re-apply viewport after wrapping (wrapping may create more lines)
        viewport_lines = wrapped_lines[-available_rows:] if wrapped_lines else []

        # Pad to fill available rows
        while len(viewport_lines) < available_rows:
            viewport_lines.append("")

        # Build framed output
        return self._build_frame(viewport_lines, dims)

    def _build_blocks(self, events: list[Event]) -> list[Block]:
        """Build block list from events.

        Args:
            events: List of events to process.

        Returns:
            List of blocks.
        """
        blocks: list[Block] = []
        block_index: dict[str, int] = {}

        for event in events:
            if isinstance(event, AddBlock):
                block_index[event.block.id] = len(blocks)
                blocks.append(event.block)
            elif isinstance(event, UpdateBlock):
                if event.block_id in block_index:
                    idx = block_index[event.block_id]
                    old_block = blocks[idx]
                    blocks[idx] = Block(
                        id=old_block.id,
                        type=old_block.type,
                        content=event.content,
                        request_id=old_block.request_id,
                    )
            elif isinstance(event, ClearAll):
                blocks.clear()
                block_index.clear()

        return blocks

    def _render_blocks_to_lines(self, blocks: list[Block]) -> list[str]:
        """Render blocks to a list of lines.

        Args:
            blocks: List of blocks to render.

        Returns:
            List of lines (without newlines).
        """
        lines: list[str] = []
        prev_request_id: str | None = None

        for block in blocks:
            formatted = self._format_block(block)
            if not formatted:
                continue

            current_rid = block.request_id

            # Insert blank line separator unless both previous and current
            # share the same non-None request_id
            if lines and not (
                prev_request_id and current_rid and prev_request_id == current_rid
            ):
                lines.append("")

            # Split formatted text into lines
            lines.extend(formatted.split("\n"))
            prev_request_id = current_rid

        return lines

    def _format_block(self, block: Block) -> str:
        """Format a single block as plain text.

        Args:
            block: The block to format.

        Returns:
            Plain text representation of the block.
        """
        content = block.content

        if isinstance(content, UserContent):
            return self._format_user_text(content.text)
        elif isinstance(content, AssistantContent):
            return self._format_assistant_text(content.text)
        elif isinstance(content, ToolCallContent):
            return self._format_tool_call(content)
        elif isinstance(content, QuestionContent):
            return self._format_question(content)
        elif isinstance(content, ThinkingContent):
            return "* Thinking..."
        elif isinstance(content, DurationContent):
            return f"* Crunched for {format_duration(content.duration_ms)}"
        elif isinstance(content, SystemContent):
            return content.text

        return ""

    def _format_user_text(self, text: str) -> str:
        """Format user input text with > prompt prefix."""
        lines = text.split("\n")
        if not lines or (len(lines) == 1 and lines[0] == ""):
            return ">"
        result = [f"> {lines[0]}"]
        for line in lines[1:]:
            result.append(f"  {line}")
        return "\n".join(result)

    def _format_assistant_text(self, text: str) -> str:
        """Format assistant text with * prefix."""
        lines = text.split("\n")
        if not lines or (len(lines) == 1 and lines[0] == ""):
            return "*"
        result = [f"* {lines[0]}"]
        for line in lines[1:]:
            result.append(f"  {line}")
        return "\n".join(result)

    def _format_tool_call(self, content: ToolCallContent) -> str:
        """Format a tool call block as plain text."""
        line = f"* {content.tool_name}({content.label})"

        # Result takes priority over progress
        if content.result is not None:
            prefix = "  X " if content.is_error else "  > "
            result_lines = content.result.split("\n")
            line += f"\n{prefix}{result_lines[0]}"
            for result_line in result_lines[1:]:
                line += f"\n    {result_line}"
        elif content.progress_text is not None:
            line += f"\n  > {content.progress_text}"

        return line

    def _format_question(self, content: QuestionContent) -> str:
        """Format a question block as plain text."""
        parts: list[str] = []

        for question in content.questions:
            header = question.header or "Question"
            lines = [f"* Question: {header}"]
            lines.append(f"  | {question.question}")

            answer = None
            if content.answers:
                answer = content.answers.get(question.question)

            if answer:
                lines.append(f"  > [x] {answer}")
            else:
                for opt in question.options:
                    lines.append(f"  | [ ] {opt.label}")
                lines.append("  > (awaiting response)")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    def _wrap_lines(self, lines: list[str], width: int) -> list[str]:
        """Wrap or truncate lines to fit within width.

        Args:
            lines: List of lines to wrap.
            width: Maximum line width.

        Returns:
            List of lines, each no longer than width.
        """
        result: list[str] = []

        for line in lines:
            if len(line) <= width:
                result.append(line)
            else:
                # Truncate with ellipsis
                result.append(line[: width - 1] + "…")

        return result

    def _build_frame(self, lines: list[str], dims: Dimensions) -> str:
        """Build the framed output with box-drawing borders.

        Args:
            lines: Content lines (already sized to fit).
            dims: Target dimensions.

        Returns:
            Framed output string.
        """
        inner_width = dims.cols - 2
        result: list[str] = []

        # Top border
        result.append(self.TOP_LEFT + self.HORIZONTAL * inner_width + self.TOP_RIGHT)

        # Content lines with side borders
        for line in lines:
            padded = line.ljust(inner_width)
            result.append(self.VERTICAL + padded + self.VERTICAL)

        # Bottom border
        result.append(
            self.BOTTOM_LEFT + self.HORIZONTAL * inner_width + self.BOTTOM_RIGHT
        )

        return "\n".join(result)


def render_events(
    events: list[Event],
    preset: Preset | None = None,
    rows: int | None = None,
    cols: int | None = None,
) -> str:
    """Convenience function to render events.

    Args:
        events: List of events to render.
        preset: Predefined dimensions (DESKTOP or MOBILE).
        rows: Number of rows (overrides preset).
        cols: Number of columns (overrides preset).

    Returns:
        Terminal-style text output with box-drawing borders.
    """
    renderer = ScreenRenderer()
    return renderer.render(events, preset=preset, rows=rows, cols=cols)
