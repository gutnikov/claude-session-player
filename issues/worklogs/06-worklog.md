# Issue 06 Worklog: Tool Result Matching & Rendering

## Files Created/Modified

| File | Description |
|------|-------------|
| `claude_session_player/formatter.py` | Added `truncate_result()` function, updated `format_element()` for multi-line result formatting |
| `claude_session_player/renderer.py` | Added `_render_tool_result()` function, added `TOOL_RESULT` dispatch in `render()`, imported new dependencies |
| `tests/test_formatter.py` | Added `TestTruncateResult` (7 tests), added 6 ToolCall result tests in `TestFormatElement` |
| `tests/test_renderer.py` | Added 4 test classes: `TestRenderToolResult` (5 tests), `TestRenderToolResultTruncation` (4 tests), `TestRenderToolResultMarkdown` (5 tests), `TestRenderToolResultFullFlow` (2 tests); fixed 1 existing test |

## How Matching Was Implemented

Tool result matching follows this flow:

1. **Render dispatch**: When `classify_line()` returns `TOOL_RESULT`, the main `render()` function calls `_render_tool_result(state, line)`.

2. **Result extraction**: `_render_tool_result()` uses `get_tool_result_info(line)` (from parser.py) to extract a list of `(tool_use_id, content, is_error)` tuples. Each tool result JSONL line typically contains one result, but the function handles multiple for forward-compatibility.

3. **Matching logic**: For each result tuple:
   - If `tool_use_id` exists in `state.tool_calls` (the dict mapping IDs to element indices), the matching `ToolCall` element is retrieved and updated with:
     - `element.result = truncate_result(content)` — truncated to 5 lines max
     - `element.is_error = is_error`
   - If no match found (orphan result), a new `SystemOutput` element is appended with the truncated content.

4. **Request ID reset**: After processing all results, `state.current_request_id` is set to `None` because tool results break assistant response grouping.

## Truncation Implementation

The `truncate_result()` function:
- Returns `"(no output)"` for empty strings
- Returns unchanged text if ≤5 lines
- Truncates to first 4 lines + `…` if >5 lines

## Multi-Line Result Formatting

The `format_element()` function was updated to handle multi-line results:
- First line: `  └ {first_line}` (or `  ✗ {first_line}` for errors)
- Subsequent lines: `    {line}` (4-space indent to align with text after the └/✗ connector)

Example:
```
● Bash(git status)
  └ On branch main
    Your branch is up to date
    Changes not staged:
      modified: file.py
```

## Edge Cases with Truncation

- **Empty result**: Returns `"(no output)"` instead of empty string
- **Whitespace-only content**: Treated as non-empty (returns unchanged)
- **Exactly 5 lines**: No truncation (boundary case)
- **6+ lines**: First 4 lines + `…`

## Test Count and Results

```
211 passed in 0.59s
```

### New Tests (28 tests)
- **TestTruncateResult** (7 tests): empty returns no output, single line, 5 lines, 6 lines truncated, 10 lines truncated, custom max_lines, whitespace
- **TestFormatElement ToolCall tests** (6 tests): single-line result, multi-line result, error result, multi-line error, truncated result (new); also kept existing basic tests
- **TestRenderToolResult** (5 tests): match existing tool call, is_error flag, orphan result creates SystemOutput, resets request_id, multiple sequential results
- **TestRenderToolResultTruncation** (4 tests): short not truncated, long truncated, empty shows no output, single line
- **TestRenderToolResultMarkdown** (5 tests): success result, error result, multi-line result, truncated result, parallel tool calls with results
- **TestRenderToolResultFullFlow** (2 tests): user→tool_use→result, 2 parallel tool_uses→2 results

### Prior Tests
- 183 tests from Issues 01-05 — all pass unchanged (1 test assertion updated to match new multi-line formatting)

## Real-Data Patterns That Needed Special Handling

1. **Orphan results**: When sessions are compacted, a tool result may reference a tool_use_id from before the compaction boundary. These are rendered as standalone `SystemOutput` elements rather than failing silently.

2. **Parallel tool results**: The real data shows that each parallel tool result arrives in a separate JSONL line with exactly one `tool_result` block. The implementation handles this correctly by processing results individually.

3. **Empty results**: Some tools (like Write) may return success with empty content. These are rendered as `(no output)` for clarity.

## Deviations from Spec

- No `match/case` statements used — consistent with Issues 03-05, system Python is 3.9 which doesn't support structural pattern matching.
