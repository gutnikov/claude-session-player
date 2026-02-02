"""Tool-specific input abbreviation logic."""


def abbreviate_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create a short display label for a tool invocation.

    Args:
        tool_name: Name of the tool (e.g., "Bash", "Read").
        tool_input: The tool's input parameters dict.

    Returns:
        Abbreviated string for display (max 60 chars).
    """
    raise NotImplementedError("Implemented in issue 02")
