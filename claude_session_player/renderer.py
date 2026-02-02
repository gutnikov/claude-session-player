"""Render function: processes JSONL lines into screen state."""

from .models import ScreenState


def render(state: ScreenState, line: dict) -> ScreenState:
    """Process a single JSONL line and update screen state.

    Args:
        state: Current screen state (mutated in place).
        line: Parsed JSONL line dict.

    Returns:
        The same state object, updated.
    """
    raise NotImplementedError("Implemented in issue 02")
