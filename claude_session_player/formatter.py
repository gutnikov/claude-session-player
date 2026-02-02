"""Formatting helpers: convert screen state to markdown."""

from __future__ import annotations

from .models import AssistantText, ScreenState, SystemOutput, UserMessage


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
