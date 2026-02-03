"""Formatting helpers: convert screen state to markdown."""

from __future__ import annotations

from .models import AssistantText, ScreenState, SystemOutput, ToolCall, UserMessage


def truncate_result(text: str, max_lines: int = 5) -> str:
    """Truncate tool result to max_lines. Add … if truncated.

    Args:
        text: The tool result text to truncate.
        max_lines: Maximum number of lines to show. Defaults to 5.

    Returns:
        The truncated text with … on the last line if truncated,
        or "(no output)" if text is empty.
    """
    if not text:
        return "(no output)"
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[: max_lines - 1]) + "\n…"


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


def format_element(element: object) -> str:
    """Format a single screen element to its markdown representation."""
    if isinstance(element, UserMessage):
        return element.text
    if isinstance(element, SystemOutput):
        return element.text
    if isinstance(element, AssistantText):
        return element.text
    if isinstance(element, ToolCall):
        line = f"\u25cf {element.tool_name}({element.label})"
        if element.progress_text is not None:
            line += f"\n  \u2514 {element.progress_text}"
        if element.result is not None:
            prefix = "  \u2717 " if element.is_error else "  \u2514 "
            result_lines = element.result.split("\n")
            line += f"\n{prefix}{result_lines[0]}"
            # Subsequent lines indented with 4 spaces to align with text after └/✗
            for result_line in result_lines[1:]:
                line += f"\n    {result_line}"
        return line
    return ""


def to_markdown(state: ScreenState) -> str:
    """Render the current screen state as markdown text.

    Elements sharing the same non-None request_id are grouped together
    with no blank line between them. Different groups are separated by
    a blank line.
    """
    parts: list[str] = []
    prev_request_id: str | None = None

    for element in state.elements:
        formatted = format_element(element)
        if not formatted:
            continue

        current_rid = getattr(element, "request_id", None)

        # Insert blank line separator unless both previous and current
        # share the same non-None request_id
        if parts and not (prev_request_id and current_rid and prev_request_id == current_rid):
            parts.append("")  # blank line

        parts.append(formatted)
        prev_request_id = current_rid

    return "\n".join(parts)
