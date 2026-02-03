# Issue 09 Worklog: Compaction, Sub-Agents & Edge Cases

## Files Modified

| File | Description |
|------|-------------|
| `claude_session_player/parser.py` | Added `isSidechain` handling in `classify_line()`, updated `get_tool_result_info()` to handle null/list content |
| `claude_session_player/renderer.py` | Added `_get_task_result_text()` for Task tool collapsed rendering in `_render_tool_result()` |
| `tests/conftest.py` | Added 9 new fixtures for sidechain, Task tool, and content variation tests |
| `tests/test_renderer.py` | Added 6 new test classes with 33 tests for compaction, Task results, content variations, edge cases |
| `tests/test_parser.py` | Added 5 new test classes with 17 tests for isSidechain, content variations, defensive handling |

## Features Implemented

### 1. isSidechain Messages (INVISIBLE)

Added check at the top of `classify_line()` to mark sidechain messages as INVISIBLE:

```python
if line.get("isSidechain") and msg_type in ("user", "assistant"):
    return LineType.INVISIBLE
```

This ensures sub-agent internal messages don't pollute the main session rendering.

### 2. Task Tool Collapsed Result Rendering

Added `_get_task_result_text()` to extract collapsed result text from `toolUseResult.content[0].text`:
- Extracts first 80 chars of the content text
- Truncates with `…` if > 80 chars
- Returns `None` if not available, triggering fallback to normal result handling

The `_render_tool_result()` function now checks if the tool is "Task" and uses the collapsed text if available.

### 3. Tool Result Content Variations

Updated `get_tool_result_info()` to properly handle all content variations:
- String content → uses directly
- List content → extracts text from `type: "text"` blocks only, joins with newlines
- `None`/null content → returns empty string (becomes "(no output)")
- Missing content key → returns empty string

### 4. User Message List Content

The existing `get_user_text()` already handled list content correctly:
- Extracts text from dict blocks with `.get("text", "")`
- Handles plain string items in the list
- Joins all parts with newlines

No changes needed; verified with tests.

### 5. Context Compaction Verification

The compaction handling was already implemented in Issue 07 (`state.clear()`). This issue verified:
- Multiple compactions work (clear → build → clear → build)
- Summary messages before compact_boundary are INVISIBLE
- Tool calls from before compaction are no longer matchable after compaction
- Only post-last-compaction content is rendered

## Edge Cases Discovered

### Real Data Patterns

1. **isSidechain in main session**: Some session files contain messages with `isSidechain: true`. These are internal sub-agent messages that leaked into the main session file. They should be invisible.

2. **toolUseResult structure**: Task tool results have a complex structure with `status`, `agentId`, `content`, `totalDurationMs`, `totalTokens`, `totalToolUseCount`. The `content` field contains the actual result to display.

3. **Null content in tool results**: Some tools return `null` content on success (e.g., Write tool). This was being converted to the string "None" via `str(block_content)`. Fixed to return empty string.

4. **List content with non-text blocks**: Tool results can contain image blocks or other non-text blocks. Updated to explicitly check for `type: "text"` when extracting from list content.

### Defensive Handling Already Present

The codebase already handled many edge cases:
- Empty content list on assistant → INVISIBLE (in `_classify_assistant`)
- Unknown content block type → INVISIBLE (not in `_ASSISTANT_BLOCK_MAP`)
- Missing message field → defensive `.get("message") or {}` throughout
- Unknown message type → INVISIBLE (at end of `classify_line`)
- queue-operation, pr-link, summary → all in `_INVISIBLE_TYPES`

## Test Results

```
299 passed in 0.58s
```

### New Tests (45 tests)

**test_renderer.py** (33 tests):
- `TestCompactionFlow` (5 tests): clear state/rebuild, multiple compactions, orphan results, summary invisible, full flow
- `TestTaskToolResults` (6 tests): tool use renders, collapsed result, truncation, empty content fallback, missing toolUseResult fallback, non-Task ignores toolUseResult
- `TestUserMessageContentVariations` (3 tests): string, single text block, multiple text blocks
- `TestToolResultContentVariations` (3 tests): string, list, null content
- `TestDefensiveEdgeCases` (8 tests): empty content, unknown block type, missing message, isSidechain user/assistant, unknown type, queue-operation, pr-link

**test_parser.py** (17 tests):
- `TestIsSidechainClassification` (4 tests): user invisible, assistant invisible, false not invisible, system type ignored
- `TestToolResultContentVariations` (5 tests): string, list extracts text, ignores non-text, null, missing
- `TestUserTextContentVariations` (4 tests): single block, multiple blocks, skips empty, handles strings
- `TestDefensiveClassification` (4 tests): non-dict block, missing type, progress without data, system without subtype

**test_conftest.py** (9 fixtures):
- `sidechain_user_line`, `sidechain_assistant_line`
- `task_tool_use_line`, `task_tool_result_line`
- `user_list_content_line`
- `tool_result_list_content_line`, `tool_result_null_content_line`

### Prior Tests

- 257 tests from Issues 01-08 — all pass unchanged

## Deviations from Spec

- No `match/case` statements used — consistent with prior issues, system Python is 3.9 which doesn't support structural pattern matching.

## Protocol Observations

1. **toolUseResult is top-level**: The `toolUseResult` field for Task results is at the top level of the user message, not inside `message.content`.

2. **Content block filtering**: When extracting text from list content, must explicitly check for `type: "text"` to avoid accidentally including image or other block types.

3. **isSidechain scope**: The `isSidechain` check only applies to user and assistant messages. System and progress messages don't have this field (or it's not meaningful for them).
