# Issue #137: End-to-end tests for question presentation in messaging

## Summary

Added comprehensive end-to-end tests that verify the complete question presentation flow from JSONL session events through to Telegram/Slack message output.

## Changes Made

### 1. Test Fixtures (tests/watcher/conftest.py)

Added four new fixtures for question-related JSONL lines:

- `question_jsonl_line` - Single AskUserQuestion tool_use with tool_use_id "toolu_q123", 3 options
- `question_answer_jsonl_line` - User's answer with toolUseResult.answers
- `multi_question_jsonl_line` - AskUserQuestion with 2 questions
- `many_options_jsonl_line` - AskUserQuestion with 8 options (triggers truncation)

### 2. End-to-End Tests (tests/watcher/test_question_e2e.py)

Created new test file with 10 tests across 3 test classes:

**TestQuestionPipelineE2E (5 tests):**
- `test_question_jsonl_to_telegram_keyboard` - Full pipeline: JSONL -> Event -> MessageAction -> Telegram keyboard
- `test_question_jsonl_to_slack_blocks` - Full pipeline: JSONL -> Event -> MessageAction -> Slack blocks
- `test_answer_updates_remove_keyboard` - Answer event produces UpdateExistingMessage with remove_keyboard flag
- `test_multiple_questions_single_message` - Multiple questions render with dividers
- `test_many_options_truncated` - Options >5 are truncated with overflow message

**TestTelegramCallbackE2E (2 tests):**
- `test_callback_data_format` - Verify callback_data format "q:{tool_use_id}:{question_idx}:{option_idx}"
- `test_callback_data_with_multiple_questions` - Verify correct indexing across multiple questions

**TestSlackInteractionE2E (3 tests):**
- `test_action_id_format` - Verify action_id starts with "question_opt_"
- `test_action_id_with_multiple_questions` - Verify correct indexing across multiple questions
- `test_block_id_contains_tool_use_id` - Verify actions block_id contains tool_use_id

## Test Approach

The tests follow an end-to-end approach without mocking core processing logic:
- Use real `ProcessingContext` and `process_line()` for event generation
- Use real `MessageStateTracker` for action generation
- Verify actual Telegram `format_question_keyboard()` and `format_question_text()` output
- Verify actual Slack `format_question_blocks()` and `format_answered_question_blocks()` output
- Verify callback/action ID formats match what handlers expect

## Key Validations

1. **Pipeline integrity** - JSONL is correctly classified, processed, and converted to events
2. **Telegram keyboard** - Inline keyboard has correct button labels and callback data format
3. **Slack blocks** - Block Kit structure with correct action_id and value formats
4. **Answer handling** - UpdateExistingMessage with remove_keyboard metadata
5. **Multi-question support** - Dividers between questions, correct indexing
6. **Truncation** - MAX_QUESTION_BUTTONS (5) limit with overflow message

## Files Changed

- `tests/watcher/conftest.py` - Added 4 question JSONL fixtures
- `tests/watcher/test_question_e2e.py` - New file with 10 tests

## Test Results

All 10 new tests pass:
```
tests/watcher/test_question_e2e.py::TestQuestionPipelineE2E::test_question_jsonl_to_telegram_keyboard PASSED
tests/watcher/test_question_e2e.py::TestQuestionPipelineE2E::test_question_jsonl_to_slack_blocks PASSED
tests/watcher/test_question_e2e.py::TestQuestionPipelineE2E::test_answer_updates_remove_keyboard PASSED
tests/watcher/test_question_e2e.py::TestQuestionPipelineE2E::test_multiple_questions_single_message PASSED
tests/watcher/test_question_e2e.py::TestQuestionPipelineE2E::test_many_options_truncated PASSED
tests/watcher/test_question_e2e.py::TestTelegramCallbackE2E::test_callback_data_format PASSED
tests/watcher/test_question_e2e.py::TestTelegramCallbackE2E::test_callback_data_with_multiple_questions PASSED
tests/watcher/test_question_e2e.py::TestSlackInteractionE2E::test_action_id_format PASSED
tests/watcher/test_question_e2e.py::TestSlackInteractionE2E::test_action_id_with_multiple_questions PASSED
tests/watcher/test_question_e2e.py::TestSlackInteractionE2E::test_block_id_contains_tool_use_id PASSED
```

Full test suite passes: 2015 tests in ~3.5 minutes.
