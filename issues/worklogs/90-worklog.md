# Issue #90: Add BotRouter for Slack/Telegram webhook routing

## Summary

Implemented `BotRouter` component that receives incoming webhooks from Slack and Telegram and routes them to appropriate handlers. Includes Slack signature verification (HMAC-SHA256) and Telegram webhook parsing.

## Changes Made

### New Files

1. **`claude_session_player/watcher/bot_router.py`**
   - `verify_slack_signature()`: Verifies Slack request signatures using HMAC-SHA256
   - `BotRouter`: Routes incoming webhooks to registered handlers
   - `register_bot_routes()`: Registers webhook routes on aiohttp application
   - `_parse_form_data()`: Parses URL-encoded form data
   - Type aliases for handler signatures

2. **`tests/watcher/test_bot_router.py`**
   - 40 tests covering all functionality

### Modified Files

1. **`claude_session_player/watcher/config.py`**
   - Added `slack_signing_secret` field to `BotConfig` dataclass
   - Updated `to_dict()` and `from_dict()` methods for serialization

## Test Coverage

| Test Class | Count | Coverage |
|------------|-------|----------|
| TestVerifySlackSignatureValid | 2 | Valid signature verification |
| TestVerifySlackSignatureInvalid | 3 | Invalid signature detection |
| TestVerifySlackSignatureExpiredTimestamp | 3 | Timestamp validation (5 min window) |
| TestVerifySlackSignatureMissingFields | 4 | Missing headers handling |
| TestSlackCommandRouting | 3 | Slash command routing |
| TestSlackCommandSignatureVerification | 3 | Signature verification in handlers |
| TestSlackInteractionRouting | 3 | Button click/menu selection routing |
| TestTelegramMessageCommandRouting | 4 | Message command routing |
| TestTelegramCallbackQueryRouting | 3 | Callback query routing |
| TestTelegramInvalidPayload | 2 | Invalid payload handling |
| TestParseFormData | 3 | URL-encoded form parsing |
| TestRegisterBotRoutes | 1 | Route registration |
| TestHandlerErrorHandling | 3 | Exception handling in handlers |
| TestHandlerRegistration | 3 | Handler registration methods |

**Total: 40 new tests, all passing**

## Design Decisions

### Slack Signature Verification

Implemented exactly per Slack API documentation:
```python
def verify_slack_signature(body, timestamp, signature, signing_secret):
    # 1. Check timestamp is within 5 minutes
    # 2. Compute HMAC-SHA256 of "v0:{timestamp}:{body}"
    # 3. Constant-time comparison to prevent timing attacks
```

### Handler Registration Pattern

Used prefix-based matching for interactions and callbacks:
- Slack: `action_id.startswith(prefix)` for "watch:", "preview:", etc.
- Telegram: `callback_data.startswith(prefix)` for "w:", "p:", "s:", etc.

This allows registering handlers like:
```python
router.register_slack_interaction("watch:", handle_watch)
router.register_telegram_callback("w:", handle_watch)
```

### Error Handling

Both Slack and Telegram expect 200 OK even on handler errors:
- Slack: Returns 200 to acknowledge, actual response via response_url
- Telegram: Returns 200 always to prevent retry storms

Handler exceptions are logged but don't propagate to HTTP response.

### Type Aliases

Used `Optional[]` syntax instead of `| None` for Python 3.9 compatibility in type aliases that are evaluated at runtime:
```python
SlackCommandHandler = Callable[
    [str, str, str, str, str], Awaitable[Optional[dict[str, Any]]]
]
```

### Form Data Parsing

Created custom `_parse_form_data()` because we read the body for signature verification before aiohttp can parse it:
```python
body = await request.read()  # For signature verification
form_data = _parse_form_data(body.decode("utf-8"))  # Manual parsing
```

## Test Results

- **New tests:** 40 tests, all passing
- **Search-related tests:** 283 passing (indexer + search + search_state + rate_limit + bot_router + config)
- **Core tests:** 474 passing (2 failures due to missing optional slack_sdk dependency - pre-existing)

## Acceptance Criteria Status

- [x] Slack signature verification working
- [x] Slack commands routed to handlers
- [x] Slack interactions routed to handlers
- [x] Telegram webhook parses updates
- [x] Telegram commands routed to handlers
- [x] Telegram callbacks routed to handlers
- [x] 401 returned for invalid signatures
- [x] All tests passing

## Test Requirements Status (from issue)

- [x] Unit test: Slack signature verification (valid)
- [x] Unit test: Slack signature verification (invalid)
- [x] Unit test: Slack signature verification (expired timestamp)
- [x] Unit test: Route /search command correctly
- [x] Unit test: Route button interaction correctly
- [x] Unit test: Telegram webhook parses message command
- [x] Unit test: Telegram webhook parses callback query

## Spec Reference

Implements issue #90 from `.claude/specs/session-search-api.md`:
- Bot Command Infrastructure section (lines 854-1050)
- Slack slash commands endpoint
- Slack interactions endpoint
- Telegram webhook endpoint
- Signature verification

## Notes

- No external runtime dependencies added (stdlib only for signature verification)
- Uses `hmac.compare_digest()` for constant-time signature comparison (prevents timing attacks)
- Handler registration is flexible with prefix matching for action routing
- Telegram has no built-in signature verification; security via secret webhook URL path
