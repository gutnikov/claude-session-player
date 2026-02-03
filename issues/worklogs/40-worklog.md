# Issue #40: Add Slack Consumer

## Summary

Implemented a Slack consumer that posts and updates messages in a Slack channel or thread as events arrive from the session processor.

## Changes Made

### New Files

1. **`claude_session_player/slack_consumer.py`**
   - `SlackConsumer` class implementing the `Consumer` protocol
   - Channel ID and optional thread_ts configuration
   - `_block_to_message_ts` mapping for tracking posted messages
   - `AddBlock` -> `chat.postMessage`, stores message timestamp
   - `UpdateBlock` -> `chat.update` using stored timestamp (skips unknown block_id)
   - `ClearAll` -> ignored (no action)
   - Retry logic (1 retry, then skip with logging)
   - `render_block()` for Slack message formatting with 4000 char limit
   - `from_env()` factory method for creating consumer with `SLACK_BOT_TOKEN` from environment

2. **`tests/test_slack_consumer.py`**
   - Tests for Consumer protocol compliance
   - Tests for AddBlock posting messages
   - Tests for UpdateBlock updating messages
   - Tests for unknown block_id being skipped
   - Tests for ClearAll being ignored
   - Tests for retry logic (retry once, then skip)
   - Tests for 4000 char limit truncation
   - Tests for from_env factory method
   - Tests for multiple events
   - All tests with mocked Slack API
   - 32 test cases

3. **`.env.example`**
   - Template for `SLACK_BOT_TOKEN=xoxb-your-token`

### Modified Files

1. **`pyproject.toml`**
   - Added `pytest-asyncio` to dev dependencies
   - Added `slack` optional dependency group with `slack-sdk>=3.0` and `aiohttp>=3.0`

## Technical Details

### SlackConsumer

```python
class SlackConsumer:
    def __init__(self, client: AsyncWebClient, channel: str, thread_ts: str | None = None)
    @classmethod
    def from_env(cls, channel: str, thread_ts: str | None = None) -> SlackConsumer
    async def on_event(self, event: Event) -> None
    def render_block(self, block: Block) -> str
```

- Uses `slack_sdk.web.async_client.AsyncWebClient` for async Slack API calls
- Posts messages with `chat.postMessage` and updates with `chat.update`
- Tracks message timestamps in `_block_to_message_ts` mapping
- Respects Slack's 4000 character message limit with truncation
- Retry logic: 1 retry with configurable delay, then skip with logging

### Message Rendering

Each block type is rendered for Slack formatting:
- User: `:bust_in_silhouette: *User:*` + text
- Assistant: `:robot_face: *Claude:*` + text
- Tool call: `:wrench:` + tool name + label, with result/progress
- Thinking: `:brain: _Thinking..._`
- Duration: `:stopwatch: Crunched for X`
- Question: `:question:` with options and answers
- System: Code block

### Error Handling

- API failures trigger 1 retry with configurable delay (default 1s)
- After retry fails, operation is skipped with error logging
- Unknown block_id in UpdateBlock is skipped silently (debug logged)
- ClearAll is ignored (Slack messages are not deleted)

## Test Coverage

All 375 tests pass:
- 32 new tests in `test_slack_consumer.py`
- All existing tests continue to pass

## Acceptance Criteria Status

- [x] `SlackConsumer` implements the `Consumer` protocol
- [x] Messages posted to configured channel/thread
- [x] Messages updated when `UpdateBlock` received
- [x] Retry logic implemented (1 retry, then skip)
- [x] `.env.example` created with `SLACK_BOT_TOKEN`
- [x] `slack-sdk` added to dependencies
- [x] Unit tests with mocked Slack API
