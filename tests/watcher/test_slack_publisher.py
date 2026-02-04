"""Tests for SlackPublisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from slack_sdk.errors import SlackApiError

from claude_session_player.events import Question, QuestionContent, QuestionOption
from claude_session_player.watcher.slack_publisher import (
    MAX_QUESTION_BUTTONS,
    SlackAuthError,
    SlackError,
    SlackPublisher,
    _build_ttl_controls_block,
    _truncate_blocks,
    _wrap_in_code_block,
    escape_mrkdwn,
    format_answered_question_blocks,
    format_question_blocks,
)


def make_slack_api_error(message: str) -> SlackApiError:
    """Create a SlackApiError for testing.

    Args:
        message: Error message.

    Returns:
        SlackApiError instance.
    """
    response = MagicMock()
    response.status_code = 400
    response.data = {"ok": False, "error": message}
    return SlackApiError(message=message, response=response)


# ---------------------------------------------------------------------------
# mrkdwn escaping tests
# ---------------------------------------------------------------------------


class TestEscapeMrkdwn:
    """Tests for escape_mrkdwn function."""

    def test_escapes_ampersand(self) -> None:
        """Ampersands are escaped."""
        assert escape_mrkdwn("hello & world") == "hello &amp; world"

    def test_escapes_less_than(self) -> None:
        """Less-than signs are escaped."""
        assert escape_mrkdwn("hello < world") == "hello &lt; world"

    def test_escapes_greater_than(self) -> None:
        """Greater-than signs are escaped."""
        assert escape_mrkdwn("hello > world") == "hello &gt; world"

    def test_escapes_multiple_chars(self) -> None:
        """Multiple special chars are escaped."""
        assert escape_mrkdwn("<&>") == "&lt;&amp;&gt;"

    def test_preserves_normal_text(self) -> None:
        """Normal text is preserved."""
        assert escape_mrkdwn("hello world") == "hello world"

    def test_empty_string(self) -> None:
        """Empty string returns empty."""
        assert escape_mrkdwn("") == ""

    def test_correct_escape_order(self) -> None:
        """Ampersand is escaped first to avoid double-escaping."""
        # If & is escaped first: & -> &amp;
        # If < is escaped first: < -> &lt;, then & -> &amp; would make it &amp;lt;
        result = escape_mrkdwn("a & b < c > d")
        assert result == "a &amp; b &lt; c &gt; d"


# ---------------------------------------------------------------------------
# Block truncation tests
# ---------------------------------------------------------------------------


class TestTruncateBlocks:
    """Tests for _truncate_blocks function."""

    def test_short_blocks_unchanged(self) -> None:
        """Short block lists are not truncated."""
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}] * 10
        result = _truncate_blocks(blocks)
        assert result == blocks
        assert len(result) == 10

    def test_truncates_long_blocks(self) -> None:
        """Long block lists are truncated."""
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(60)]
        result = _truncate_blocks(blocks)
        assert len(result) == 50
        # Last block should be truncation indicator
        assert "truncated" in result[-1]["text"]["text"]

    def test_exact_limit_unchanged(self) -> None:
        """Block list at exact limit is not truncated."""
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(50)]
        result = _truncate_blocks(blocks)
        assert len(result) == 50
        assert result == blocks

    def test_custom_max_blocks(self) -> None:
        """Custom max_blocks is respected."""
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(20)]
        result = _truncate_blocks(blocks, max_blocks=10)
        assert len(result) == 10
        assert "truncated" in result[-1]["text"]["text"]


# ---------------------------------------------------------------------------
# Code block wrapping tests
# ---------------------------------------------------------------------------


class TestWrapInCodeBlock:
    """Tests for _wrap_in_code_block function."""

    def test_wraps_content_in_code_block(self) -> None:
        """Wraps content in triple backticks."""
        result = _wrap_in_code_block("Hello World")
        assert len(result) == 1
        assert result[0]["type"] == "section"
        assert result[0]["text"]["type"] == "mrkdwn"
        assert result[0]["text"]["text"] == "```Hello World```"

    def test_wraps_multiline_content(self) -> None:
        """Wraps multiline content correctly."""
        content = "Line 1\nLine 2\nLine 3"
        result = _wrap_in_code_block(content)
        assert result[0]["text"]["text"] == f"```{content}```"

    def test_wraps_empty_content(self) -> None:
        """Wraps empty string."""
        result = _wrap_in_code_block("")
        assert result[0]["text"]["text"] == "``````"

    def test_wraps_content_with_special_chars(self) -> None:
        """Wraps content with special characters."""
        content = "<pre> & stuff > here"
        result = _wrap_in_code_block(content)
        # Content is NOT escaped when wrapped in code block
        assert result[0]["text"]["text"] == f"```{content}```"

    def test_wraps_content_with_ttl_controls_is_live(self) -> None:
        """Adds TTL controls when message_ts provided and is_live=True."""
        result = _wrap_in_code_block("content", message_ts="1234567890.123456", is_live=True)

        assert len(result) == 2
        assert result[0]["type"] == "section"
        assert result[1]["type"] == "actions"
        assert result[1]["block_id"] == "ttl_controls"

        elements = result[1]["elements"]
        assert len(elements) == 2

        # Live indicator button
        assert elements[0]["action_id"] == "ttl_live_indicator"
        assert elements[0]["style"] == "primary"
        assert "\u26a1 Live" in elements[0]["text"]["text"]

        # +30s button
        assert elements[1]["action_id"] == "extend_ttl"
        assert elements[1]["value"] == "1234567890.123456"
        assert elements[1]["text"]["text"] == "+30s"

    def test_wraps_content_with_ttl_controls_not_live(self) -> None:
        """Adds only +30s button when is_live=False."""
        result = _wrap_in_code_block("content", message_ts="1234567890.123456", is_live=False)

        assert len(result) == 2
        elements = result[1]["elements"]
        assert len(elements) == 1

        # Only +30s button, no live indicator
        assert elements[0]["action_id"] == "extend_ttl"
        assert elements[0]["value"] == "1234567890.123456"

    def test_wraps_content_no_ttl_controls_by_default(self) -> None:
        """No TTL controls when message_ts is None."""
        result = _wrap_in_code_block("content")
        assert len(result) == 1
        assert result[0]["type"] == "section"

    def test_wraps_content_is_live_ignored_without_message_ts(self) -> None:
        """is_live parameter is ignored when message_ts is None."""
        result = _wrap_in_code_block("content", is_live=False)
        assert len(result) == 1
        assert result[0]["type"] == "section"


# ---------------------------------------------------------------------------
# TTL controls block tests
# ---------------------------------------------------------------------------


class TestBuildTtlControlsBlock:
    """Tests for _build_ttl_controls_block function."""

    def test_builds_block_with_live_indicator(self) -> None:
        """Builds actions block with live indicator when is_live=True."""
        block = _build_ttl_controls_block("1234567890.123456", is_live=True)

        assert block["type"] == "actions"
        assert block["block_id"] == "ttl_controls"
        assert len(block["elements"]) == 2

        # First element: live indicator
        live_btn = block["elements"][0]
        assert live_btn["type"] == "button"
        assert live_btn["action_id"] == "ttl_live_indicator"
        assert live_btn["style"] == "primary"
        assert live_btn["text"]["type"] == "plain_text"
        assert live_btn["text"]["emoji"] is True

        # Second element: +30s button
        extend_btn = block["elements"][1]
        assert extend_btn["type"] == "button"
        assert extend_btn["action_id"] == "extend_ttl"
        assert extend_btn["value"] == "1234567890.123456"

    def test_builds_block_without_live_indicator(self) -> None:
        """Builds actions block without live indicator when is_live=False."""
        block = _build_ttl_controls_block("1234567890.123456", is_live=False)

        assert len(block["elements"]) == 1

        # Only +30s button
        extend_btn = block["elements"][0]
        assert extend_btn["action_id"] == "extend_ttl"
        assert extend_btn["value"] == "1234567890.123456"

    def test_button_values_match_message_ts(self) -> None:
        """Button value contains the exact message_ts for lookup."""
        ts = "9999999999.999999"
        block = _build_ttl_controls_block(ts, is_live=True)

        extend_btn = block["elements"][1]
        assert extend_btn["value"] == ts

    def test_button_text_has_emoji_flag(self) -> None:
        """Both buttons have emoji flag set."""
        block = _build_ttl_controls_block("123.456", is_live=True)

        for element in block["elements"]:
            assert element["text"]["emoji"] is True


# ---------------------------------------------------------------------------
# SlackPublisher tests
# ---------------------------------------------------------------------------


class TestSlackPublisherInit:
    """Tests for SlackPublisher initialization."""

    def test_init_with_token(self) -> None:
        """Initializes with token."""
        publisher = SlackPublisher(token="xoxb-test-token")
        assert publisher._token == "xoxb-test-token"
        assert publisher._validated is False
        assert publisher._client is None

    def test_init_without_token(self) -> None:
        """Initializes without token."""
        publisher = SlackPublisher()
        assert publisher._token is None
        assert publisher._validated is False


class TestSlackPublisherValidate:
    """Tests for SlackPublisher.validate()."""

    @pytest.mark.asyncio
    async def test_validate_without_token_raises(self) -> None:
        """Validation fails without token."""
        publisher = SlackPublisher(token=None)
        with pytest.raises(ValueError, match="token not configured"):
            await publisher.validate()

    @pytest.mark.asyncio
    async def test_validate_skips_if_already_validated(self) -> None:
        """Skips validation if already validated."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._validated = True

        # Should not raise or call any external code
        await publisher.validate()
        assert publisher._validated is True

    @pytest.mark.asyncio
    async def test_validate_success(self) -> None:
        """Successful validation sets _validated flag."""
        publisher = SlackPublisher(token="xoxb-test-token")

        mock_client = MagicMock()
        mock_client.auth_test = AsyncMock(
            return_value={"ok": True, "user": "test_bot", "team": "test_team"}
        )

        with patch("claude_session_player.watcher.slack_publisher.check_slack_available", return_value=True):
            with patch(
                "slack_sdk.web.async_client.AsyncWebClient", return_value=mock_client
            ):
                await publisher.validate()

        assert publisher._validated is True
        assert publisher._client is mock_client

    @pytest.mark.asyncio
    async def test_validate_auth_failure_not_ok(self) -> None:
        """Auth failure raises SlackAuthError when ok is False."""
        publisher = SlackPublisher(token="xoxb-invalid-token")

        mock_client = MagicMock()
        mock_client.auth_test = AsyncMock(
            return_value={"ok": False, "error": "invalid_auth"}
        )

        with patch("claude_session_player.watcher.slack_publisher.check_slack_available", return_value=True):
            with patch(
                "slack_sdk.web.async_client.AsyncWebClient", return_value=mock_client
            ):
                with pytest.raises(SlackAuthError, match="Auth test failed"):
                    await publisher.validate()

    @pytest.mark.asyncio
    async def test_validate_auth_failure_exception(self) -> None:
        """Auth failure raises SlackAuthError on SlackApiError."""
        publisher = SlackPublisher(token="xoxb-invalid-token")

        mock_client = MagicMock()
        mock_client.auth_test = AsyncMock(
            side_effect=make_slack_api_error("invalid_auth")
        )

        with patch("claude_session_player.watcher.slack_publisher.check_slack_available", return_value=True):
            with patch(
                "slack_sdk.web.async_client.AsyncWebClient", return_value=mock_client
            ):
                with pytest.raises(SlackAuthError, match="validation failed"):
                    await publisher.validate()

    @pytest.mark.asyncio
    async def test_validate_slack_sdk_not_installed(self) -> None:
        """Raises SlackError if slack-sdk not installed."""
        publisher = SlackPublisher(token="xoxb-test-token")

        with patch("claude_session_player.watcher.slack_publisher.check_slack_available", return_value=False):
            with pytest.raises(SlackError, match="slack-sdk library not installed"):
                await publisher.validate()


