"""Tool-specific input abbreviation for display."""

from __future__ import annotations

import os

MAX_LABEL_LENGTH = 60


def _truncate(text: str, max_len: int = MAX_LABEL_LENGTH) -> str:
    """Truncate text to max_len characters, appending ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def abbreviate_tool_input(tool_name: str, tool_input: dict) -> str:
    """Return abbreviated display label for a tool call.

    Each tool has a preferred field to show. If the field is missing or empty,
    falls back to showing ellipsis.
    """
    if tool_name == "Bash":
        desc = tool_input.get("description", "")
        if desc:
            return _truncate(desc)
        cmd = tool_input.get("command", "")
        if cmd:
            return _truncate(cmd)
        return "\u2026"

    if tool_name in ("Read", "Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            return os.path.basename(file_path)
        return "\u2026"

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return _truncate(pattern)
        return "\u2026"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        if pattern:
            return _truncate(pattern)
        return "\u2026"

    if tool_name == "Task":
        desc = tool_input.get("description", "")
        if desc:
            return _truncate(desc)
        return "\u2026"

    if tool_name == "WebSearch":
        query = tool_input.get("query", "")
        if query:
            return _truncate(query)
        return "\u2026"

    if tool_name == "WebFetch":
        url = tool_input.get("url", "")
        if url:
            return _truncate(url)
        return "\u2026"

    # Unknown tool
    return "\u2026"
