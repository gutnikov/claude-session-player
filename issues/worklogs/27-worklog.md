# Issue 27 Worklog: Event Processor

## Summary

Implemented `process_line()` function that converts JSONL lines into events for the event-driven renderer. This is Phase 2 of the event-driven renderer specification, building on the core event model from Issue #26.

## Files Created

| File | Description |
|------|-------------|
| `claude_session_player/processor.py` | Main processor with `process_line()` and 16 handler functions |
| `tests/test_processor.py` | 35 unit tests covering all line types |

## Implementation Details

### Main Function

```python
def process_line(context: ProcessingContext, line: dict) -> list[Event]
```

Dispatches to type-specific handlers based on `classify_line()` result.

### Event Generation Rules

| LineType | Event Type | Notes |
|----------|------------|-------|
| USER_INPUT | AddBlock(USER) | Resets context.current_request_id |
| LOCAL_COMMAND_OUTPUT | AddBlock(SYSTEM) | Extracts text from local-command-stdout tags |
| ASSISTANT_TEXT | AddBlock(ASSISTANT) | Updates context.current_request_id |
| TOOL_USE | AddBlock(TOOL_CALL) | Stores mapping in context, updates request_id |
| THINKING | AddBlock(THINKING) | Updates context.current_request_id |
| TURN_DURATION | AddBlock(DURATION) | Resets context.current_request_id |
| TOOL_RESULT (match) | UpdateBlock | Uses stored content to build complete update |
| TOOL_RESULT (orphan) | AddBlock(SYSTEM) | Truncated result as system output |
| COMPACT_BOUNDARY | ClearAll | Clears context and internal cache |
| *_PROGRESS (match) | UpdateBlock | Updates progress_text on tool call |
| WAITING_FOR_TASK (no match) | AddBlock(SYSTEM) | Standalone system output |
| INVISIBLE | [] | Returns empty list |

### Design Decision: Tool Content Cache

The spec defines `ProcessingContext.tool_use_id_to_block_id` as `dict[str, str]` (tool_use_id → block_id only). However, `UpdateBlock` requires complete `ToolCallContent` including tool_name and label.

**Solution**: Added a module-level `_tool_content_cache` that stores the original `ToolCallContent` when processing TOOL_USE. This allows creating complete `UpdateBlock` events for tool results and progress messages without modifying the `ProcessingContext` interface from Issue #26.

The cache is cleared on COMPACT_BOUNDARY along with the context.

### Reused Components

- `classify_line()` from parser.py
- `get_user_text()`, `get_tool_use_info()`, `get_tool_result_info()`, etc. from parser.py
- `abbreviate_tool_input()` from tools.py
- `truncate_result()` from formatter.py
- `_get_task_result_text()` pattern from renderer.py (for Task tool special handling)

## Test Summary

| Test Class | Test Count | Coverage |
|------------|------------|----------|
| `TestUserInput` | 3 | USER_INPUT handling, request_id reset, multiline |
| `TestLocalCommandOutput` | 1 | LOCAL_COMMAND_OUTPUT handling |
| `TestAssistantText` | 2 | ASSISTANT_TEXT handling, request_id update |
| `TestToolUse` | 3 | TOOL_CALL creation, context mapping, request_id |
| `TestThinking` | 2 | THINKING handling, request_id |
| `TestTurnDuration` | 2 | DURATION handling, request_id reset |
| `TestToolResult` | 3 | Match → UpdateBlock, error flag, orphan → AddBlock |
| `TestProgressMessages` | 7 | All 6 progress types with match, waiting_for_task without match |
| `TestCompactBoundary` | 2 | ClearAll event, context cleared |
| `TestInvisible` | 3 | Empty list for meta, sidechain user, sidechain assistant |
| `TestBlockIdGeneration` | 2 | Unique IDs, valid 32-char hex |
| `TestToolUseIdMapping` | 1 | Mapping works across multiple tools |
| `TestRequestIdGrouping` | 1 | Sequential blocks preserve request_id |
| `TestProgressWithoutMatch` | 3 | bash/hook/agent progress without match → empty list |
| **Total** | **35** | All line types covered |

## Test Results

```
411 passed in 10.40s
```

- 376 existing tests: all pass (no regressions)
- 35 new tests: all pass

## Decisions Made

1. **Module-level cache**: Used `_tool_content_cache` dict to store original `ToolCallContent` for building complete `UpdateBlock` events. This is cleared on COMPACT_BOUNDARY.

2. **Block ID generation**: Using `uuid.uuid4().hex` (32-char hex string) as specified.

3. **Progress without match**: Returns empty list for most progress types without matching tool call, except WAITING_FOR_TASK which creates standalone SystemOutput (matching existing renderer behavior).

4. **Task tool results**: Preserved special handling from renderer.py - uses `toolUseResult.content` if available, truncated to 80 chars.

## Deviations from Spec

1. **Tool content cache**: Added internal `_tool_content_cache` to enable complete `UpdateBlock` content. This was necessary because the `ProcessingContext` spec only stores block_id, not the full content needed for updates.

## Definition of Done Checklist

- [x] `process_line()` handles all 15 line types
- [x] Context state managed correctly
- [x] Block IDs generated uniquely (uuid4.hex)
- [x] Reuses parser.py, tools.py, formatter.py
- [x] ≥20 unit tests (35 tests), all passing
- [x] All prior tests still pass (411 total)
