# Issue #134 Worklog: Enable question block handling in MessageStateTracker

## Summary

Enabled `BlockType.QUESTION` blocks to flow through the messaging pipeline by updating `MessageStateTracker` to handle question blocks with proper `SendNewMessage` and `UpdateExistingMessage` actions.

## Files Modified

### `claude_session_player/watcher/message_state.py`

1. **Added `QuestionContent` import** (line 27)
   - Needed for type checking in `_handle_update_block()`

2. **Added `QuestionState` dataclass** (lines 74-83)
   - Tracks question state including `tool_use_id`, `block_id`, `content`
   - Stores message IDs per destination (`telegram_messages`, `slack_messages`)

3. **Updated `SessionMessageState`** (line 93)
   - Added `questions: dict[str, QuestionState]` to track questions by `tool_use_id`

4. **Updated `SendNewMessage`** (lines 103, 110)
   - Added `"question"` to `message_type` literal
   - Added `metadata: dict[str, str | bool]` field

5. **Updated `UpdateExistingMessage`** (line 121)
   - Added `metadata: dict[str, str | bool]` field

6. **Updated `_handle_add_block()`** (lines 346-347)
   - Changed from `NoAction(reason="Question blocks not yet supported...")`
   - Now calls `self._handle_question_block(state, block)`

7. **Updated `_handle_update_block()`** (lines 451-459)
   - Added handling for `QuestionContent` updates (answered questions)
   - Checks if `tool_use_id` exists in `state.questions`
   - Updates question state and renders via `_render_question_update()`

8. **Added `_handle_question_block()`** (lines 542-572)
   - Creates `QuestionState` and stores in `state.questions`
   - Formats text and Slack blocks
   - Returns `SendNewMessage` with metadata containing `tool_use_id` and `block_type`

9. **Added `_render_question_update()`** (lines 574-602)
   - Formats answered question for display
   - Returns `UpdateExistingMessage` if message IDs exist (with `remove_keyboard: True`)
   - Falls back to `SendNewMessage` if no message IDs recorded yet

10. **Added `_format_question_text()`** (lines 604-613)
    - Formats question for Telegram with `❓ {header}` and `_(respond in CLI)_`

11. **Added `_format_answered_question()`** (lines 615-628)
    - Formats answered question with `✓ Selected: {answer}`

12. **Added `_format_question_blocks()`** (lines 630-646)
    - Formats question as Slack Block Kit with section and context blocks

13. **Added `_format_answered_question_blocks()`** (lines 648-661)
    - Formats answered question for Slack with answer inline

14. **Added `record_question_message_id()`** (lines 664-687)
    - Records message ID for a question after sending

15. **Added `get_question_message_id()`** (lines 689-714)
    - Retrieves message ID for a question at a destination

### `claude_session_player/watcher/__init__.py`

- Already exports `QuestionState` (line 37, 126)

### `tests/watcher/test_message_state.py`

Added comprehensive tests:

1. **Test fixtures** (lines 113-175)
   - `make_question_block()` - creates single question blocks
   - `make_multi_question_block()` - creates blocks with multiple questions

2. **TestHandleQuestionBlock** (lines 1037-1108)
   - `test_question_block_returns_send_action` - verifies `SendNewMessage` returned
   - `test_question_block_tracks_state` - verifies question tracked in session state
   - `test_question_block_metadata` - verifies metadata includes `tool_use_id`, `block_type`
   - `test_question_block_turn_id` - verifies `turn_id` format
   - `test_question_block_slack_blocks` - verifies Slack blocks formatted correctly

3. **TestHandleQuestionUpdate** (lines 1111-1206)
   - `test_question_update_returns_update_action` - verifies `UpdateExistingMessage` with metadata
   - `test_question_update_without_message_id` - verifies fallback to `SendNewMessage`
   - `test_question_update_unknown_tool_use_id` - verifies `NoAction` for unknown questions

4. **TestMultipleQuestionsInBlock** (lines 1209-1248)
   - `test_multiple_questions_render_in_single_message` - verifies all questions in one message
   - `test_multiple_questions_slack_blocks` - verifies separate section blocks per question

5. **TestMultiSelectAnswerFormatting** (lines 1251-1291)
   - `test_multi_select_answer_formatting` - verifies comma-separated answers display correctly

6. **TestQuestionMessageIdTracking** (lines 1294-1351)
   - `test_record_telegram_question_message_id` - verifies Telegram ID recording
   - `test_record_slack_question_message_id` - verifies Slack ID recording
   - `test_get_question_message_id_unknown_question` - verifies None for unknown
   - `test_get_question_message_id_unknown_identifier` - verifies None for unknown identifier

7. **TestQuestionState** (lines 1354-1405)
   - `test_create_question_state` - verifies dataclass creation
   - `test_question_state_message_tracking` - verifies message tracking fields

## Test Results

- **Total tests in `test_message_state.py`**: 64 (17 new question tests)
- **Full test suite**: 1971 passed
- **No regressions**

## Definition of Done Checklist

- [x] Question blocks produce `SendNewMessage` action
- [x] Answered questions produce `UpdateExistingMessage` action
- [x] `tool_use_id` tracking works for questions
- [x] `remove_keyboard` metadata flag set on answer updates
- [x] All unit tests passing
- [x] No regressions in existing message state tests

## Design Decisions

1. **Separate tracking dict**: Questions use `state.questions` dict instead of reusing turn state, since questions are standalone events that don't belong to turns.

2. **Metadata for downstream**: Added `metadata` field to both `SendNewMessage` and `UpdateExistingMessage` to pass information needed by Telegram/Slack publishers (e.g., `remove_keyboard` flag).

3. **Fallback to SendNewMessage**: If `_render_question_update()` is called before message IDs are recorded, it returns `SendNewMessage` instead of failing silently.

4. **Format methods separate from publishers**: Text/block formatting is done in `MessageStateTracker` rather than delegating to publishers, keeping the tracker self-contained for formatting questions.
