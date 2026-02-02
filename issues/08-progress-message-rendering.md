# Issue 08: Progress Message Rendering

## Priority: P1 — Important
## Dependencies: Issues 05, 06
## Estimated Complexity: Medium

## Summary

Implement rendering of all progress message types — bash output streaming, hook execution, web search progress, agent activity, and task waiting. Progress messages update existing tool call widgets rather than creating new screen elements.

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md` through `issues/worklogs/07-worklog.md`

Progress messages are emitted during long-running tool operations. They update the `└` line under the corresponding tool call. They link to tool calls via the `parentToolUseID` field.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Progress Message Matching", progress rows in visibility table
- `claude-code-session-protocol-schema.md` — section 4.5 "progress"

### Real Data Examples

**bash_progress:**
```json
{
  "type": "progress",
  "data": {
    "type": "bash_progress",
    "output": "",
    "fullOutput": "Building...\nStep 1/12: FROM python:3.11-slim",
    "elapsedTimeSeconds": 2,
    "totalLines": 0
  },
  "toolUseID": "bash-progress-0",
  "parentToolUseID": "toolu_01HqccoujvbFF2QgwjUyyqQA"
}
```

**hook_progress:**
```json
{
  "type": "progress",
  "data": {
    "type": "hook_progress",
    "hookEvent": "PostToolUse",
    "hookName": "PostToolUse:Read",
    "command": "callback"
  },
  "parentToolUseID": "toolu_01EiLY1EmfaBBjhfyypEjKWt",
  "toolUseID": "toolu_01EiLY1EmfaBBjhfyypEjKWt"
}
```

**query_update (WebSearch):**
```json
{
  "type": "progress",
  "data": {
    "type": "query_update",
    "query": "Claude Code hooks feature 2026"
  },
  "parentToolUseID": "toolu_xyz"
}
```

**search_results_received:**
```json
{
  "type": "progress",
  "data": {
    "type": "search_results_received",
    "resultCount": 10,
    "query": "Claude Code hooks feature 2026"
  },
  "parentToolUseID": "toolu_xyz"
}
```

**waiting_for_task:**
```json
{
  "type": "progress",
  "data": {
    "type": "waiting_for_task",
    "taskDescription": "Debug socat bridge from inside Docker container",
    "taskType": "local_bash"
  }
}
```

## Detailed Requirements

### 1. Progress → Tool Call Matching

All progress messages (except `waiting_for_task`) have a `parentToolUseID` field that matches the `tool_use.id` of the original tool call:

```python
parent_id = get_parent_tool_use_id(line)  # from parser.py
if parent_id and parent_id in state.tool_calls:
    idx = state.tool_calls[parent_id]
    tool_call = state.elements[idx]  # must be a ToolCall
    tool_call.progress_text = progress_text
```

If no match found → ignore the progress message (defensive).

### 2. Progress Text Formatting

Each progress subtype produces a different text:

| Subtype | Text | Source Fields |
|---|---|---|
| `bash_progress` | Last non-empty line of `data.fullOutput` | `data.fullOutput` |
| `hook_progress` | `Hook: {data.hookName}` | `data.hookName` |
| `agent_progress` | `Agent: working…` | (fixed text) |
| `query_update` | `Searching: {data.query}` | `data.query` |
| `search_results_received` | `{data.resultCount} results` | `data.resultCount` |
| `waiting_for_task` | `Waiting: {data.taskDescription}` | `data.taskDescription` |

### 3. bash_progress Special Handling

For `bash_progress`, display the last non-empty line of `fullOutput` (truncated to 76 chars to fit within 80 cols with the `  └ ` prefix):

```python
def get_bash_progress_text(data: dict) -> str:
    full_output = data.get("fullOutput", "")
    lines = [l for l in full_output.split("\n") if l.strip()]
    if not lines:
        return "running…"
    last_line = lines[-1]
    if len(last_line) > 76:
        return last_line[:75] + "…"
    return last_line
```

### 4. Progress Overwrites Previous Progress

Multiple progress messages for the same tool call overwrite each other. The `progress_text` field on `ToolCall` always reflects the LATEST progress message. When the tool result arrives (issue 06), it replaces the progress text with the final result.

### 5. waiting_for_task Without Tool Matching

`waiting_for_task` may not have a `parentToolUseID`. If it doesn't, or if the ID doesn't match any tool call, render it as a standalone element:
- Append `SystemOutput(text=f"└ Waiting: {description}")` to state.elements

### 6. Update format_element for Progress

The ToolCall format_element should show progress_text when result is not yet set:

```python
case ToolCall():
    line = f"● {element.tool_name}({element.label})"
    if element.result is not None:
        prefix = "  ✗ " if element.is_error else "  └ "
        result_lines = element.result.split("\n")
        line += f"\n{prefix}{result_lines[0]}"
        for rl in result_lines[1:]:
            line += f"\n    {rl}"
    elif element.progress_text is not None:
        line += f"\n  └ {element.progress_text}"
    return line
```

Result takes priority over progress (result is the final state).

### 7. Add render() Dispatches

```python
case LineType.BASH_PROGRESS:
    _render_bash_progress(state, line)
case LineType.HOOK_PROGRESS:
    _render_hook_progress(state, line)
case LineType.AGENT_PROGRESS:
    _render_agent_progress(state, line)
case LineType.QUERY_UPDATE:
    _render_query_update(state, line)
case LineType.SEARCH_RESULTS:
    _render_search_results(state, line)
case LineType.WAITING_FOR_TASK:
    _render_waiting_for_task(state, line)
```

## Test Requirements

### Matching:
- bash_progress with valid parentToolUseID → updates ToolCall.progress_text
- bash_progress with unknown parentToolUseID → ignored, state unchanged
- hook_progress → updates correct ToolCall
- Multiple progress messages → last one wins

### Formatting:
- bash_progress with multi-line fullOutput → last non-empty line
- bash_progress with empty fullOutput → `running…`
- bash_progress with long line → truncated at 76 chars
- hook_progress → `Hook: PostToolUse:Read`
- agent_progress → `Agent: working…`
- query_update → `Searching: Claude Code hooks 2026`
- search_results_received → `10 results`
- waiting_for_task → `Waiting: Debug socat bridge…`

### Priority:
- Tool call with progress_text → shows progress in markdown
- Tool call with progress_text then result → shows result (not progress)
- Tool call with neither → just the `● Tool(label)` line

### Full Flow:
- Tool_use → bash_progress → bash_progress → tool_result
  → markdown shows result (not last progress)
- Tool_use → bash_progress → markdown shows progress
- Tool_use → hook_progress → tool_result → markdown shows result

## Definition of Done

- [ ] All 6 progress subtypes handled
- [ ] Matching via `parentToolUseID` → `state.tool_calls`
- [ ] bash_progress extracts last non-empty line from fullOutput
- [ ] Progress overwrites previous progress on same tool call
- [ ] Result takes priority over progress in format_element
- [ ] waiting_for_task works with and without tool matching
- [ ] ≥18 unit tests, all passing
- [ ] All prior tests still pass

## Worklog

Write `issues/worklogs/08-worklog.md` with:
- Progress types found in real data vs spec
- Edge cases with matching
- Test count and results
