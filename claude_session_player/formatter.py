"""Formatting helpers: convert screen state to markdown."""

from __future__ import annotations

from .models import ScreenState, SystemOutput, UserMessage


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


def format_element(element: object) -> str:
    """Format a single screen element to its markdown representation."""
    if isinstance(element, UserMessage):
        return element.text
    if isinstance(element, SystemOutput):
        return element.text
    return ""


def to_markdown(state: ScreenState) -> str:
    """Render the current screen state as markdown text."""
    parts = []
    for element in state.elements:
        formatted = format_element(element)
        if formatted:
            parts.append(formatted)
    return "\n\n".join(parts)
