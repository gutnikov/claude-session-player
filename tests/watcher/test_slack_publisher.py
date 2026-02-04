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
    ToolCallInfo,
    _truncate_blocks,
    escape_mrkdwn,
    format_answered_question_blocks,
    format_context_compacted_blocks,
    format_question_blocks,
    format_system_message_blocks,
    format_turn_message_blocks,
    format_user_message_blocks,
    get_tool_icon,
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
# Tool icon tests
# ---------------------------------------------------------------------------


class TestGetToolIcon:
    """Tests for get_tool_icon function."""

    def test_read_icon(self) -> None:
        """Read tool has book icon."""
        assert get_tool_icon("Read") == "📖"

    def test_write_icon(self) -> None:
        """Write tool has memo icon."""
        assert get_tool_icon("Write") == "📝"

    def test_edit_icon(self) -> None:
        """Edit tool has pencil icon."""
        assert get_tool_icon("Edit") == "✏️"

    def test_bash_icon(self) -> None:
        """Bash tool has wrench icon."""
        assert get_tool_icon("Bash") == "🔧"

    def test_task_icon(self) -> None:
        """Task tool has robot icon."""
        assert get_tool_icon("Task") == "🤖"

    def test_unknown_tool_icon(self) -> None:
        """Unknown tool gets gear icon."""
        assert get_tool_icon("UnknownTool") == "⚙️"


# ---------------------------------------------------------------------------
# Block Kit formatting tests
# ---------------------------------------------------------------------------


class TestFormatUserMessageBlocks:
    """Tests for format_user_message_blocks function."""

    def test_basic_message(self) -> None:
        """Formats basic user message as blocks."""
        result = format_user_message_blocks("Hello world")
        assert len(result) == 1
        assert result[0]["type"] == "section"
        assert result[0]["text"]["type"] == "mrkdwn"
        assert "👤 *User*" in result[0]["text"]["text"]
        assert "Hello world" in result[0]["text"]["text"]

    def test_escapes_mrkdwn(self) -> None:
        """Escapes mrkdwn in user text."""
        result = format_user_message_blocks("Hello <world>")
        assert "&lt;world&gt;" in result[0]["text"]["text"]

    def test_multiline_message(self) -> None:
        """Handles multiline message."""
        result = format_user_message_blocks("Line 1\nLine 2")
        assert "Line 1\nLine 2" in result[0]["text"]["text"]


class TestFormatTurnMessageBlocks:
    """Tests for format_turn_message_blocks function."""

    def test_assistant_text_only(self) -> None:
        """Formats turn with assistant text only."""
        result = format_turn_message_blocks(
            assistant_text="Hello world",
            tool_calls=[],
            duration_ms=None,
        )
        assert len(result) == 1
        assert "🤖 *Assistant*" in result[0]["text"]["text"]
        assert "Hello world" in result[0]["text"]["text"]

    def test_with_duration(self) -> None:
        """Includes duration footer."""
        result = format_turn_message_blocks(
            assistant_text="Hello",
            tool_calls=[],
            duration_ms=5000,
        )
        # Last block should be context with duration
        assert result[-1]["type"] == "context"
        assert "5.0s" in result[-1]["elements"][0]["text"]

    def test_with_tool_call(self) -> None:
        """Formats tool call."""
        result = format_turn_message_blocks(
            assistant_text=None,
            tool_calls=[
                ToolCallInfo(
                    name="Read",
                    label="file.txt",
                    icon="📖",
                    result="contents",
                    is_error=False,
                )
            ],
            duration_ms=None,
        )
        # Should have header, divider, tool call section
        assert len(result) == 3
        assert result[1]["type"] == "divider"
        tool_text = result[2]["text"]["text"]
        assert "*Read*" in tool_text
        assert "`file.txt`" in tool_text
        assert "✓ contents" in tool_text

    def test_tool_call_with_error(self) -> None:
        """Formats tool call error."""
        result = format_turn_message_blocks(
            assistant_text=None,
            tool_calls=[
                ToolCallInfo(
                    name="Bash",
                    label="ls -la",
                    icon="🔧",
                    result=None,
                    is_error=True,
                )
            ],
            duration_ms=None,
        )
        tool_text = result[2]["text"]["text"]
        assert "✗ Error" in tool_text

    def test_multiple_tool_calls(self) -> None:
        """Handles multiple tool calls."""
        result = format_turn_message_blocks(
            assistant_text=None,
            tool_calls=[
                ToolCallInfo(name="Read", label="a.txt", icon="📖", result="a", is_error=False),
                ToolCallInfo(name="Read", label="b.txt", icon="📖", result="b", is_error=False),
            ],
            duration_ms=None,
        )
        # Header + (divider + tool) * 2 = 5 blocks
        assert len(result) == 5
        # Count dividers
        dividers = [b for b in result if b["type"] == "divider"]
        assert len(dividers) == 2

    def test_truncates_long_tool_result(self) -> None:
        """Truncates long tool results."""
        long_result = "x" * 1500
        result = format_turn_message_blocks(
            assistant_text=None,
            tool_calls=[
                ToolCallInfo(
                    name="Read",
                    label="big.txt",
                    icon="📖",
                    result=long_result,
                    is_error=False,
                )
            ],
            duration_ms=None,
        )
        tool_text = result[2]["text"]["text"]
        assert "..." in tool_text
        # Should be truncated to ~1000 chars + overhead
        assert len(tool_text) < 1200

    def test_escapes_assistant_text(self) -> None:
        """Escapes mrkdwn in assistant text."""
        result = format_turn_message_blocks(
            assistant_text="Hello <world>",
            tool_calls=[],
            duration_ms=None,
        )
        assert "&lt;world&gt;" in result[0]["text"]["text"]


