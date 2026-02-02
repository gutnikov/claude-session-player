# Issue 09: Compaction, Sub-Agents & Edge Cases

## Priority: P1 — Polish
## Dependencies: All prior issues (01–08)
## Estimated Complexity: Medium-High

## Summary

Handle remaining edge cases: context compaction flow, sub-agent (Task tool) collapsed rendering, malformed data, and various protocol quirks found in real session files.

## Context

Before starting, read:
- ALL worklogs: `issues/worklogs/01-worklog.md` through `issues/worklogs/08-worklog.md`

This issue covers the "long tail" of protocol features that don't fit neatly into the main rendering pipeline.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Context Compaction", "Sub-Agent Rendering"
- `claude-code-session-protocol-schema.md` — sections 8 (Sub-Agent), 9 (Context Compaction)

## Detailed Requirements

### 1. Context Compaction Flow

The full compaction flow in a JSONL file looks like:

```
... (many messages) ...
{"type":"summary","summary":"Phase 5 implementation complete","leafUuid":"83df90f7-..."}
{"type":"system","subtype":"compact_boundary","compactMetadata":{"trigger":"auto","preTokens":155025}}
... (messages after compaction, starting fresh) ...
```

The `compact_boundary` handling is already implemented (issue 07 — `state.clear()`). This issue needs to verify:
- Multiple compactions in one session work (clear → build → clear → build)
- Summary messages before compact_boundary are correctly skipped (INVISIBLE)
- Tool calls from before compaction are no longer matchable after compaction
- The rendered output only shows post-last-compaction content

### 2. Sub-Agent (Task) Collapsed Rendering

When the assistant calls the `Task` tool:
- Tool call renders as: `● Task(description…)` (handled by issue 05)
- Tool result has `toolUseResult` with special structure:

```json
{
  "toolUseResult": {
    "status": "completed",
    "agentId": "ab97f57",
    "content": [{"type": "text", "text": "There are still 114 errors..."}],
    "totalDurationMs": 785728,
    "totalTokens": 126186,
    "totalToolUseCount": 77
  }
}
```

The result text to display: first 80 chars of `toolUseResult.content[0].text` (if available), otherwise fall back to the `message.content[0].content` string.

Implement special handling in `_render_tool_result()`:
```python
def _get_task_result_text(line: dict) -> str:
    """Extract collapsed result text for Task tool results."""
    tur = line.get("toolUseResult", {})
    if isinstance(tur, dict) and "content" in tur:
        content_list = tur.get("content", [])
        if content_list and isinstance(content_list[0], dict):
            text = content_list[0].get("text", "")
            if len(text) > 80:
                return text[:79] + "…"
            return text
    return None  # Fall back to normal result handling
```

### 3. User Message with Content Blocks (not string)

Some user messages have `message.content` as a list of content blocks (not a string). For example, when the user's input includes images or structured content:

```json
{"type":"user","message":{"content":[{"type":"text","text":"implement this"}]}}
```

The `get_user_text()` function must handle both:
- `content` is string → use directly
- `content` is list → extract text from `text`-type blocks, join with newlines

### 4. Assistant Blocks with Empty or Missing Content

Defensive handling:
- `message.content` is empty list → skip (INVISIBLE)
- `message.content[0]` has unknown type → skip
- Missing `message` field entirely → INVISIBLE

### 5. Tool Result Content Variations

The `content` field in a `tool_result` block can be:
- A string (most common)
- A list of content blocks (less common, for image results etc.)
- Missing/null (empty result)

Handle all:
```python
def _extract_result_content(block: dict) -> str:
    content = block.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        return "\n".join(texts)
    return "(no output)"
```

### 6. `isSidechain` Messages in Main Session

Main session files can contain messages with `isSidechain: true` (unusual but possible). These should be treated as INVISIBLE since we render collapsed sub-agents.

Update `classify_line()`:
```python
# At the top of classify_line, before type dispatch:
if line.get("isSidechain") and line.get("type") in ("user", "assistant"):
    return LineType.INVISIBLE
```

### 7. Queue Operations with Content

`queue-operation` with `operation: "enqueue"` has a `content` field with the queued message text. Per spec decision, these are INVISIBLE. No change needed — just verify it's handled.

### 8. Robustness: Unknown Message Types

Any `type` value not in the known set → `INVISIBLE`. Already handled, but verify with test.

## Test Requirements

### Compaction:
- Build state (5 elements) → summary → compact_boundary → state empty
- Compact → user → assistant → renders only post-compaction content
- Double compaction → only content after last compaction visible
- Tool call before compaction → tool result after compaction → orphan result handled

### Sub-Agent:
- Task tool_use → renders as `● Task(description…)`
- Task tool_result with `toolUseResult.content` → collapsed result text
- Task result text > 80 chars → truncated
- Task result with empty content → falls back to normal result
- Task result with missing toolUseResult → falls back to normal result

### Content Variations:
- User message with string content → normal rendering
- User message with list content → extracted text rendering
- Tool result with string content → normal
- Tool result with list content → extracted text
- Tool result with null content → `(no output)`

### Defensive:
- Empty content list on assistant → no crash, no element added
- Unknown content block type → no crash
- Missing message field → INVISIBLE
- isSidechain=true in main session → INVISIBLE
- Completely unknown message type → INVISIBLE

### Full Session Flow:
- Process a real session with compaction from examples/
- Verify no crashes and reasonable output

## Definition of Done

- [ ] Compaction clears state and only post-compaction content rendered
- [ ] Multiple compactions work correctly
- [ ] Task tool results use collapsed rendering (first 80 chars of content)
- [ ] User messages with list content handled
- [ ] Tool results with various content types handled
- [ ] isSidechain messages in main session → INVISIBLE
- [ ] No crashes on any malformed input
- [ ] ≥20 unit tests, all passing
- [ ] All prior tests still pass

## Worklog

Write `issues/worklogs/09-worklog.md` with:
- Edge cases discovered and how they were handled
- Real data patterns that required special handling
- Test count and results
- Any protocol spec updates needed
