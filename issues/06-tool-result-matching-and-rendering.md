# Issue 06: Tool Result Matching & Rendering

## Priority: P0 — Core
## Dependencies: Issue 05
## Estimated Complexity: Medium

## Summary

Implement rendering of tool results — when a tool completes, its output is displayed underneath the corresponding tool call line with a `└` or `✗` connector.

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md` through `issues/worklogs/05-worklog.md`

After the assistant calls a tool, the next relevant JSONL line is a `user` message containing a `tool_result` content block. The result must be matched to the original tool call (via `tool_use_id`) and displayed underneath it.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Tool Result Matching", "Tool Result Rendering"
- `claude-code-session-protocol-schema.md` — section 7.2 "Tool Result", 7.3 "toolUseResult Metadata"

### Real Data Examples

**Bash result (success):**
```json
{
  "type": "user",
  "message": {
    "content": [{
      "tool_use_id": "toolu_011KE171EW6bVUT2iv2aBzx7",
      "type": "tool_result",
      "content": "Frontend cleaned",
      "is_error": false
    }]
  },
  "toolUseResult": {"stdout": "Frontend cleaned", "stderr": "", "interrupted": false}
}
```

**Write result:**
```json
{
  "type": "user",
  "message": {
    "content": [{
      "tool_use_id": "toolu_01CdGooruESj6nTjDN2ULtEM",
      "type": "tool_result",
      "content": "File created successfully at: /Users/agutnikov/work/trello-clone/.gitignore"
    }]
  },
  "toolUseResult": {"type": "create", "filePath": "/Users/.../gitignore", "content": "..."}
}
```

## Detailed Requirements

### 1. Render TOOL_RESULT

When `classify_line` returns `TOOL_RESULT`:

1. Extract results via `get_tool_result_info(line)` → `[(tool_use_id, content, is_error)]`
2. For each result:
   a. Look up `tool_use_id` in `state.tool_calls` to find the element index
   b. If found, update the `ToolCall` element:
      - `element.result = truncate_result(content)`
      - `element.is_error = is_error`
   c. If NOT found (orphan result), append a standalone `SystemOutput` with the content
3. Reset `state.current_request_id = None` (tool result breaks assistant grouping)

### 2. Result Truncation

```python
def truncate_result(text: str, max_lines: int = 5) -> str:
    """Truncate tool result to max_lines. Add … if truncated."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines - 1]) + "\n…"
```

- Max 5 lines of output
- If truncated, replace last visible line with `…`
- Empty result → `(no output)`

### 3. Update format_element for ToolCall

The ToolCall formatting must now handle results:

```
● Bash(Remove node_modules and build artifacts)
  └ Frontend cleaned
```

For errors:
```
● Bash(invalid command here…)
  ✗ command not found: invalid
```

For multi-line results:
```
● Bash(git status)
  └ On branch main
    Your branch is up to date
    Changes not staged:
      modified: file.py
```

Multi-line result formatting:
- First line: `  └ {first_line}` (or `  ✗ {first_line}` for errors)
- Subsequent lines: `    {line}` (4-space indent, aligning with text after `└ `)

### 4. Parallel Tool Results

Multiple tool results may arrive for parallel tool calls. Each is a separate JSONL line with one `tool_result` block. Process each individually, matching by `tool_use_id`.

Note: In the JSONL data, each tool result message contains exactly ONE `tool_result` block (not multiple). But `get_tool_result_info` returns a list for forward-compatibility.

### 5. Missing Tool Call (Orphan Result)

If a `tool_use_id` has no match in `state.tool_calls`:
- This can happen if the session was compacted (tool call in pre-compaction, result in post-compaction)
- Render as a standalone `SystemOutput` with the content text

### 6. Add render() Dispatch

```python
case LineType.TOOL_RESULT:
    _render_tool_result(state, line)
```

## Test Requirements

### Result Matching:
- Tool result matches existing tool call → result field updated
- Tool result with `is_error=true` → `is_error` flag set on ToolCall
- Tool result with unknown tool_use_id → rendered as SystemOutput
- Multiple sequential tool results for different tool calls → each matched correctly

### Result Truncation:
- Short result (1-5 lines) → not truncated
- Long result (>5 lines) → truncated to 4 lines + `…`
- Empty result → `(no output)`
- Single-line result → single line

### Markdown Output:
- Tool call + success result → `● Tool(label)\n  └ output`
- Tool call + error result → `● Tool(label)\n  ✗ error message`
- Tool call + multi-line result → proper indentation
- Tool call + truncated result → `…` on last line
- Parallel tool calls + their results → each rendered correctly

### Full Flow:
- User input → assistant tool_use → tool_result → correct final markdown
- User input → 2 parallel tool_uses → 2 tool_results → all matched, all rendered

## Definition of Done

- [ ] `_render_tool_result()` matches results to tool calls via `tool_use_id`
- [ ] `ToolCall.result` and `ToolCall.is_error` updated correctly
- [ ] Result truncation to 5 lines with `…` marker
- [ ] Multi-line result formatting with proper indentation
- [ ] Error results use `✗` prefix
- [ ] Orphan results rendered as `SystemOutput`
- [ ] `current_request_id` reset on tool result
- [ ] ≥15 unit tests, all passing
- [ ] All prior tests still pass

## Worklog

Write `issues/worklogs/06-worklog.md` with:
- How matching was implemented
- Edge cases with truncation
- Test count and results
- Any real-data patterns that needed special handling
