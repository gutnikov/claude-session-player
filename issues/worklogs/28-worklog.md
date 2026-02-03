# Issue 28 Worklog: ScreenStateConsumer

## Summary

Implemented `ScreenStateConsumer` class that builds full conversation state from events, providing backwards compatibility with the existing CLI and `replay-session.sh`. This is Phase 3 of the event-driven renderer specification.

## Files Created

| File | Description |
|------|-------------|
| `claude_session_player/consumer.py` | ScreenStateConsumer class, format_block(), replay_session() |
| `tests/test_consumer.py` | 30 unit tests covering all functionality |

## Implementation Details

### ScreenStateConsumer Class

```python
class ScreenStateConsumer:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self._block_index: dict[str, int] = {}  # block_id → index

    def handle(self, event: Event) -> None:
        """Process AddBlock, UpdateBlock, or ClearAll events."""

    def to_markdown(self) -> str:
        """Render all blocks with request_id grouping."""
```

### Event Handling

- `AddBlock`: Appends block to list, stores index in `_block_index`
- `UpdateBlock`: Creates new Block with updated content (immutable update pattern)
- `ClearAll`: Clears both `blocks` and `_block_index`

### Formatting Functions

| Function | Description |
|----------|-------------|
| `format_block(block)` | Dispatches to type-specific formatters |
| `format_user_text(text)` | `❯` prefix with 2-space continuation indent |
| `format_assistant_text(text)` | `●` prefix with 2-space continuation indent |
| `format_tool_call(content)` | Tool name/label with optional result/progress |

### Convenience Function

```python
def replay_session(lines: list[dict]) -> str:
    """Process JSONL lines and return markdown output."""
```

This provides a simple entry point that matches the old API pattern.

## Test Summary

| Test Class | Test Count | Coverage |
|------------|------------|----------|
| `TestAddBlock` | 3 | Appends, updates index, multiple blocks |
| `TestUpdateBlock` | 3 | Modifies content, preserves metadata |
| `TestClearAll` | 2 | Empties state, allows new blocks after |
| `TestToMarkdownUserContent` | 2 | Single-line, multiline |
| `TestToMarkdownAssistantContent` | 2 | Single-line, multiline |
| `TestToMarkdownToolCallContent` | 4 | No result, with result, with error, with progress |
| `TestToMarkdownOtherContent` | 4 | Thinking, duration (2 formats), system |
| `TestRequestIdGrouping` | 3 | Same ID (no gap), different IDs (gap), None IDs |
| `TestReplaySession` | 3 | End-to-end, empty, tool calls |
| `TestFormatHelpers` | 4 | Empty strings, result priority, all content types |
| **Total** | **30** | All requirements covered |

## Test Results

```
441 passed in 10.30s
```

- 411 existing tests: all pass (no regressions)
- 30 new tests: all pass

## Decisions Made

1. **Immutable update pattern**: For `UpdateBlock`, create a new `Block` instance rather than mutating the existing one. This matches the spec example and keeps blocks more predictable.

2. **Duplicated format functions**: Created separate `format_user_text()` and `format_assistant_text()` in consumer.py rather than importing from formatter.py. This avoids circular dependencies and keeps the consumer module self-contained with all the formatting logic it needs.

3. **Reused format_duration**: Imported `format_duration()` from formatter.py since it's a pure utility function with no dependencies.

4. **Late import for replay_session**: Used a local import for `process_line` inside `replay_session()` to avoid circular import issues.

## Deviations from Spec

1. **Test count**: Spec requested ≥20 tests, implementation has 30 tests for more comprehensive coverage.

2. **Format functions**: Created local format functions rather than updating formatter.py, to keep the new event-driven code separate from the legacy code until Phase 4 (Integration & Migration).

## Definition of Done Checklist

- [x] ScreenStateConsumer handles all event types (AddBlock, UpdateBlock, ClearAll)
- [x] to_markdown() produces output matching the old formatter's format
- [x] replay_session() convenience function works
- [x] ≥20 unit tests (30 tests), all passing
- [x] All prior tests still pass (441 total)
