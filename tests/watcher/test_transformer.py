"""Tests for the stateless session transformer."""

from __future__ import annotations

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    BlockType,
    ClearAll,
    DurationContent,
    ProcessingContext,
    SystemContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.processor import (
    _clear_tool_content_cache,
    _question_content_cache,
    _tool_content_cache,
    process_line,
)
from claude_session_player.watcher.transformer import transform


# ---------------------------------------------------------------------------
# Basic functionality tests
# ---------------------------------------------------------------------------


class TestTransformBasic:
    """Tests for basic transform() functionality."""

    def test_empty_lines_returns_empty_events(self) -> None:
        """Empty lines list returns empty events list."""
        context = ProcessingContext()
        events, new_ctx = transform([], context)

        assert events == []
        assert new_ctx.tool_use_id_to_block_id == {}
        assert new_ctx.current_request_id is None

    def test_empty_lines_preserves_context(self) -> None:
        """Empty lines list returns equivalent context (not mutated original)."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"tu_123": "block_456"},
            current_request_id="req_789",
        )
        original_mapping = context.tool_use_id_to_block_id.copy()

        events, new_ctx = transform([], context)

        # Original context unchanged
        assert context.tool_use_id_to_block_id == original_mapping
        assert context.current_request_id == "req_789"
        # New context has same values
        assert new_ctx.tool_use_id_to_block_id == original_mapping
        assert new_ctx.current_request_id == "req_789"


class TestTransformImmutability:
    """Tests verifying original context is not mutated."""

    def test_original_context_unchanged_after_user_input(
        self, user_input_line: dict
    ) -> None:
        """Original context is not mutated when processing user input."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"existing": "mapping"},
            current_request_id="old_request",
        )
        original_tool_map = context.tool_use_id_to_block_id.copy()
        original_request_id = context.current_request_id

        events, new_ctx = transform([user_input_line], context)

        # Original context unchanged
        assert context.tool_use_id_to_block_id == original_tool_map
        assert context.current_request_id == original_request_id
        # New context was modified (user input resets request_id)
        assert new_ctx.current_request_id is None

    def test_original_context_unchanged_after_tool_use(
        self, tool_use_line: dict
    ) -> None:
        """Original context is not mutated when processing tool_use."""
        context = ProcessingContext()

        events, new_ctx = transform([tool_use_line], context)

        # Original context unchanged
        assert context.tool_use_id_to_block_id == {}
        # New context has the tool mapping
        assert "toolu_001" in new_ctx.tool_use_id_to_block_id

    def test_original_context_unchanged_after_compact_boundary(
        self, tool_use_line: dict, compact_boundary_line: dict
    ) -> None:
        """Original context is not mutated when processing compact_boundary."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"existing": "mapping"},
            current_request_id="old_request",
        )
        original_tool_map = context.tool_use_id_to_block_id.copy()
        original_request_id = context.current_request_id

        events, new_ctx = transform([compact_boundary_line], context)

        # Original context unchanged
        assert context.tool_use_id_to_block_id == original_tool_map
        assert context.current_request_id == original_request_id
        # New context was cleared
        assert new_ctx.tool_use_id_to_block_id == {}
        assert new_ctx.current_request_id is None

    def test_nested_dict_not_shared(self, tool_use_line: dict) -> None:
        """Deep copy ensures nested dicts are not shared."""
        context = ProcessingContext(
            tool_use_id_to_block_id={"existing": "mapping"},
        )

        events, new_ctx = transform([tool_use_line], context)

        # Modifying new context doesn't affect original
        new_ctx.tool_use_id_to_block_id["new_key"] = "new_value"
        assert "new_key" not in context.tool_use_id_to_block_id


# ---------------------------------------------------------------------------
# Event generation tests
# ---------------------------------------------------------------------------


class TestTransformEventGeneration:
    """Tests for event generation from various line types."""

    def test_user_input_generates_add_block(self, user_input_line: dict) -> None:
        """User input generates AddBlock(USER) event."""
        context = ProcessingContext()
        events, _ = transform([user_input_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.USER
        assert isinstance(events[0].block.content, UserContent)
        assert events[0].block.content.text == "hello world"

    def test_assistant_text_generates_add_block(self, assistant_text_line: dict) -> None:
        """Assistant text generates AddBlock(ASSISTANT) event."""
        context = ProcessingContext()
        events, _ = transform([assistant_text_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.ASSISTANT
        assert isinstance(events[0].block.content, AssistantContent)
        assert events[0].block.content.text == "Here is my response."

    def test_tool_use_generates_add_block(self, tool_use_line: dict) -> None:
        """Tool use generates AddBlock(TOOL_CALL) event."""
        context = ProcessingContext()
        events, _ = transform([tool_use_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.TOOL_CALL
        assert isinstance(events[0].block.content, ToolCallContent)
        assert events[0].block.content.tool_name == "Bash"
        assert events[0].block.content.tool_use_id == "toolu_001"

    def test_turn_duration_generates_add_block(self, turn_duration_line: dict) -> None:
        """Turn duration generates AddBlock(DURATION) event."""
        context = ProcessingContext()
        events, _ = transform([turn_duration_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.DURATION
        assert isinstance(events[0].block.content, DurationContent)
        assert events[0].block.content.duration_ms == 12500

    def test_compact_boundary_generates_clear_all(
        self, compact_boundary_line: dict
    ) -> None:
        """Compact boundary generates ClearAll event."""
        context = ProcessingContext()
        events, _ = transform([compact_boundary_line], context)

        assert len(events) == 1
        assert isinstance(events[0], ClearAll)

    def test_thinking_generates_add_block(self, thinking_line: dict) -> None:
        """Thinking generates AddBlock(THINKING) event."""
        context = ProcessingContext()
        events, _ = transform([thinking_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.THINKING

    def test_local_command_output_generates_add_block(
        self, local_command_output_line: dict
    ) -> None:
        """Local command output generates AddBlock(SYSTEM) event."""
        context = ProcessingContext()
        events, _ = transform([local_command_output_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.SYSTEM
        assert isinstance(events[0].block.content, SystemContent)


# ---------------------------------------------------------------------------
# Tool use + result linking tests
# ---------------------------------------------------------------------------


class TestTransformToolLinking:
    """Tests for tool_use → tool_result linking."""

    def test_tool_result_updates_matching_tool_call(
        self, tool_use_line: dict, tool_result_line: dict
    ) -> None:
        """Tool result generates UpdateBlock for matching tool_use."""
        context = ProcessingContext()
        events, _ = transform([tool_use_line, tool_result_line], context)

        assert len(events) == 2
        # First event: AddBlock for tool_use
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.TOOL_CALL
        block_id = events[0].block.id

        # Second event: UpdateBlock for tool_result
        assert isinstance(events[1], UpdateBlock)
        assert events[1].block_id == block_id
        assert isinstance(events[1].content, ToolCallContent)
        assert events[1].content.result is not None

    def test_orphan_tool_result_generates_system_block(
        self, tool_result_line: dict
    ) -> None:
        """Tool result without matching tool_use generates AddBlock(SYSTEM)."""
        context = ProcessingContext()
        events, _ = transform([tool_result_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.SYSTEM

    def test_tool_mapping_stored_in_context(self, tool_use_line: dict) -> None:
        """Tool use stores mapping in returned context."""
        context = ProcessingContext()
        events, new_ctx = transform([tool_use_line], context)

        assert "toolu_001" in new_ctx.tool_use_id_to_block_id
        block_id = new_ctx.tool_use_id_to_block_id["toolu_001"]
        assert events[0].block.id == block_id


# ---------------------------------------------------------------------------
# Multiple lines accumulation tests
# ---------------------------------------------------------------------------


class TestTransformMultipleLines:
    """Tests for processing multiple lines."""

    def test_multiple_lines_accumulate_events(
        self, user_input_line: dict, assistant_text_line: dict, tool_use_line: dict
    ) -> None:
        """Multiple lines produce accumulated events."""
        context = ProcessingContext()
        events, _ = transform(
            [user_input_line, assistant_text_line, tool_use_line], context
        )

        assert len(events) == 3
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.USER
        assert isinstance(events[1], AddBlock)
        assert events[1].block.type == BlockType.ASSISTANT
        assert isinstance(events[2], AddBlock)
        assert events[2].block.type == BlockType.TOOL_CALL

    def test_invisible_lines_produce_no_events(
        self, sidechain_user_line: dict, sidechain_assistant_line: dict
    ) -> None:
        """Sidechain (invisible) lines produce no events."""
        context = ProcessingContext()
        events, _ = transform(
            [sidechain_user_line, sidechain_assistant_line], context
        )

        assert events == []

    def test_context_evolves_across_lines(
        self, tool_use_line: dict, tool_use_read_line: dict
    ) -> None:
        """Context accumulates state across multiple lines."""
        context = ProcessingContext()
        events, new_ctx = transform([tool_use_line, tool_use_read_line], context)

        # Both tool uses should be mapped
        assert "toolu_001" in new_ctx.tool_use_id_to_block_id
        assert "toolu_003" in new_ctx.tool_use_id_to_block_id


# ---------------------------------------------------------------------------
# Context compaction tests
# ---------------------------------------------------------------------------


class TestTransformContextCompaction:
    """Tests for context compaction (ClearAll)."""

    def test_compact_boundary_clears_returned_context(
        self, tool_use_line: dict, compact_boundary_line: dict
    ) -> None:
        """Compact boundary clears tool mappings in returned context."""
        context = ProcessingContext()
        # Process tool_use first, then compact
        events, new_ctx = transform([tool_use_line, compact_boundary_line], context)

        assert len(events) == 2
        assert isinstance(events[0], AddBlock)
        assert isinstance(events[1], ClearAll)
        # Returned context is cleared
        assert new_ctx.tool_use_id_to_block_id == {}
        assert new_ctx.current_request_id is None

    def test_tool_result_after_compaction_is_orphan(
        self, tool_use_line: dict, compact_boundary_line: dict, tool_result_line: dict
    ) -> None:
        """Tool result after compaction becomes orphan (no matching tool_use)."""
        context = ProcessingContext()
        events, _ = transform(
            [tool_use_line, compact_boundary_line, tool_result_line], context
        )

        assert len(events) == 3
        assert isinstance(events[0], AddBlock)  # tool_use
        assert isinstance(events[1], ClearAll)  # compact
        assert isinstance(events[2], AddBlock)  # orphan result as SYSTEM
        assert events[2].block.type == BlockType.SYSTEM


# ---------------------------------------------------------------------------
# Progress message tests
# ---------------------------------------------------------------------------


class TestTransformProgressMessages:
    """Tests for progress messages (bash, hook, agent, etc.)."""

    def test_bash_progress_updates_tool_call(
        self, tool_use_line: dict, bash_progress_line: dict
    ) -> None:
        """Bash progress generates UpdateBlock for matching tool_use."""
        context = ProcessingContext()
        events, _ = transform([tool_use_line, bash_progress_line], context)

        assert len(events) == 2
        assert isinstance(events[0], AddBlock)
        assert isinstance(events[1], UpdateBlock)
        assert events[1].content.progress_text is not None

    def test_progress_without_parent_ignored(
        self, waiting_for_task_no_parent_line: dict
    ) -> None:
        """Progress without parent generates standalone block."""
        context = ProcessingContext()
        events, _ = transform([waiting_for_task_no_parent_line], context)

        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.SYSTEM


# ---------------------------------------------------------------------------
# Parity with process_line tests
# ---------------------------------------------------------------------------


class TestTransformParityWithProcessLine:
    """Tests ensuring transform() output matches process_line()."""

    def test_single_line_parity(self, user_input_line: dict) -> None:
        """transform() produces same events as direct process_line() call."""
        context1 = ProcessingContext()
        context2 = ProcessingContext()

        # Using transform
        transform_events, _ = transform([user_input_line], context1)

        # Using process_line directly
        direct_events = process_line(context2, user_input_line)

        # Clean up module caches after direct process_line call
        _clear_tool_content_cache()

        assert len(transform_events) == len(direct_events)
        # Compare event types and content (not block IDs which are random)
        for t_event, d_event in zip(transform_events, direct_events):
            assert type(t_event) == type(d_event)
            if isinstance(t_event, AddBlock):
                assert t_event.block.type == d_event.block.type
                assert type(t_event.block.content) == type(d_event.block.content)

    def test_multi_line_parity(
        self,
        user_input_line: dict,
        assistant_text_line: dict,
        tool_use_line: dict,
        tool_result_line: dict,
    ) -> None:
        """transform() produces same events as sequential process_line() calls."""
        lines = [user_input_line, assistant_text_line, tool_use_line, tool_result_line]

        # Using transform
        context1 = ProcessingContext()
        transform_events, _ = transform(lines, context1)

        # Using process_line directly
        context2 = ProcessingContext()
        direct_events = []
        for line in lines:
            direct_events.extend(process_line(context2, line))

        # Clean up module caches after direct process_line calls
        _clear_tool_content_cache()

        assert len(transform_events) == len(direct_events)
        for t_event, d_event in zip(transform_events, direct_events):
            assert type(t_event) == type(d_event)


# ---------------------------------------------------------------------------
# Module cache isolation tests
# ---------------------------------------------------------------------------


class TestTransformCacheIsolation:
    """Tests ensuring module-level caches are properly isolated."""

    def test_transform_does_not_pollute_module_caches(
        self, tool_use_line: dict
    ) -> None:
        """transform() restores module caches after execution."""
        # Set up some state in module caches
        _tool_content_cache["pre_existing"] = ToolCallContent(
            tool_name="PreExisting",
            tool_use_id="pre_existing",
            label="test",
        )

        context = ProcessingContext()
        events, _ = transform([tool_use_line], context)

        # Pre-existing cache entry should still be there
        assert "pre_existing" in _tool_content_cache
        # New entry from transform should NOT be there
        assert "toolu_001" not in _tool_content_cache

    def test_transform_does_not_use_stale_cache(
        self, tool_result_line: dict
    ) -> None:
        """transform() doesn't use pre-existing cache entries."""
        # Set up a cache entry that would match the tool_result
        _tool_content_cache["toolu_001"] = ToolCallContent(
            tool_name="Stale",
            tool_use_id="toolu_001",
            label="stale entry",
        )

        context = ProcessingContext()
        # Process just the tool_result (no tool_use first)
        events, _ = transform([tool_result_line], context)

        # Should be orphan result (SYSTEM block) not an update
        assert len(events) == 1
        assert isinstance(events[0], AddBlock)
        assert events[0].block.type == BlockType.SYSTEM

        # Clean up
        _tool_content_cache.clear()

    def test_concurrent_transforms_isolated(
        self, tool_use_line: dict, tool_use_read_line: dict
    ) -> None:
        """Multiple transform calls don't interfere with each other."""
        context1 = ProcessingContext()
        context2 = ProcessingContext()

        # First transform
        events1, new_ctx1 = transform([tool_use_line], context1)

        # Second transform with different line
        events2, new_ctx2 = transform([tool_use_read_line], context2)

        # Each should only have its own mapping
        assert "toolu_001" in new_ctx1.tool_use_id_to_block_id
        assert "toolu_003" not in new_ctx1.tool_use_id_to_block_id

        assert "toolu_003" in new_ctx2.tool_use_id_to_block_id
        assert "toolu_001" not in new_ctx2.tool_use_id_to_block_id
