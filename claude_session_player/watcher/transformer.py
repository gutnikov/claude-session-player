"""Stateless session transformer for the watcher service.

This module provides a pure function that transforms JSONL lines into events
with explicit state threading. The original context is never mutated.
"""

from __future__ import annotations

import copy

from claude_session_player.events import (
    Event,
    ProcessingContext,
)
from claude_session_player.processor import (
    _question_content_cache,
    _tool_content_cache,
    process_line,
)


def transform(
    lines: list[dict],
    context: ProcessingContext,
) -> tuple[list[Event], ProcessingContext]:
    """Process lines and return events with updated context.

    Pure function: no side effects, no I/O.
    The original context is not mutated; a new context is returned.

    Args:
        lines: List of parsed JSONL line dicts to process.
        context: Processing context with tool mappings and current request ID.

    Returns:
        Tuple of (events, new_context) where events is the list of all events
        produced and new_context is the updated processing context.
    """
    # Deep copy context so we don't mutate the original
    ctx = copy.deepcopy(context)

    # Save and restore module-level caches to ensure isolation
    # This is necessary because processor.py uses module-level caches
    saved_tool_cache = _tool_content_cache.copy()
    saved_question_cache = _question_content_cache.copy()

    try:
        # Clear module caches and restore them from context state if needed
        # Note: The caches need to be in sync with the context's tool mappings
        _tool_content_cache.clear()
        _question_content_cache.clear()

        events: list[Event] = []
        for line in lines:
            line_events = process_line(ctx, line)
            events.extend(line_events)

            # Check if ClearAll was emitted (context compaction)
            # process_line already calls ctx.clear() and _clear_tool_content_cache()
            # but we track this for clarity

        return events, ctx

    finally:
        # Restore the original module-level caches
        _tool_content_cache.clear()
        _tool_content_cache.update(saved_tool_cache)
        _question_content_cache.clear()
        _question_content_cache.update(saved_question_cache)
