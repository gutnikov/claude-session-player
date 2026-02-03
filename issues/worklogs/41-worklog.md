# Issue #41: Add Telegram Consumer

## Summary

Implemented a Telegram consumer that posts and updates messages in a Telegram chat or thread as events arrive from the session processor.

## Changes Made

### New Files

1. **`claude_session_player/telegram_consumer.py`**
   - `TelegramConsumer` class implementing the `Consumer` protocol
   - Chat ID and optional message_thread_id configuration
   - `_block_to_message_id` mapping for tracking posted messages (Telegram uses int IDs)
   - `AddBlock` -> `send_message`, stores message ID
   - `UpdateBlock` -> `edit_message_text` using stored ID (skips unknown block_id)
   - `ClearAll` -> ignored (no action)
   - Retry logic (1 retry, then skip with logging)
   - `render_block()` for Telegram message formatting with 4096 char limit
   - `from_env()` factory method for creating consumer with `TELEGRAM_BOT_TOKEN` from environment

2. **`tests/test_telegram_consumer.py`**
   - Tests for Consumer protocol compliance
   - Tests for AddBlock sending messages
   - Tests for UpdateBlock editing messages
   - Tests for unknown block_id being skipped
   - Tests for ClearAll being ignored
   - Tests for retry logic (retry once, then skip)
   - Tests for 4096 char limit truncation
   - Tests for from_env factory method
   - Tests for multiple events
   - All tests with mocked Telegram API
   - 33 test cases

### Modified Files

1. **`pyproject.toml`**
   - Added `telegram` optional dependency group with `python-telegram-bot>=21.0`

2. **`.env.example`**
   - Added template for `TELEGRAM_BOT_TOKEN=123456:ABC-your-token`

## Technical Details

### TelegramConsumer

```python
class TelegramConsumer:
    def __init__(self, bot: Bot, chat_id: int | str, message_thread_id: int | None = None)
    @classmethod
    def from_env(cls, chat_id: int | str, message_thread_id: int | None = None) -> TelegramConsumer
    async def on_event(self, event: Event) -> None
    def render_block(self, block: Block) -> str
```

- Uses `telegram.Bot` from python-telegram-bot for async Telegram API calls
- Sends messages with `send_message` and edits with `edit_message_text`
- Tracks message IDs in `_block_to_message_id` mapping (int type, not string)
- Respects Telegram's 4096 character message limit with truncation
- Retry logic: 1 retry with configurable delay, then skip with logging
- Supports both numeric chat IDs and channel usernames (e.g., "@channelname")

### Message Rendering

Each block type is rendered for plain text (Telegram supports basic formatting):
- User: `User:` + text
- Assistant: `Claude:` + text
- Tool call: `tool_name(label)`, with `[OK]`/`[ERROR]`/`[...]` prefixes for result/error/progress
- Thinking: `Thinking...`
- Duration: `Crunched for X`
- Question: `[?]` with options and `[OK]` for answers
- System: Code block

### Error Handling

- API failures trigger 1 retry with configurable delay (default 1s)
- After retry fails, operation is skipped with error logging
- Unknown block_id in UpdateBlock is skipped silently (debug logged)
- ClearAll is ignored (Telegram messages are not deleted)

## Test Coverage

All 408 tests pass:
- 33 new tests in `test_telegram_consumer.py`
- All existing tests continue to pass

## Acceptance Criteria Status

- [x] `TelegramConsumer` implements the `Consumer` protocol
- [x] Messages sent to configured chat/thread
- [x] Messages edited when `UpdateBlock` received
- [x] Retry logic implemented (1 retry, then skip)
- [x] `.env.example` updated with `TELEGRAM_BOT_TOKEN`
- [x] `python-telegram-bot` added to dependencies
- [x] Unit tests with mocked Telegram API
