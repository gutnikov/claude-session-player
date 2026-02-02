# Issue 02: JSONL Parser & Line Classification

## Priority: P0 — Foundation
## Dependencies: Issue 01
## Estimated Complexity: Medium

## Summary

Implement the JSONL parser that reads session files and classifies each line into its message type and subtype. This is the "input side" of the pipeline — it takes raw JSON dicts and determines what kind of screen update they represent.

## Context

Before reading, check `issues/worklogs/01-worklog.md` for any deviations from spec.

Claude Code session files are JSONL (one JSON object per line). Each line has a `type` field that determines the message category, and within each category there are subtypes. The parser must classify each line so the renderer knows what to do with it.

### Key Spec References
- `.claude/specs/claude-session-player.md` — section "Detecting Message Subtypes"
- `claude-code-session-protocol-schema.md` — sections 3 (Common Envelope Fields), 4 (Message Types Reference)

### Real Data Patterns (from protocol research)

**User message subtypes** — classified by examining `isMeta`, `message.content` type, and content:
```
isMeta=true                           → INVISIBLE (skill expansion or caveat)
message.content is str:
  contains <local-command-stdout>     → LOCAL_COMMAND_OUTPUT
  contains <local-command-caveat>     → INVISIBLE (but also isMeta=true)
  otherwise                           → USER_INPUT
message.content is list:
  any block has type="tool_result"    → TOOL_RESULT
  otherwise                           → USER_INPUT (content blocks)
```

**Assistant message subtypes** — from `message.content[0].type`:
```
"text"      → ASSISTANT_TEXT
"tool_use"  → TOOL_USE
"thinking"  → THINKING
```

**System message subtypes** — from `subtype` field:
```
"turn_duration"    → TURN_DURATION
"compact_boundary" → COMPACT_BOUNDARY
"local_command"    → INVISIBLE
```

**Progress subtypes** — from `data.type` field:
```
"bash_progress"            → BASH_PROGRESS
"hook_progress"            → HOOK_PROGRESS
"agent_progress"           → AGENT_PROGRESS
"query_update"             → QUERY_UPDATE
"search_results_received"  → SEARCH_RESULTS
"waiting_for_task"         → WAITING_FOR_TASK
```

**Always invisible types:**
```
"file-history-snapshot" → INVISIBLE
"queue-operation"       → INVISIBLE
"summary"               → INVISIBLE
"pr-link"               → INVISIBLE
```

## Detailed Requirements

### 1. Line Classification Enum

```python
from enum import Enum, auto

class LineType(Enum):
    # User
    USER_INPUT = auto()
    TOOL_RESULT = auto()
    LOCAL_COMMAND_OUTPUT = auto()

    # Assistant
    ASSISTANT_TEXT = auto()
    TOOL_USE = auto()
    THINKING = auto()

    # System
    TURN_DURATION = auto()
    COMPACT_BOUNDARY = auto()

    # Progress
    BASH_PROGRESS = auto()
    HOOK_PROGRESS = auto()
    AGENT_PROGRESS = auto()
    QUERY_UPDATE = auto()
    SEARCH_RESULTS = auto()
    WAITING_FOR_TASK = auto()

    # Skip
    INVISIBLE = auto()
```

### 2. classify_line Function

```python
def classify_line(line: dict) -> LineType:
    """Classify a parsed JSONL line into its rendering type."""
```

Must handle:
- Missing `type` field → `INVISIBLE` (defensive)
- Unknown `type` values → `INVISIBLE`
- Unknown system `subtype` values → `INVISIBLE`
- Unknown progress `data.type` values → `INVISIBLE`

### 3. JSONL File Reader

```python
def read_session(path: str | Path) -> list[dict]:
    """Read a JSONL file and return list of parsed dicts."""
```

