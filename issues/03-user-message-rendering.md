# Issue 03: User Message Rendering

## Priority: P0 — Core
## Dependencies: Issues 01, 02
## Estimated Complexity: Low-Medium

## Summary

Implement rendering of user input messages and local command output. This is the first rendering logic — it takes classified user messages and adds `ScreenElement` instances to `ScreenState`.

## Context

Before starting, read:
- `issues/worklogs/01-worklog.md`
- `issues/worklogs/02-worklog.md`

Users type messages in Claude Code and see them rendered with a `❯` prompt prefix. Local commands produce stdout output rendered as plain text.

### Key Spec References
- `.claude/specs/claude-session-player.md` — "Message Types & Visibility" (user rows), "Formatting Rules"

### Visual Output Examples

**Single-line user message:**
```
❯ hello world
```

**Multi-line user message:**
```
❯ split by working days please feature + LOC.
  create excel file with this data so i can
  build charts
```

**Local command output:**
```
✓ Installed feature-dev. Restart Claude Code to load new plugins.
```

## Detailed Requirements

### 1. Render User Input

When `classify_line` returns `USER_INPUT`:
1. Extract text via `get_user_text(line)`
2. Format: first line prefixed with `❯ `, subsequent lines indented with 2 spaces
3. Create `UserMessage(text=formatted_text)` and append to `state.elements`
4. Reset `state.current_request_id = None` (new user message breaks assistant grouping)

### 2. Render Local Command Output

When `classify_line` returns `LOCAL_COMMAND_OUTPUT`:
1. Extract text via `get_local_command_text(line)`
2. Create `SystemOutput(text=extracted_text)` and append to `state.elements`

### 3. Invisible Messages

When `classify_line` returns `INVISIBLE` → do nothing, return state unchanged.

### 4. Implement render() Dispatch (partial)

In `renderer.py`, implement the main `render()` function skeleton:

```python
def render(state: ScreenState, line: dict) -> ScreenState:
    line_type = classify_line(line)

    match line_type:
        case LineType.USER_INPUT:
            _render_user_input(state, line)
        case LineType.LOCAL_COMMAND_OUTPUT:
            _render_local_command(state, line)
        case LineType.INVISIBLE:
            pass
        case _:
            pass  # Other types handled in future issues

    return state
```

### 5. Implement to_markdown() (partial)

In `formatter.py` or as a method on `ScreenState`, implement markdown output for the element types created in this issue:

```python
def format_element(element: ScreenElement) -> str:
    match element:
        case UserMessage(text=text):
            return text  # Already formatted with ❯ prefix
        case SystemOutput(text=text):
            return text
        case _:
            return ""  # Other types in future issues

def to_markdown(state: ScreenState) -> str:
    parts = []
    for element in state.elements:
        formatted = format_element(element)
        if formatted:
            parts.append(formatted)
    return "\n\n".join(parts)
```

Elements separated by one blank line (double newline in markdown).

### 6. User Text Formatting

```python
def format_user_text(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return "❯"
    result = [f"❯ {lines[0]}"]
    for line in lines[1:]:
        result.append(f"  {line}")
    return "\n".join(result)
```

## Test Requirements

### Rendering Tests:
- Single-line user message → `❯ hello`
- Multi-line user message → first line `❯`, rest indented 2 spaces
- Empty user message → `❯`
- User message with special chars (markdown, unicode)
- Local command output → plain text without prefix
- Invisible message → state unchanged (elements list stays same length)
- isMeta=true user message → state unchanged

### State Mutation Tests:
- Verify `render` returns the same `ScreenState` object (identity check)
- Verify elements list grows by 1 after user input
- Verify `current_request_id` reset to None after user input

### to_markdown Tests:
- Empty state → empty string
- Single user message → formatted text
- Two user messages → separated by blank line
- User message + system output → separated by blank line
- Mixed elements render in order

### Integration Mini-Test:
- Feed 3 lines: invisible, user input, invisible → state has exactly 1 element
- Feed user input + local command output → state has 2 elements, correct markdown

## Definition of Done

- [ ] `render()` function dispatches USER_INPUT, LOCAL_COMMAND_OUTPUT, INVISIBLE correctly
- [ ] User text formatting with `❯` prefix and 2-space indent for continuation lines
- [ ] Local command text extraction from `<local-command-stdout>` tags
- [ ] `to_markdown()` produces correct output for UserMessage and SystemOutput
- [ ] Elements separated by blank lines in markdown
- [ ] `current_request_id` reset on user input
- [ ] ≥12 unit tests, all passing
- [ ] Render returns same state object (mutability verified)

## Worklog

Write `issues/worklogs/03-worklog.md` with:
- Files modified
- Formatting edge cases found
- Test count and results
- Any changes to models from issue 01
