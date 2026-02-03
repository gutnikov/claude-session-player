# Issue #39: Refactor ScreenStateConsumer to Async Protocol

## Summary

Refactored `ScreenStateConsumer` to implement the `Consumer` protocol from issue #38, adding async `on_event()` and `render_block()` methods while maintaining full backward compatibility.

## Changes Made

### `/Users/agutnikov/work/claude-session-player/claude_session_player/consumer.py`

1. **Added `async def on_event(event: Event) -> None`**
   - Implements the `Consumer` protocol for use with `EventEmitter`
   - Internally delegates to the synchronous `handle()` method
   - No awaits needed since ScreenStateConsumer is internally synchronous

2. **Added `def render_block(block: Block) -> str`**
   - Implements the `Consumer` protocol's render method
   - Delegates to the existing `format_block()` module-level function
   - Allows consistent interface for all consumers

3. **Updated class docstring**
   - Documents that the class implements the Consumer protocol

4. **Updated `handle()` docstring**
   - Clarifies this is the synchronous method for backward compatibility

### `/Users/agutnikov/work/claude-session-player/tests/test_consumer.py`

Added 14 new tests in three test classes:

1. **TestAsyncOnEvent** (4 tests)
   - `test_on_event_handles_add_block` - AddBlock events work
   - `test_on_event_handles_update_block` - UpdateBlock events work
   - `test_on_event_handles_clear_all` - ClearAll events work
   - `test_on_event_produces_same_result_as_handle` - Identical output

2. **TestRenderBlock** (7 tests)
   - `test_render_block_returns_same_as_format_block` - Consistency check
   - `test_render_block_for_user_content` - UserContent rendering
   - `test_render_block_for_assistant_content` - AssistantContent rendering
   - `test_render_block_for_tool_call_with_result` - ToolCallContent rendering
   - `test_render_block_for_thinking_content` - ThinkingContent rendering
   - `test_render_block_for_duration_content` - DurationContent rendering
   - `test_render_block_for_system_content` - SystemContent rendering

3. **TestConsumerProtocolCompliance** (3 tests)
   - `test_consumer_implements_protocol` - isinstance check with Consumer
   - `test_consumer_can_be_used_with_emitter` - EventEmitter subscription
   - `test_consumer_works_with_emitter_emit` - Full integration test

## Design Decisions

1. **Delegation pattern**: `on_event()` delegates to `handle()` rather than duplicating logic. This ensures the synchronous and async paths always behave identically.

2. **render_block() delegates to format_block()**: Rather than extracting the logic into the method, we delegate to the existing module-level function. This:
   - Maintains backward compatibility for code using `format_block()` directly
   - Avoids code duplication
   - Keeps the implementation simple

3. **Internally synchronous**: Since `ScreenStateConsumer` only modifies in-memory data structures, no actual async operations are needed. The async signature is for protocol compliance.

## Testing

All 343 tests pass:
- 30 existing consumer tests (unchanged behavior)
- 14 new async interface tests
- 299 other tests (unchanged)

## Acceptance Criteria Verification

- [x] `ScreenStateConsumer` implements the `Consumer` protocol from #38
- [x] `on_event()` handles `AddBlock`, `UpdateBlock`, `ClearAll` as before
- [x] `render_block()` renders individual blocks to markdown
- [x] `to_markdown()` still works and produces identical output
- [x] All existing tests pass
- [x] New tests for async interface
