# Issue 04: Assistant Text Block Rendering

## Priority: P0 — Core
## Dependencies: Issues 01, 02
## Estimated Complexity: Medium

## Summary

Implement rendering of assistant text blocks, including `requestId`-based merging of content blocks that belong to the same API response.

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md`
- `issues/worklogs/02-worklog.md`
- `issues/worklogs/03-worklog.md`

Assistant responses in Claude Code are split into one JSONL line per content block (thinking, text, tool_use). Text blocks sharing the same `requestId` belong to the same logical response and must be merged visually (no blank line between them).

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Content Block Merging", assistant rows in visibility table
- `claude-code-session-protocol-schema.md` — section 10 "Streaming & Content Block Splitting"

### Real Data Pattern

A single API response producing `[thinking, text]` generates 2 JSONL lines:

```jsonl
{"type":"assistant","requestId":"req_001","message":{"content":[{"type":"thinking","thinking":"Let me..."}],"stop_reason":null}}
{"type":"assistant","requestId":"req_001","message":{"content":[{"type":"text","text":"Here's what I found..."}],"stop_reason":"end_turn"}}
```

Both share `requestId: "req_001"`. The thinking renders as `✱ Thinking…` and the text as `● text`. No blank line between them because they're the same response.

## Detailed Requirements

### 1. Render ASSISTANT_TEXT

When `classify_line` returns `ASSISTANT_TEXT`:
1. Extract `requestId` from line via `get_request_id(line)`
2. Extract text from `line["message"]["content"][0]["text"]`
3. Format text: first line prefixed with `● `, continuation lines indented 2 spaces
4. **If `requestId` matches `state.current_request_id`**: this is a continuation block — append to the same response group (no blank line separator when rendering)
5. **If `requestId` is new**: start a new response group, set `state.current_request_id = requestId`
6. Append `AssistantText(text=formatted_text)` to `state.elements`

### 2. Response Group Tracking

The `current_request_id` on `ScreenState` tracks whether consecutive assistant blocks belong together:
- When a new assistant block arrives with the same `requestId` as `current_request_id`, it's part of the same response
- When a non-assistant line arrives (user input, system, etc.), reset `current_request_id = None`
- In `to_markdown()`, elements from the same request group have no blank line between them

**Implementation approach**: Add a `request_id: str | None` field to each `ScreenElement` that's part of an assistant response. In `to_markdown()`, only insert blank line separator when consecutive elements have different (or None) request IDs.

Update the model:
```python
@dataclass
class AssistantText:
    text: str
    request_id: str | None = None
```

### 3. Assistant Text Formatting

```python
def format_assistant_text(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return "●"
    result = [f"● {lines[0]}"]
    for line in lines[1:]:
        result.append(f"  {line}")
    return "\n".join(result)
```

Markdown in the text is passed through verbatim — the output IS markdown, so `**bold**`, lists, code blocks, etc. all work naturally.

### 4. Update to_markdown()

Modify the `to_markdown()` logic to handle response grouping:

```python
def to_markdown(state: ScreenState) -> str:
    parts = []
    prev_request_id = None

    for element in state.elements:
        formatted = format_element(element)
        if not formatted:
            continue

        # Determine if we need a blank line separator
        current_rid = getattr(element, 'request_id', None)
        if parts and not (prev_request_id and current_rid and prev_request_id == current_rid):
            parts.append("")  # blank line
        parts.append(formatted)
        prev_request_id = current_rid

    return "\n".join(parts)
```

### 5. Add render() Dispatch

Extend the `render()` match statement:
```python
case LineType.ASSISTANT_TEXT:
    _render_assistant_text(state, line)
```

## Test Requirements

### Text Rendering:
- Single-line assistant text → `● hello`
- Multi-line assistant text → first line `● `, rest indented 2 spaces
- Empty text → `●`
- Text with markdown (bold, lists, code) → passed through unchanged
- Text with special characters

### RequestId Merging:
- Two text blocks with same requestId → no blank line between them in markdown
- Two text blocks with different requestIds → blank line between them
- Text block after user message → blank line separator
- Three blocks: thinking (future) + text + tool_use (future) with same requestId → grouped

### State Tracking:
- `current_request_id` set after assistant text block
- `current_request_id` reset when user input arrives between assistant blocks
- Multiple assistant blocks with same requestId: all elements have correct `request_id`

### Full Markdown Output:
- User message → assistant text → correct markdown with blank line between them
- User message → assistant text (req_1) → assistant text (req_1) → no blank line between assistant texts
- User message → assistant text (req_1) → user message → assistant text (req_2) → proper spacing

## Definition of Done

- [ ] `_render_assistant_text()` creates `AssistantText` elements with correct formatting
- [ ] `request_id` field added to `AssistantText` (and later other assistant elements)
- [ ] `to_markdown()` handles response grouping — no blank line within same `requestId`
- [ ] Blank lines correctly inserted between different response groups
- [ ] Markdown in text passed through verbatim
- [ ] `current_request_id` tracking works across render calls
- [ ] ≥15 unit tests, all passing
- [ ] Existing tests from issues 01-03 still pass

## Worklog

Write `issues/worklogs/04-worklog.md` with:
- Model changes (fields added to ScreenElement types)
- How response grouping was implemented
- Test count and results
- Any formatting decisions made
