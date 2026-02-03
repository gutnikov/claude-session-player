"""Event consumer: builds full conversation state from events."""

from __future__ import annotations

from .events import (
    AddBlock,
    AssistantContent,
    Block,
    ClearAll,
    DurationContent,
    Event,
    ProcessingContext,
    SystemContent,
    ThinkingContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from .formatter import format_duration


class ScreenStateConsumer:
    """Builds full conversation state from events.

    This consumer accumulates blocks from events, providing backwards
    compatibility with the existing CLI and replay-session.sh.
    """

    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self._block_index: dict[str, int] = {}  # block_id → index in blocks

    def handle(self, event: Event) -> None:
        """Process a single event.

        Args:
            event: An AddBlock, UpdateBlock, or ClearAll event.
        """
        if isinstance(event, AddBlock):
            self._block_index[event.block.id] = len(self.blocks)
            self.blocks.append(event.block)
        elif isinstance(event, UpdateBlock):
            index = self._block_index[event.block_id]
            # Create new Block with updated content (immutable update)
            old_block = self.blocks[index]
            self.blocks[index] = Block(
                id=old_block.id,
                type=old_block.type,
                content=event.content,
                request_id=old_block.request_id,
            )
        elif isinstance(event, ClearAll):
            self.blocks.clear()
            self._block_index.clear()

    def to_markdown(self) -> str:
        """Render all blocks as markdown.

        Blocks sharing the same non-None request_id are grouped together
        with no blank line between them. Different groups are separated
        by a blank line.

        Returns:
            Markdown string representation of all blocks.
        """
        parts: list[str] = []
        prev_request_id: str | None = None

        for block in self.blocks:
            formatted = format_block(block)
            if not formatted:
                continue

            current_rid = block.request_id

            # Insert blank line separator unless both previous and current
            # share the same non-None request_id
            if parts and not (
                prev_request_id and current_rid and prev_request_id == current_rid
            ):
                parts.append("")  # blank line

            parts.append(formatted)
            prev_request_id = current_rid

        return "\n".join(parts)


def format_block(block: Block) -> str:
    """Format a single block as markdown.

    Args:
        block: The block to format.

    Returns:
        Markdown string representation of the block.
    """
    content = block.content

    if isinstance(content, UserContent):
        return format_user_text(content.text)
    elif isinstance(content, AssistantContent):
        return format_assistant_text(content.text)
    elif isinstance(content, ToolCallContent):
        return format_tool_call(content)
    elif isinstance(content, ThinkingContent):
        return "\u2731 Thinking\u2026"
    elif isinstance(content, DurationContent):
        return f"\u2731 Crunched for {format_duration(content.duration_ms)}"
    elif isinstance(content, SystemContent):
        return content.text

    return ""


def format_user_text(text: str) -> str:
    """Format user input text with ❯ prompt prefix.

    First line gets ``❯ `` prefix, subsequent lines are indented 2 spaces.
    """
    lines = text.split("\n")
    if not lines or (len(lines) == 1 and lines[0] == ""):
        return "❯"
    result = [f"❯ {lines[0]}"]
    for line in lines[1:]:
        result.append(f"  {line}")
    return "\n".join(result)


def format_assistant_text(text: str) -> str:
    """Format assistant text with ● prefix.

    First line gets ``● `` prefix, continuation lines are indented 2 spaces.
    Markdown in text is passed through verbatim.
    """
    lines = text.split("\n")
    if not lines or (len(lines) == 1 and lines[0] == ""):
        return "●"
    result = [f"● {lines[0]}"]
    for line in lines[1:]:
        result.append(f"  {line}")
    return "\n".join(result)


def format_tool_call(content: ToolCallContent) -> str:
    """Format a tool call block as markdown.

    Args:
        content: The ToolCallContent to format.

    Returns:
        Formatted tool call string with optional result/progress.
    """
    line = f"\u25cf {content.tool_name}({content.label})"

    # Result takes priority over progress (result is the final state)
    if content.result is not None:
        prefix = "  \u2717 " if content.is_error else "  \u2514 "
        result_lines = content.result.split("\n")
        line += f"\n{prefix}{result_lines[0]}"
        # Subsequent lines indented with 4 spaces to align with text after └/✗
        for result_line in result_lines[1:]:
            line += f"\n    {result_line}"
    elif content.progress_text is not None:
        line += f"\n  \u2514 {content.progress_text}"

    return line


def replay_session(lines: list[dict]) -> str:
    """Convenience function for replaying a full session.

    Args:
        lines: List of parsed JSONL line dicts.

    Returns:
        Markdown string of the entire session.
    """
    from .processor import process_line

    context = ProcessingContext()
    consumer = ScreenStateConsumer()

    for line in lines:
        for event in process_line(context, line):
            consumer.handle(event)

    return consumer.to_markdown()
