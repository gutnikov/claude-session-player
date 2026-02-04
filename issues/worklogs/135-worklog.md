# Issue #135: Telegram: Question presentation with inline keyboard buttons

## Summary

Added inline keyboard buttons for question presentation in Telegram messages.
When Claude asks the user a question, Telegram now displays the options as
clickable buttons. Clicking a button shows a toast message directing the user
to respond in the CLI.

## Changes

### telegram_publisher.py

1. Added `MAX_QUESTION_BUTTONS = 5` constant to limit displayed options
2. Added `format_question_keyboard(content: QuestionContent) -> InlineKeyboardMarkup | None`:
   - Creates inline keyboard with option buttons
   - Returns None for answered questions (to remove keyboard)
   - Truncates labels longer than 30 characters
   - Limits to MAX_QUESTION_BUTTONS options
   - Callback data format: `q:{tool_use_id}:{question_idx}:{option_idx}`
3. Added `format_question_text(content: QuestionContent) -> str`:
   - Formats question with header, text, and options
   - Shows overflow message when more than 5 options exist
4. Extended `send_message()` to accept optional `reply_markup` parameter
5. Extended `edit_message()` to accept optional `reply_markup` parameter

### telegram_bot.py

1. Added `create_question_callback_handler() -> CallbackHandler`:
   - Handles `q:*` callback queries from button presses
   - Shows toast: "Please respond to this question in the Claude CLI"
   - Uses `show_alert=False` for non-blocking notification

### __init__.py

Exported new functions:
- `format_question_keyboard`
- `format_question_text`
- `MAX_QUESTION_BUTTONS`
- `create_question_callback_handler`

## Tests Added

### test_telegram_publisher.py

- `TestFormatQuestionKeyboard`:
  - `test_single_question_with_options` - basic keyboard creation
  - `test_truncates_at_max_buttons` - respects MAX_QUESTION_BUTTONS
  - `test_answered_question_returns_none` - no keyboard for answered
  - `test_truncates_long_labels` - label truncation at 30 chars
  - `test_empty_options_returns_none` - handles empty options

- `TestFormatQuestionText`:
  - `test_basic_question_text` - header, question, footer
  - `test_shows_overflow_message` - shows "N more options in CLI"
  - `test_singular_overflow_message` - singular "option" for 1 extra
  - `test_escapes_markdown_in_header` - markdown escaping
  - `test_default_header` - uses "Question" when header empty

- Tests for reply_markup parameter:
  - `test_send_message_with_reply_markup`
  - `test_edit_message_with_reply_markup`
  - `test_edit_message_remove_keyboard`

### test_telegram_bot.py

- `TestCreateQuestionCallbackHandler`:
  - `test_handler_answers_question_callback`
  - `test_handler_ignores_non_question_callbacks`
  - `test_handler_ignores_empty_callback_data`
  - `test_handler_ignores_empty_string_callback_data`

## Usage

The keyboard formatting is designed to be used by the service layer when
sending question messages:

```python
from claude_session_player.watcher import (
    format_question_keyboard,
    format_question_text,
)

# When sending a question message
content = QuestionContent(...)
text = format_question_text(content)
keyboard = format_question_keyboard(content)

await publisher.send_message(
    chat_id=chat_id,
    text=text,
    reply_markup=keyboard,
)

# When question is answered, remove keyboard
keyboard = format_question_keyboard(content_with_answers)  # Returns None
await publisher.edit_message(
    chat_id=chat_id,
    message_id=msg_id,
    text=updated_text,
    reply_markup=keyboard,  # None removes the keyboard
)
```

## Testing

All 175 watcher tests pass, including 27 new tests for question keyboard
functionality.