class TestSlackPublisherSendMessage:
    """Tests for SlackPublisher.send_message()."""

    @pytest.fixture
    def validated_publisher(self) -> SlackPublisher:
        """Create a pre-validated publisher with mock client."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._validated = True
        publisher._client = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_send_message_success(self, validated_publisher: SlackPublisher) -> None:
        """Successfully sends message."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        ts = await validated_publisher.send_message(
            channel="C0123456789",
            text="Hello world",
        )

        assert ts == "1234567890.123456"
        validated_publisher._client.chat_postMessage.assert_called_once_with(
            channel="C0123456789",
            text="Hello world",
            blocks=None,
        )

    @pytest.mark.asyncio
    async def test_send_message_with_blocks(self, validated_publisher: SlackPublisher) -> None:
        """Sends message with blocks."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}]
        ts = await validated_publisher.send_message(
            channel="C0123456789",
            text="Hello world",
            blocks=blocks,
        )

        assert ts == "1234567890.123456"
        call_args = validated_publisher._client.chat_postMessage.call_args
        assert call_args.kwargs["blocks"] == blocks

    @pytest.mark.asyncio
    async def test_send_message_truncates_blocks(self, validated_publisher: SlackPublisher) -> None:
        """Truncates blocks exceeding limit."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(60)]
        await validated_publisher.send_message(
            channel="C0123456789",
            text="Hello world",
            blocks=blocks,
        )

        call_args = validated_publisher._client.chat_postMessage.call_args
        sent_blocks = call_args.kwargs["blocks"]
        assert len(sent_blocks) == 50
        assert "truncated" in sent_blocks[-1]["text"]["text"]

    @pytest.mark.asyncio
    async def test_send_message_retry_on_failure(self, validated_publisher: SlackPublisher) -> None:
        """Retries once on API failure."""
        # First call fails, second succeeds
        validated_publisher._client.chat_postMessage = AsyncMock(
            side_effect=[
                make_slack_api_error("rate_limited"),
                {"ok": True, "ts": "1234567890.123456"},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            ts = await validated_publisher.send_message(
                channel="C0123456789",
                text="Hello",
            )

        assert ts == "1234567890.123456"
        assert validated_publisher._client.chat_postMessage.call_count == 2

    @pytest.mark.asyncio
    async def test_send_message_raises_after_retry_fails(self, validated_publisher: SlackPublisher) -> None:
        """Raises SlackError after retry fails."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            side_effect=make_slack_api_error("channel_not_found")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(SlackError, match="Post failed"):
                await validated_publisher.send_message(
                    channel="C0123456789",
                    text="Hello",
                )

    @pytest.mark.asyncio
    async def test_send_message_validates_first(self) -> None:
        """Validates before sending if not validated."""
        publisher = SlackPublisher(token="xoxb-test-token")

        mock_client = MagicMock()
        mock_client.auth_test = AsyncMock(
            return_value={"ok": True, "user": "test_bot", "team": "test_team"}
        )
        mock_client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        with patch("claude_session_player.watcher.slack_publisher.check_slack_available", return_value=True):
            with patch("slack_sdk.web.async_client.AsyncWebClient", return_value=mock_client):
                ts = await publisher.send_message(
                    channel="C0123456789",
                    text="Hello",
                )

        assert ts == "1234567890.123456"
        assert publisher._validated is True


class TestSlackPublisherUpdateMessage:
    """Tests for SlackPublisher.update_message()."""

    @pytest.fixture
    def validated_publisher(self) -> SlackPublisher:
        """Create a pre-validated publisher with mock client."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._validated = True
        publisher._client = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_update_message_success(self, validated_publisher: SlackPublisher) -> None:
        """Successfully updates message."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        result = await validated_publisher.update_message(
            channel="C0123456789",
            ts="1234567890.123456",
            text="Updated text",
        )

        assert result is True
        validated_publisher._client.chat_update.assert_called_once_with(
            channel="C0123456789",
            ts="1234567890.123456",
            text="Updated text",
            blocks=None,
        )

    @pytest.mark.asyncio
    async def test_update_message_with_blocks(self, validated_publisher: SlackPublisher) -> None:
        """Updates message with blocks."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Updated"}}]
        result = await validated_publisher.update_message(
            channel="C0123456789",
            ts="1234567890.123456",
            text="Updated text",
            blocks=blocks,
        )

        assert result is True
        call_args = validated_publisher._client.chat_update.call_args
        assert call_args.kwargs["blocks"] == blocks

    @pytest.mark.asyncio
    async def test_update_message_not_found_returns_false(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """Returns False when message not found."""
        validated_publisher._client.chat_update = AsyncMock(
            side_effect=make_slack_api_error("message_not_found")
        )

        result = await validated_publisher.update_message(
            channel="C0123456789",
            ts="1234567890.123456",
            text="Updated text",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_message_retry_on_failure(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """Retries once on API failure."""
        # First call fails, second succeeds
        validated_publisher._client.chat_update = AsyncMock(
            side_effect=[
                make_slack_api_error("rate_limited"),
                {"ok": True},
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await validated_publisher.update_message(
                channel="C0123456789",
                ts="1234567890.123456",
                text="Updated",
            )

        assert result is True
        assert validated_publisher._client.chat_update.call_count == 2

    @pytest.mark.asyncio
    async def test_update_message_returns_false_after_retry_fails(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """Returns False after retry fails."""
        validated_publisher._client.chat_update = AsyncMock(
            side_effect=make_slack_api_error("channel_not_found")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await validated_publisher.update_message(
                channel="C0123456789",
                ts="1234567890.123456",
                text="Updated",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_update_message_truncates_blocks(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """Truncates blocks exceeding limit."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f"Block {i}"}} for i in range(60)]
        await validated_publisher.update_message(
            channel="C0123456789",
            ts="1234567890.123456",
            text="Updated",
            blocks=blocks,
        )

        call_args = validated_publisher._client.chat_update.call_args
        sent_blocks = call_args.kwargs["blocks"]
        assert len(sent_blocks) == 50
        assert "truncated" in sent_blocks[-1]["text"]["text"]


class TestSlackPublisherSessionMessage:
    """Tests for SlackPublisher.send_session_message() and update_session_message()."""

    @pytest.fixture
    def validated_publisher(self) -> SlackPublisher:
        """Create a pre-validated publisher with mock client."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._validated = True
        publisher._client = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_send_session_message_wraps_in_code_block(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """send_session_message wraps content in code block."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        ts = await validated_publisher.send_session_message(
            channel="C0123456789",
            content="Session content here",
        )

        assert ts == "1234567890.123456"
        call_args = validated_publisher._client.chat_postMessage.call_args
        assert call_args.kwargs["text"] == "Session content here"
        blocks = call_args.kwargs["blocks"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert blocks[0]["text"]["text"] == "```Session content here```"

    @pytest.mark.asyncio
    async def test_send_session_message_multiline(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """send_session_message handles multiline content."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        content = "Line 1\nLine 2\nLine 3"
        await validated_publisher.send_session_message(
            channel="C0123456789",
            content=content,
        )

        call_args = validated_publisher._client.chat_postMessage.call_args
        blocks = call_args.kwargs["blocks"]
        assert blocks[0]["text"]["text"] == f"```{content}```"

    @pytest.mark.asyncio
    async def test_update_session_message_wraps_in_code_block(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """update_session_message wraps content in code block with TTL controls."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        await validated_publisher.update_session_message(
            channel="C0123456789",
            ts="1234567890.123456",
            content="Updated session content",
        )

        call_args = validated_publisher._client.chat_update.call_args
        assert call_args.kwargs["text"] == "Updated session content"
        blocks = call_args.kwargs["blocks"]
        # Now includes TTL controls by default
        assert len(blocks) == 2
        assert blocks[0]["text"]["text"] == "```Updated session content```"
        assert blocks[1]["type"] == "actions"
        assert blocks[1]["block_id"] == "ttl_controls"

    @pytest.mark.asyncio
    async def test_update_session_message_returns_none(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """update_session_message returns None."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        result = await validated_publisher.update_session_message(
            channel="C0123456789",
            ts="1234567890.123456",
            content="Content",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_session_message_includes_ttl_controls_with_ts(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """update_session_message includes TTL controls with message ts as value."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        await validated_publisher.update_session_message(
            channel="C0123456789",
            ts="9999999999.999999",
            content="Content",
        )

        call_args = validated_publisher._client.chat_update.call_args
        blocks = call_args.kwargs["blocks"]
        actions_block = blocks[1]

        # Should have live indicator and +30s button
        assert len(actions_block["elements"]) == 2
        assert actions_block["elements"][0]["action_id"] == "ttl_live_indicator"
        assert actions_block["elements"][1]["action_id"] == "extend_ttl"
        assert actions_block["elements"][1]["value"] == "9999999999.999999"

    @pytest.mark.asyncio
    async def test_update_session_message_is_live_true_shows_indicator(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """update_session_message with is_live=True shows live indicator."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        await validated_publisher.update_session_message(
            channel="C0123456789",
            ts="1234567890.123456",
            content="Content",
            is_live=True,
        )

        call_args = validated_publisher._client.chat_update.call_args
        blocks = call_args.kwargs["blocks"]
        elements = blocks[1]["elements"]

        assert len(elements) == 2
        assert elements[0]["action_id"] == "ttl_live_indicator"
        assert elements[0]["style"] == "primary"

    @pytest.mark.asyncio
    async def test_update_session_message_is_live_false_no_indicator(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """update_session_message with is_live=False hides live indicator."""
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        await validated_publisher.update_session_message(
            channel="C0123456789",
            ts="1234567890.123456",
            content="Content",
            is_live=False,
        )

        call_args = validated_publisher._client.chat_update.call_args
        blocks = call_args.kwargs["blocks"]
        elements = blocks[1]["elements"]

        # Only +30s button, no live indicator
        assert len(elements) == 1
        assert elements[0]["action_id"] == "extend_ttl"

    @pytest.mark.asyncio
    async def test_send_session_message_without_ttl_controls(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """send_session_message without TTL controls doesn't update message."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        ts = await validated_publisher.send_session_message(
            channel="C0123456789",
            content="Content",
            include_ttl_controls=False,
        )

        assert ts == "1234567890.123456"
        # Should only call postMessage, not update
        validated_publisher._client.chat_postMessage.assert_called_once()
        validated_publisher._client.chat_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_session_message_with_ttl_controls(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """send_session_message with TTL controls updates message after send."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )
        validated_publisher._client.chat_update = AsyncMock(
            return_value={"ok": True}
        )

        ts = await validated_publisher.send_session_message(
            channel="C0123456789",
            content="Session content",
            include_ttl_controls=True,
        )

        assert ts == "1234567890.123456"

        # Should call postMessage then update
        validated_publisher._client.chat_postMessage.assert_called_once()
        validated_publisher._client.chat_update.assert_called_once()

        # Verify update includes TTL controls with correct ts
        update_call = validated_publisher._client.chat_update.call_args
        blocks = update_call.kwargs["blocks"]
        assert len(blocks) == 2
        assert blocks[1]["type"] == "actions"
        assert blocks[1]["elements"][1]["value"] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_send_session_message_backward_compatible(
        self, validated_publisher: SlackPublisher
    ) -> None:
        """send_session_message is backward compatible without new params."""
        validated_publisher._client.chat_postMessage = AsyncMock(
            return_value={"ok": True, "ts": "1234567890.123456"}
        )

        # Call without include_ttl_controls (defaults to False)
        ts = await validated_publisher.send_session_message(
            channel="C0123456789",
            content="Content",
        )

        assert ts == "1234567890.123456"
        # Only one block (code), no TTL controls
        blocks = validated_publisher._client.chat_postMessage.call_args.kwargs["blocks"]
        assert len(blocks) == 1


class TestSlackPublisherClose:
    """Tests for SlackPublisher.close()."""

    @pytest.mark.asyncio
    async def test_close_with_client(self) -> None:
        """Close clears client reference."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._validated = True
        publisher._client = MagicMock()

        await publisher.close()

        assert publisher._client is None
        assert publisher._validated is False

    @pytest.mark.asyncio
    async def test_close_without_client(self) -> None:
        """Close handles no client gracefully."""
        publisher = SlackPublisher(token="xoxb-test-token")
        publisher._client = None

        # Should not raise
        await publisher.close()
        assert publisher._client is None


# ---------------------------------------------------------------------------
# Module import tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports and __all__."""

    def test_import_slack_publisher_from_watcher(self) -> None:
        """Can import SlackPublisher from watcher package."""
        from claude_session_player.watcher import SlackPublisher as SP

        assert SP is SlackPublisher

    def test_import_exceptions_from_watcher(self) -> None:
        """Can import exceptions from watcher package."""
        from claude_session_player.watcher import SlackAuthError as SAE
        from claude_session_player.watcher import SlackError as SE

        assert SE is SlackError
        assert SAE is SlackAuthError

    def test_import_escape_mrkdwn_from_watcher(self) -> None:
        """Can import escape_mrkdwn from watcher package."""
        from claude_session_player.watcher import escape_mrkdwn as em

        assert em is escape_mrkdwn

    def test_exports_in_all(self) -> None:
        """Key exports are in __all__."""
        from claude_session_player import watcher

        assert "SlackPublisher" in watcher.__all__
        assert "SlackError" in watcher.__all__
        assert "SlackAuthError" in watcher.__all__
        assert "escape_mrkdwn" in watcher.__all__
        assert "format_question_blocks" in watcher.__all__
        assert "format_answered_question_blocks" in watcher.__all__
        assert "SLACK_MAX_QUESTION_BUTTONS" in watcher.__all__


# ---------------------------------------------------------------------------
# Question Block Kit formatting tests
# ---------------------------------------------------------------------------


class TestFormatQuestionBlocksStructure:
    """Tests for format_question_blocks function block structure."""

    def test_single_question_produces_section_actions_context(self) -> None:
        """Single question produces section + actions + context blocks."""
        content = QuestionContent(
            tool_use_id="test-123",
            questions=[
                Question(
                    question="Which option?",
                    header="Choose an option",
                    options=[
                        QuestionOption(label="Option A", description="First option"),
                        QuestionOption(label="Option B", description="Second option"),
                    ],
                    multi_select=False,
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)

        # Should have: section (question), actions (buttons), context (CLI prompt)
        assert len(blocks) == 3
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "actions"
        assert blocks[2]["type"] == "context"

        # Check section content
        assert ":question:" in blocks[0]["text"]["text"]
        assert "*Choose an option*" in blocks[0]["text"]["text"]
        assert "Which option?" in blocks[0]["text"]["text"]

        # Check actions block
        assert len(blocks[1]["elements"]) == 2
        assert blocks[1]["elements"][0]["type"] == "button"
        assert blocks[1]["elements"][0]["text"]["text"] == "Option A"
        assert blocks[1]["elements"][1]["text"]["text"] == "Option B"

        # Check context
        assert "_respond in CLI_" in blocks[2]["elements"][0]["text"]

    def test_button_action_ids_and_values(self) -> None:
        """Buttons have correct action_id and value format."""
        content = QuestionContent(
            tool_use_id="tool-abc",
            questions=[
                Question(
                    question="Pick one",
                    header="Options",
                    options=[
                        QuestionOption(label="A", description=""),
                        QuestionOption(label="B", description=""),
                    ],
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        actions_block = blocks[1]

        # First button
        assert actions_block["elements"][0]["action_id"] == "question_opt_0_0"
        assert actions_block["elements"][0]["value"] == "tool-abc:0:0"

        # Second button
        assert actions_block["elements"][1]["action_id"] == "question_opt_0_1"
        assert actions_block["elements"][1]["value"] == "tool-abc:0:1"

    def test_actions_block_id_format(self) -> None:
        """Actions block has correct block_id format."""
        content = QuestionContent(
            tool_use_id="xyz-789",
            questions=[
                Question(
                    question="Q",
                    header="H",
                    options=[QuestionOption(label="O", description="")],
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        assert blocks[1]["block_id"] == "q_xyz-789_0"

    def test_escapes_mrkdwn_in_header_and_question(self) -> None:
        """Escapes mrkdwn special characters in header and question text."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Choose <item> & stuff",
                    header="Header > title",
                    options=[QuestionOption(label="A", description="")],
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        section_text = blocks[0]["text"]["text"]

        # Should be escaped
        assert "&lt;item&gt;" in section_text
        assert "&amp;" in section_text
        assert "Header &gt; title" in section_text


class TestFormatQuestionBlocksTruncation:
    """Tests for format_question_blocks truncation at MAX_QUESTION_BUTTONS."""

    def test_truncates_at_max_buttons(self) -> None:
        """More than MAX_QUESTION_BUTTONS options shows only MAX buttons with overflow."""
        options = [
            QuestionOption(label=f"Option {i}", description=f"Desc {i}")
            for i in range(8)
        ]
        content = QuestionContent(
            tool_use_id="test-id",
            questions=[
                Question(
                    question="Which one?",
                    header="Choose",
                    options=options,
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)

        # Find actions block
        actions_block = next(b for b in blocks if b["type"] == "actions")
        assert len(actions_block["elements"]) == MAX_QUESTION_BUTTONS

        # Check button labels
        for i in range(MAX_QUESTION_BUTTONS):
            assert actions_block["elements"][i]["text"]["text"] == f"Option {i}"

        # Find overflow context
        context_blocks = [b for b in blocks if b["type"] == "context"]
        # Should have overflow context + final CLI context
        assert len(context_blocks) == 2
        overflow_text = context_blocks[0]["elements"][0]["text"]
        assert "3 more options" in overflow_text

    def test_exactly_max_buttons_no_overflow(self) -> None:
        """Exactly MAX_QUESTION_BUTTONS options shows no overflow notice."""
        options = [
            QuestionOption(label=f"Option {i}", description=f"Desc {i}")
            for i in range(MAX_QUESTION_BUTTONS)
        ]
        content = QuestionContent(
            tool_use_id="test-id",
            questions=[
                Question(
                    question="Which one?",
                    header="Choose",
                    options=options,
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)

        # Only one context block (the final CLI prompt)
        context_blocks = [b for b in blocks if b["type"] == "context"]
        assert len(context_blocks) == 1
        assert "_respond in CLI_" in context_blocks[0]["elements"][0]["text"]

    def test_truncates_long_button_labels(self) -> None:
        """Long button labels are truncated."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q",
                    header="H",
                    options=[
                        QuestionOption(
                            label="This is a very long option label that exceeds the limit",
                            description="",
                        )
                    ],
                )
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        button_text = blocks[1]["elements"][0]["text"]["text"]

        # Should be truncated with ellipsis
        assert len(button_text) <= 30
        assert button_text.endswith("...")

    def test_overflow_singular_option(self) -> None:
        """Overflow notice uses singular 'option' for one extra."""
        options = [
            QuestionOption(label=f"Option {i}", description="")
            for i in range(MAX_QUESTION_BUTTONS + 1)
        ]
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(question="Q", header="H", options=options)
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        context_blocks = [b for b in blocks if b["type"] == "context"]
        overflow_text = context_blocks[0]["elements"][0]["text"]

        assert "1 more option in CLI" in overflow_text
        assert "options" not in overflow_text


class TestFormatQuestionBlocksMultipleQuestions:
    """Tests for format_question_blocks with multiple questions."""

    def test_multiple_questions_separated_by_dividers(self) -> None:
        """Multiple questions are separated by dividers."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="First question?",
                    header="Q1",
                    options=[QuestionOption(label="A1", description="")],
                ),
                Question(
                    question="Second question?",
                    header="Q2",
                    options=[QuestionOption(label="A2", description="")],
                ),
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)

        # Count dividers (should be 1 between questions, not after last)
        divider_count = sum(1 for b in blocks if b["type"] == "divider")
        assert divider_count == 1

        # Verify structure: section, actions, divider, section, actions, context
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "actions"
        assert blocks[2]["type"] == "divider"
        assert blocks[3]["type"] == "section"
        assert blocks[4]["type"] == "actions"
        assert blocks[5]["type"] == "context"

    def test_three_questions_two_dividers(self) -> None:
        """Three questions produce two dividers."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question=f"Question {i}?",
                    header=f"Q{i}",
                    options=[QuestionOption(label=f"A{i}", description="")],
                )
                for i in range(3)
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)
        divider_count = sum(1 for b in blocks if b["type"] == "divider")
        assert divider_count == 2

    def test_multiple_questions_button_indices(self) -> None:
        """Button indices are scoped per question."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q1?",
                    header="H1",
                    options=[
                        QuestionOption(label="Q1-A", description=""),
                        QuestionOption(label="Q1-B", description=""),
                    ],
                ),
                Question(
                    question="Q2?",
                    header="H2",
                    options=[
                        QuestionOption(label="Q2-A", description=""),
                    ],
                ),
            ],
            answers=None,
        )

        blocks = format_question_blocks(content)

        # First question actions
        q1_actions = blocks[1]
        assert q1_actions["block_id"] == "q_test_0"
        assert q1_actions["elements"][0]["action_id"] == "question_opt_0_0"
        assert q1_actions["elements"][1]["action_id"] == "question_opt_0_1"

        # Second question actions (after divider)
        q2_actions = blocks[4]
        assert q2_actions["block_id"] == "q_test_1"
        assert q2_actions["elements"][0]["action_id"] == "question_opt_1_0"


class TestFormatAnsweredQuestionBlocks:
    """Tests for format_answered_question_blocks function."""

    def test_answered_question_shows_selection(self) -> None:
        """Answered question shows the selected answer."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Which option?",
                    header="Choose",
                    options=[
                        QuestionOption(label="Option A", description=""),
                        QuestionOption(label="Option B", description=""),
                    ],
                )
            ],
            answers={"Which option?": "Option A"},
        )

        blocks = format_answered_question_blocks(content)

        # Should have question section + answer section
        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "section"

        # Check question section
        assert ":question:" in blocks[0]["text"]["text"]
        assert "*Choose*" in blocks[0]["text"]["text"]
        assert "Which option?" in blocks[0]["text"]["text"]

        # Check answer section
        assert ":white_check_mark:" in blocks[1]["text"]["text"]
        assert "Selected:" in blocks[1]["text"]["text"]
        assert "_Option A_" in blocks[1]["text"]["text"]

    def test_answered_question_no_actions_block(self) -> None:
        """Answered question has no actions block."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q?",
                    header="H",
                    options=[QuestionOption(label="A", description="")],
                )
            ],
            answers={"Q?": "A"},
        )

        blocks = format_answered_question_blocks(content)

        # No actions blocks
        actions_count = sum(1 for b in blocks if b["type"] == "actions")
        assert actions_count == 0

    def test_answered_question_escapes_answer(self) -> None:
        """Answer text is escaped."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q?",
                    header="H",
                    options=[QuestionOption(label="<answer>", description="")],
                )
            ],
            answers={"Q?": "<special> & stuff"},
        )

        blocks = format_answered_question_blocks(content)
        answer_text = blocks[1]["text"]["text"]

        assert "&lt;special&gt;" in answer_text
        assert "&amp;" in answer_text

    def test_answered_question_no_answer_in_dict(self) -> None:
        """Question without answer in dict doesn't show selection."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q?",
                    header="H",
                    options=[QuestionOption(label="A", description="")],
                )
            ],
            answers={"Other question?": "Other answer"},
        )

        blocks = format_answered_question_blocks(content)

        # Only question section, no answer section
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"

    def test_answered_question_multiple_questions(self) -> None:
        """Multiple answered questions each show their answer."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="Q1?",
                    header="H1",
                    options=[QuestionOption(label="A1", description="")],
                ),
                Question(
                    question="Q2?",
                    header="H2",
                    options=[QuestionOption(label="A2", description="")],
                ),
            ],
            answers={"Q1?": "Answer 1", "Q2?": "Answer 2"},
        )

        blocks = format_answered_question_blocks(content)

        # Q1 section + answer, Q2 section + answer = 4 blocks
        assert len(blocks) == 4

        # Check first answer
        assert "Answer 1" in blocks[1]["text"]["text"]

        # Check second answer
        assert "Answer 2" in blocks[3]["text"]["text"]

    def test_answered_question_uses_question_header_default(self) -> None:
        """Uses 'Question' as default header if none provided."""
        content = QuestionContent(
            tool_use_id="test",
            questions=[
                Question(
                    question="What?",
                    header="",  # Empty header
                    options=[QuestionOption(label="A", description="")],
                )
            ],
            answers={"What?": "A"},
        )

        blocks = format_answered_question_blocks(content)
        assert "*Question*" in blocks[0]["text"]["text"]
