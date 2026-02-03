"""Formatting helpers: duration and result truncation utilities."""

from __future__ import annotations


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration.

    Args:
        ms: Duration in milliseconds.

    Returns:
        Formatted string like "5s" or "1m 28s".
    """
    total_seconds = ms // 1000
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}m {seconds}s"


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
