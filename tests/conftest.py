"""Shared test fixtures for Claude Session Player."""

import pytest

from claude_session_player.models import ScreenState


@pytest.fixture
def empty_state() -> ScreenState:
    """Return a fresh, empty ScreenState."""
    return ScreenState()
