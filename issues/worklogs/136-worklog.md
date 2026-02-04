# Issue #136: Slack: Question presentation with Block Kit action buttons

## Summary

Added Block Kit action buttons for question presentation in Slack messages.
When Claude asks the user a question, Slack now displays the options as
clickable buttons. Clicking a button shows an ephemeral message directing
the user to respond in the CLI.

## Changes

### slack_publisher.py

1. Added `MAX_QUESTION_BUTTONS = 5` constant to limit displayed options
2. Added `format_question_blocks(content: QuestionContent) -> list[dict]`:
   - Creates Block Kit blocks with section + actions + context
   - Each question gets a section with header and text
   - Actions block contains button elements for each option
   - Overflow context shows "N more options in CLI" when truncated
   - Dividers between multiple questions (not after last)
   - Final context prompts "respond in CLI"
   - Button action_id format: `question_opt_{q_idx}_{opt_idx}`
   - Button value format: `{tool_use_id}:{q_idx}:{opt_idx}`
   - Actions block_id format: `q_{tool_use_id}_{q_idx}`
   - Truncates labels longer than 30 characters
3. Added `format_answered_question_blocks(content: QuestionContent) -> list[dict]`:
   - Shows question header and text
   - Displays selected answer with checkmark emoji
   - No actions block (buttons removed)
4. Added TYPE_CHECKING import for QuestionContent type hint

### slack_commands.py

1. Added `handle_question_button_interaction()` method:
   - Handles button clicks from question action buttons
   - Sends ephemeral message: "Please respond to this question in the Claude Code CLI"
   - Uses existing `_respond_ephemeral()` helper

### message_state.py

1. Updated imports to include new formatters from slack_publisher
2. Updated `_format_question_blocks()` to delegate to `format_question_blocks()`
3. Updated `_format_answered_question_blocks()` to delegate to `format_answered_question_blocks()`

### __init__.py

Exported new functions:
- `format_question_blocks`
- `format_answered_question_blocks`
- `SLACK_MAX_QUESTION_BUTTONS`

## Block Structure

### Unanswered Question
```python
[
    {"type": "section", "text": {"type": "mrkdwn", "text": ":question: *{header}*\n{question}"}},
    {"type": "actions", "block_id": "q_{tool_use_id}_{i}", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "{label}"},
         "action_id": "question_opt_{i}_{j}", "value": "{tool_use_id}:{i}:{j}"},
        # ... up to 5 buttons
    ]},
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_and {N} more options in CLI_"}]},  # if >5
    {"type": "divider"},  # between questions
    {"type": "context", "elements": [{"type": "mrkdwn", "text": "_respond in CLI_"}]}
]
```

### Answered Question
```python
[
    {"type": "section", "text": {"type": "mrkdwn", "text": ":question: *{header}*\n{question}"}},
    {"type": "section", "text": {"type": "mrkdwn", "text": ":white_check_mark: Selected: _{answer}_"}}
]
```

## Tests Added

### test_slack_publisher.py

- `TestFormatQuestionBlocksStructure`:
  - `test_single_question_produces_section_actions_context` - basic block structure
  - `test_button_action_ids_and_values` - correct action_id and value format
  - `test_actions_block_id_format` - correct block_id format
  - `test_escapes_mrkdwn_in_header_and_question` - mrkdwn escaping

- `TestFormatQuestionBlocksTruncation`:
  - `test_truncates_at_max_buttons` - respects MAX_QUESTION_BUTTONS
  - `test_exactly_max_buttons_no_overflow` - no overflow at exact limit
  - `test_truncates_long_button_labels` - label truncation at 30 chars
  - `test_overflow_singular_option` - singular "option" for 1 extra

- `TestFormatQuestionBlocksMultipleQuestions`:
  - `test_multiple_questions_separated_by_dividers` - dividers between questions
  - `test_three_questions_two_dividers` - correct divider count
  - `test_multiple_questions_button_indices` - indices scoped per question

- `TestFormatAnsweredQuestionBlocks`:
  - `test_answered_question_shows_selection` - checkmark and answer display
  - `test_answered_question_no_actions_block` - no buttons for answered
  - `test_answered_question_escapes_answer` - answer text escaping
  - `test_answered_question_no_answer_in_dict` - handles missing answer
  - `test_answered_question_multiple_questions` - multiple answers
  - `test_answered_question_uses_question_header_default` - default header

## Testing

All 2005 tests pass, including 17 new tests for Slack question block formatting.

```bash
uv run pytest tests/watcher/test_slack_publisher.py -xvs  # 74 passed
uv run pytest -x  # 2005 passed
```