- One JSON object per line
- Skip empty lines
- Skip lines that fail JSON parsing (log warning, don't crash)
- Return list in file order

### 4. Field Extraction Helpers

Create helpers that extract commonly needed fields from classified lines:

```python
def get_user_text(line: dict) -> str:
    """Extract display text from a user input message."""

def get_tool_use_info(line: dict) -> tuple[str, str, dict]:
    """Extract (tool_name, tool_use_id, input_dict) from a tool_use message."""

def get_tool_result_info(line: dict) -> list[tuple[str, str, bool]]:
    """Extract [(tool_use_id, content, is_error)] from a tool_result message."""

def get_request_id(line: dict) -> str | None:
    """Extract requestId from an assistant message."""

def get_duration_ms(line: dict) -> int:
    """Extract durationMs from a turn_duration system message."""

def get_progress_data(line: dict) -> dict:
    """Extract the data dict from a progress message."""

def get_parent_tool_use_id(line: dict) -> str | None:
    """Extract parentToolUseID from a progress message."""

def get_local_command_text(line: dict) -> str:
    """Extract text from <local-command-stdout> tags."""
```

## Test Requirements

### Classification Tests (test each path):
- User input with string content → `USER_INPUT`
- User input with `isMeta=true` → `INVISIBLE`
- User input with `tool_result` content → `TOOL_RESULT`
- User input with `<local-command-stdout>` → `LOCAL_COMMAND_OUTPUT`
- Assistant with text block → `ASSISTANT_TEXT`
- Assistant with tool_use block → `TOOL_USE`
- Assistant with thinking block → `THINKING`
- System with `turn_duration` → `TURN_DURATION`
- System with `compact_boundary` → `COMPACT_BOUNDARY`
- System with `local_command` → `INVISIBLE`
- Each progress subtype → correct enum
- `file-history-snapshot` → `INVISIBLE`
- `queue-operation` → `INVISIBLE`
- `summary` → `INVISIBLE`
- `pr-link` → `INVISIBLE`
- Unknown type → `INVISIBLE`
- Missing type field → `INVISIBLE`
- Empty dict → `INVISIBLE`

### Extraction Tests:
- `get_user_text` with single-line and multi-line content
- `get_tool_use_info` with Bash, Read, Write tool calls
- `get_tool_result_info` with success and error results
- `get_tool_result_info` with multiple results (parallel tools)
- `get_request_id` present and absent
- `get_duration_ms` with various durations
- `get_local_command_text` extracts text between XML tags
- `get_parent_tool_use_id` present and absent

### File Reader Tests:
- Read valid JSONL file
- Skip empty lines
- Handle malformed JSON lines without crashing
- Return correct number of parsed dicts

### Real Data Tests:
- Read a real session file from `examples/` and verify all lines classify without error
- Verify no crashes on any example file

## Test Fixtures

Create `tests/fixtures/` with hand-crafted JSONL dicts for each message type. Example:

```python
# tests/conftest.py additions

@pytest.fixture
def user_input_line():
    return {
        "type": "user",
        "isMeta": False,
        "uuid": "aaa-111",
        "parentUuid": None,
        "sessionId": "sess-001",
        "message": {"role": "user", "content": "hello world"},
    }

@pytest.fixture
def tool_use_line():
    return {
        "type": "assistant",
        "uuid": "bbb-222",
        "parentUuid": "aaa-111",
        "requestId": "req_001",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "toolu_001", "name": "Bash", "input": {"command": "ls -la", "description": "List files"}}],
            "stop_reason": None,
        },
    }

# ... etc for each type
```

## Definition of Done

- [ ] `LineType` enum with all 16 variants defined
- [ ] `classify_line()` correctly classifies all message types and subtypes
- [ ] `classify_line()` handles missing/unknown fields defensively (returns `INVISIBLE`)
- [ ] `read_session()` reads JSONL files, skips bad lines
- [ ] All field extraction helpers implemented and tested
- [ ] ≥25 unit tests covering every classification path
- [ ] ≥10 extraction helper tests
- [ ] ≥3 file reader tests
- [ ] At least 1 test using a real example JSONL file
- [ ] All tests passing

## Worklog

Write `issues/worklogs/02-worklog.md` with:
- Files created/modified
- Final enum values (if any changed from spec)
- Edge cases discovered in real data
- Test count and results
- Any fields found in real data not covered by the spec
