# Issue 31 Worklog: Support AskUserQuestion Tool Rendering

## Summary

Implemented support for rendering `AskUserQuestion` tool calls and their responses. This tool is used when Claude asks users to select from options or provide input.

## Files Modified

### Source Code

| File | Changes |
|------|---------|
| `claude_session_player/events.py` | Added `QUESTION` to `BlockType` enum, added `QuestionOption`, `Question`, and `QuestionContent` dataclasses, updated `BlockContent` union type |
| `claude_session_player/parser.py` | Added `get_ask_user_question_data()` and `get_tool_use_result_answers()` helper functions |
| `claude_session_player/processor.py` | Added `_question_content_cache`, `_store_question_content()`, `_process_ask_user_question()`, modified `_process_tool_use()` to detect AskUserQuestion, modified `_process_tool_result()` to handle answers |
| `claude_session_player/consumer.py` | Added `format_question()` function, updated `format_block()` to handle `QuestionContent` |
| `claude_session_player/__init__.py` | Added exports for `Question`, `QuestionContent`, `QuestionOption` |

### Tests

| File | Changes |
|------|---------|
| `tests/test_question.py` | Created with 21 comprehensive tests |
| `tests/test_events.py` | Updated `test_block_type_has_six_values` to `test_block_type_has_seven_values`, added `test_block_type_question` |

## Implementation Details

### New Types

```python
@dataclass
class QuestionOption:
    label: str
    description: str

@dataclass
class Question:
    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool = False

@dataclass
class QuestionContent:
    tool_use_id: str
    questions: list[Question]
    answers: dict[str, str] | None = None
```

### Event Flow

1. **AskUserQuestion tool_use** → `_process_ask_user_question()` creates `AddBlock(QUESTION, QuestionContent)` with questions parsed from input
2. **tool_result with toolUseResult.answers** → `_process_tool_result()` detects question block via cache, creates `UpdateBlock` with answers filled in
3. **Orphan answer** (no matching question) → Falls through to SystemOutput as with other orphan results

### Rendering Format

**Pending (no answers):**
```
● Question: Pkg manager
  ├ How should we manage dependencies?
  │ ○ uv (Recommended)
  │ ○ poetry
  │ ○ pip + requirements.txt
  └ (awaiting response)
```

**Answered:**
```
● Question: Pkg manager
  ├ How should we manage dependencies?
  └ ✓ uv (Recommended)
```

## Test Coverage

- 21 new tests in `test_question.py`
- 1 new test in `test_events.py` (BlockType.QUESTION)
- Total: 295 tests passing
- Coverage: 98%

### Test Categories

1. **Parser tests** (4 tests): Extract questions and answers from JSONL
2. **Processor tests** (7 tests): Event generation for questions and answers
3. **Rendering tests** (4 tests): Markdown output formatting
4. **Integration tests** (3 tests): Full question → answer flow
5. **Edge case tests** (3 tests): Empty options, partial answers, long labels

## Decisions Made

1. **Question block vs Tool block**: Created separate `QUESTION` block type rather than reusing `TOOL_CALL` to enable distinct rendering format with options and checkmarks
2. **Question cache**: Added `_question_content_cache` parallel to `_tool_content_cache` to preserve questions when answers arrive
3. **Partial answers**: When only some questions are answered, answered ones show checkmark, pending ones show options with "(awaiting response)"
4. **Multi-select**: Preserved `multi_select` flag in data model though current rendering treats all questions the same way

## Definition of Done Checklist

- [x] QuestionContent and related types defined
- [x] AskUserQuestion tool_use classified and processed
- [x] Answers matched to questions via tool_use_id
- [x] Rendering shows questions and selected answers
- [x] ≥10 unit tests, all passing (21 tests)
- [x] All prior tests still pass (295 total)
- [x] Coverage maintained (98%)
