"""Tool-specific input abbreviation logic."""

from __future__ import annotations


def _truncate(text: str, max_len: int = 60) -> str:
    """Truncate text to max_len chars, appending … if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _basename(path: str) -> str:
    """Extract basename from a file path."""
    return path.rsplit("/", 1)[-1] if "/" in path else path


# Tool name → (primary_field, fallback_field, transform)
# transform: "truncate", "basename", or "fixed:value"
_TOOL_RULES: dict[str, tuple[str, str | None, str]] = {
    "Bash": ("description", "command", "truncate"),
    "Read": ("file_path", None, "basename"),
    "Write": ("file_path", None, "basename"),
    "Edit": ("file_path", None, "basename"),
    "Glob": ("pattern", None, "truncate"),
    "Grep": ("pattern", None, "truncate"),
    "Task": ("description", None, "truncate"),
    "WebSearch": ("query", None, "truncate"),
    "WebFetch": ("url", None, "truncate"),
    "NotebookEdit": ("notebook_path", None, "basename"),
    "TodoWrite": (None, None, "fixed:todos"),
}


def abbreviate_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a short display label for a tool invocation.

    Args:
        tool_name: Name of the tool (e.g., "Bash", "Read").
        tool_input: The tool's input parameters dict.

    Returns:
        Abbreviated string for display (max 60 chars).
    """
    rule = _TOOL_RULES.get(tool_name)
    if rule is None:
        return "\u2026"

    primary_field, fallback_field, transform = rule

    # Fixed value tools (e.g., TodoWrite → "todos")
    if transform.startswith("fixed:"):
        return transform[6:]

    # Get the raw value from primary or fallback field
    raw = ""
    if primary_field is not None:
        raw = tool_input.get(primary_field, "")
    if not raw and fallback_field is not None:
        raw = tool_input.get(fallback_field, "")
    if not raw:
        return "\u2026"

    # Apply transform
    if transform == "basename":
        return _basename(raw)
    # "truncate"
    return _truncate(raw)
