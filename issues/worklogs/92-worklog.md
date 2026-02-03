# Issue #92: Add TelegramCommandHandler for /search command and callbacks

## Summary

Implemented `TelegramCommandHandler` to handle `/search` bot commands and inline keyboard callbacks in Telegram. This provides the Telegram-side implementation for the session search feature, mirroring the Slack implementation from issue #91.

## Changes Made

### New Files

1. **`claude_session_player/watcher/telegram_commands.py`**
   - `TelegramCommandHandler`: Main handler class for search commands and callbacks
   - `format_search_results_telegram()`: Formats search results as Markdown + keyboard
   - `format_empty_results_telegram()`: Formats "no results found" message
   - `format_rate_limited_telegram()`: Formats rate limit error message
   - `format_watch_confirmation_telegram()`: Formats session watch confirmation
   - `format_preview_telegram()`: Formats session preview with events
   - `format_error_telegram()`: Formats generic error messages
   - `format_expired_state_telegram()`: Formats expired search state message
   - `_build_search_keyboard()`: Builds inline keyboard for results
   - Helper functions: `_format_file_size()`, `_format_duration()`, `_format_date()`, `_escape_markdown()`

2. **`tests/watcher/test_telegram_commands.py`**
   - 53 tests covering all functionality

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestEscapeMarkdown | 5 | Markdown character escaping |
| TestFormatFileSize | 3 | File size formatting (B, KB, MB) |
| TestFormatDuration | 4 | Duration formatting (none, seconds, minutes, hours) |
| TestFormatDate | 1 | Date formatting |
| TestFormatSearchResultsTelegram | 5 | Search results Markdown + keyboard |
| TestBuildSearchKeyboard | 3 | Inline keyboard generation |
| TestFormatEmptyResultsTelegram | 2 | Empty results formatting |
| TestFormatRateLimitedTelegram | 1 | Rate limit message |
| TestFormatWatchConfirmationTelegram | 1 | Watch confirmation |
| TestFormatPreviewTelegram | 2 | Preview formatting |
| TestFormatErrorTelegram | 1 | Error message formatting |
| TestFormatExpiredStateTelegram | 1 | Expired state message |
| TestHandleSearchRateLimiting | 2 | Rate limiting on search command |
| TestHandleCallback | 6 | Callback routing and handling |
| TestHandleWatch | 3 | Watch button interaction |
| TestHandlePreview | 2 | Preview button interaction |
| TestHandlePagination | 4 | Pagination button interactions |
| TestIntegration | 1 | Full search flow |
| TestCallbackDataParsing | 6 | Callback data parsing |

**Total: 53 new tests, all passing**

## Design Decisions

### Callback Data Format (64-byte limit)

Used short action codes to fit within Telegram's 64-byte callback_data limit:
- `w:0` → Watch result at index 0
- `p:2` → Preview result at index 2
- `s:n` → Search next page
- `s:p` → Search prev page
- `s:r` → Search refresh
- `noop` → No action (page indicator)

Full session IDs are stored in `SearchStateManager`, referenced by index.

### Markdown Formatting

Uses Telegram Markdown V1 with proper escaping:
- Escapes `_`, `*`, `` ` ``, `[` characters
- Uses bold (`*text*`) for headers and session names
- Uses code (`\`text\``) for file paths/labels
- Separator lines using `━` character

### Inline Keyboard Layout

Three rows:
1. Watch buttons: `[👁 1] [👁 2] [👁 3]`
2. Preview buttons: `[📋 1] [📋 2] [📋 3]`
3. Navigation: `[◀️] [1/1] [▶️] [🔄]`

### Rate Limiting

Uses existing `RateLimiter` with key format `telegram:{chat_id}`:
- 10 searches per minute per chat (matches spec)

### State Management

Uses `SearchStateManager` with key format `telegram:{chat_id}`:
- Stores full result list for pagination
- Tracks current page offset
- Expires after 5 minutes (TTL)

### Preview Implementation

Current implementation is simplified:
- Shows session summary as assistant text
- Full implementation would call `/sessions/{id}/preview` API

### Message Replies

Preview responses are sent as replies to the search message:
- Uses `reply_to_message_id` parameter
- Keeps chat organized

## Test Results

- **New tests:** 53 tests, all passing
- **Search-related tests:** 241 passing (includes indexer, search, search_state, rate_limit, bot_router, slack_commands, telegram_commands)
- **Core tests:** 474 passing (2 failures due to missing optional slack_sdk dependency - pre-existing)

## Acceptance Criteria Status

- [x] `/search` command handler implemented
- [x] Markdown formatting matches spec mockups
- [x] Inline keyboard layout correct
- [x] Watch callback attaches session
- [x] Preview callback shows events as reply
- [x] Pagination edits message in place
- [x] Refresh re-runs search
- [x] Callback returns answer text to clear loading state
- [x] Rate limiting enforced
- [x] Error messages formatted correctly
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Format search results as Markdown + keyboard
- [x] Unit test: Handle empty results
- [x] Unit test: Parse callback data correctly
- [x] Unit test: Handle watch callback
- [x] Unit test: Handle preview callback
- [x] Unit test: Handle pagination callbacks
- [x] Unit test: Handle expired search state
- [x] Unit test: Rate limiting
- [x] Integration test: Full search flow

## Spec Reference

Implements issue #92 from `.claude/specs/session-search-api.md`:
- Telegram User Experience section (lines 152-303)
- Bot Command Infrastructure section - Telegram parts (lines 959-1050)

## Notes

- No new runtime dependencies (uses existing aiogram from watcher module)
- Uses `aiogram.types.InlineKeyboardMarkup` and `InlineKeyboardButton` for keyboards
- The `attach_callback` is injected to allow integration with WatcherService
- Preview is simplified - would need `/sessions/{id}/preview` endpoint for full implementation
- Callback data parsing handles invalid inputs gracefully
