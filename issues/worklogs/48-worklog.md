# Issue #48: Add to_dict/from_dict serialization to all event dataclasses

## Summary

Added comprehensive tests for the `to_dict()` and `from_dict()` serialization methods that were already implemented in `events.py`. The serialization support enables state persistence for the Session Watcher Service.

## Discovery

Upon investigation, all serialization methods were already implemented in `events.py`:
- `ProcessingContext.to_dict()` / `from_dict()`
- `Block.to_dict()` / `from_dict()`
- `UserContent.to_dict()` / `from_dict()`
- `AssistantContent.to_dict()` / `from_dict()`
- `ToolCallContent.to_dict()` / `from_dict()`
- `ThinkingContent.to_dict()` / `from_dict()`
- `DurationContent.to_dict()` / `from_dict()`
- `SystemContent.to_dict()` / `from_dict()`
- `QuestionOption.to_dict()` / `from_dict()`
- `Question.to_dict()` / `from_dict()`
- `QuestionContent.to_dict()` / `from_dict()`
- `content_from_dict()` dispatcher function

What was missing: comprehensive test coverage for these serialization methods.

## Changes Made

### Modified Files

1. **`tests/test_events.py`**
   - Added imports for `Question`, `QuestionContent`, `QuestionOption`, `content_from_dict`
   - Added 64 new serialization tests organized by content type:
     - `TestUserContentSerialization` (5 tests)
     - `TestAssistantContentSerialization` (3 tests)
     - `TestToolCallContentSerialization` (8 tests)
     - `TestThinkingContentSerialization` (3 tests)
     - `TestDurationContentSerialization` (4 tests)
     - `TestSystemContentSerialization` (3 tests)
     - `TestQuestionOptionSerialization` (3 tests)
     - `TestQuestionSerialization` (4 tests)
     - `TestQuestionContentSerialization` (5 tests)
     - `TestContentFromDict` (9 tests)
     - `TestBlockSerialization` (11 tests)
     - `TestProcessingContextSerialization` (7 tests)

2. **`issues/worklogs/48-worklog.md`** (this file)

## Test Coverage

Each serialization test class includes:
- `to_dict()` returns expected dict with type discriminator
- `from_dict()` reconstructs object correctly
- Round-trip test: `obj == Cls.from_dict(obj.to_dict())`
- Tests for missing optional fields using defaults
- Edge cases (empty text, zero duration, etc.)

The `content_from_dict()` dispatcher tests cover:
- All 7 content types correctly dispatched
- `KeyError` raised for unknown type
- `KeyError` raised for missing type field

## Test Results

- **Before:** 36 tests in `test_events.py`, 408 total
- **After:** 100 tests in `test_events.py`, 472 total
- **New tests:** 64 serialization tests
- All 472 tests pass

## Acceptance Criteria Status

- [x] All dataclasses have `to_dict()` and `from_dict()` methods (already implemented)
- [x] Round-trip works: `obj == Cls.from_dict(obj.to_dict())` (verified via tests)
- [x] `content_from_dict()` correctly dispatches all content types (7 types including QuestionContent)
- [x] No external dependencies (stdlib only)
- [x] Type hints on all methods (already present)

## Testing DoD Status

- [x] Unit test for each dataclass: `to_dict()` returns expected dict
- [x] Unit test for each dataclass: `from_dict()` reconstructs object
- [x] Round-trip test for each dataclass
- [x] Test `content_from_dict()` with all content types
- [x] Test `from_dict()` with missing optional fields (uses defaults)
- [x] Test `Block.from_dict()` correctly uses `content_from_dict()`
- [x] All tests pass
- [x] No decrease in coverage