class TestFormatSystemMessageBlocks:
    """Tests for format_system_message_blocks function."""

    def test_basic_system_message(self) -> None:
        """Formats system message as blocks."""
        result = format_system_message_blocks("Session started")
        assert len(result) == 1
        assert result[0]["type"] == "section"
        assert "⚡ *Session started*" in result[0]["text"]["text"]

    def test_escapes_mrkdwn(self) -> None:
        """Escapes mrkdwn in system text."""
        result = format_system_message_blocks("Error: <failed>")
        assert "&lt;failed&gt;" in result[0]["text"]["text"]


class TestFormatContextCompactedBlocks:
    """Tests for format_context_compacted_blocks function."""

    def test_compaction_message(self) -> None:
        """Returns context compacted message blocks."""
        result = format_context_compacted_blocks()
        assert len(result) == 1
        assert "⚡ *Context compacted*" in result[0]["text"]["text"]
        assert "previous messages cleared" in result[0]["text"]["text"]


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

    def test_import_formatting_functions_from_watcher(self) -> None:
        """Can import formatting functions from watcher package."""
        from claude_session_player.watcher import (
            escape_mrkdwn as em,
            format_context_compacted_blocks as fccb,
            format_system_message_blocks as fsmb,
            format_turn_message_blocks as ftmb,
            format_user_message_blocks as fumb,
        )

        assert em is escape_mrkdwn
        assert fccb is format_context_compacted_blocks
        assert fsmb is format_system_message_blocks
        assert ftmb is format_turn_message_blocks
        assert fumb is format_user_message_blocks

    def test_import_slack_tool_call_info_from_watcher(self) -> None:
        """Can import SlackToolCallInfo from watcher package."""
        from claude_session_player.watcher import SlackToolCallInfo as STCI

        assert STCI is ToolCallInfo

    def test_exports_in_all(self) -> None:
        """All exports are in __all__."""
        from claude_session_player import watcher

        assert "SlackPublisher" in watcher.__all__
        assert "SlackError" in watcher.__all__
        assert "SlackAuthError" in watcher.__all__
        assert "SlackToolCallInfo" in watcher.__all__
        assert "escape_mrkdwn" in watcher.__all__
        assert "format_user_message_blocks" in watcher.__all__
        assert "format_turn_message_blocks" in watcher.__all__
        assert "format_system_message_blocks" in watcher.__all__
        assert "format_context_compacted_blocks" in watcher.__all__


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
