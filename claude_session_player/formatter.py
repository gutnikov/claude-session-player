"""Formatting helpers: convert screen state to markdown."""

from .models import ScreenState


def to_markdown(state: ScreenState) -> str:
    """Render the current screen state as markdown text.

    Args:
        state: The screen state to format.

    Returns:
        Markdown string representation of the screen.
    """
    raise NotImplementedError("Implemented in issue 03-04")
