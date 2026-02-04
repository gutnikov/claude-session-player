"""Tests for TelegramPublisher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import EditMessageText, GetMe, SendMessage

from claude_session_player.events import Question, QuestionContent, QuestionOption
from claude_session_player.watcher.telegram_publisher import (
    MAX_QUESTION_BUTTONS,
    TelegramAuthError,
    TelegramError,
    TelegramPublisher,
    _truncate_message,
    escape_html,
    format_question_keyboard,
    format_question_text,
    format_ttl_keyboard,
)


def make_telegram_api_error(message: str, method_type: str = "send") -> TelegramAPIError:
    """Create a TelegramAPIError for testing.

    Args:
        message: Error message.
        method_type: Type of method ("get_me", "send", "edit").

    Returns:
        TelegramAPIError instance.
    """
    if method_type == "get_me":
        method = GetMe()
    elif method_type == "edit":
        method = EditMessageText(chat_id=0, message_id=0, text="")
    else:
        method = SendMessage(chat_id=0, text="")
    return TelegramAPIError(method=method, message=message)


# ---------------------------------------------------------------------------
# HTML escaping tests
# ---------------------------------------------------------------------------


class TestEscapeHtml:
    """Tests for escape_html function."""

    def test_escapes_ampersand(self) -> None:
        """Ampersands are escaped."""
        assert escape_html("hello & world") == "hello &amp; world"

    def test_escapes_less_than(self) -> None:
        """Less-than signs are escaped."""
        assert escape_html("a < b") == "a &lt; b"

    def test_escapes_greater_than(self) -> None:
        """Greater-than signs are escaped."""
        assert escape_html("a > b") == "a &gt; b"

    def test_escapes_multiple_chars(self) -> None:
        """Multiple HTML chars are escaped."""
        assert escape_html("<a>&</a>") == "&lt;a&gt;&amp;&lt;/a&gt;"

    def test_preserves_normal_text(self) -> None:
        """Normal text is preserved."""
        assert escape_html("hello world") == "hello world"

    def test_empty_string(self) -> None:
        """Empty string returns empty."""
        assert escape_html("") == ""


# ---------------------------------------------------------------------------
# Message truncation tests
# ---------------------------------------------------------------------------


class TestTruncateMessage:
    """Tests for _truncate_message function."""

    def test_short_message_unchanged(self) -> None:
        """Short messages are not truncated."""
        text = "Hello world"
        result = _truncate_message(text)
        assert result == text

    def test_truncates_long_message(self) -> None:
        """Long messages are truncated."""
        text = "x" * 5000
        result = _truncate_message(text)
        assert len(result) <= 4096
        assert result.endswith("... [truncated]")

    def test_exact_limit_unchanged(self) -> None:
        """Message at exact limit is not truncated."""
        text = "x" * 4096
        result = _truncate_message(text)
        assert result == text

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        text = "x" * 100
        result = _truncate_message(text, max_length=50)
        assert len(result) <= 50
        assert result.endswith("... [truncated]")


# ---------------------------------------------------------------------------
# TelegramPublisher tests
# ---------------------------------------------------------------------------


class TestTelegramPublisherInit:
    """Tests for TelegramPublisher initialization."""

    def test_init_with_token(self) -> None:
        """Initializes with token."""
        publisher = TelegramPublisher(token="test-token")
        assert publisher._token == "test-token"
        assert publisher._validated is False
        assert publisher._bot is None

    def test_init_without_token(self) -> None:
        """Initializes without token."""
        publisher = TelegramPublisher()
        assert publisher._token is None
        assert publisher._validated is False


class TestTelegramPublisherValidate:
    """Tests for TelegramPublisher.validate()."""

    @pytest.mark.asyncio
    async def test_validate_without_token_raises(self) -> None:
        """Validation fails without token."""
        publisher = TelegramPublisher(token=None)
        with pytest.raises(ValueError, match="token not configured"):
            await publisher.validate()

    @pytest.mark.asyncio
    async def test_validate_skips_if_already_validated(self) -> None:
        """Skips validation if already validated."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True

        # Should not raise or call any external code
        await publisher.validate()
        assert publisher._validated is True

    @pytest.mark.asyncio
    async def test_validate_success(self) -> None:
        """Successful validation sets _validated flag."""
        publisher = TelegramPublisher(token="test-token")

        mock_bot = MagicMock()
        mock_me = MagicMock()
        mock_me.username = "test_bot"
        mock_bot.get_me = AsyncMock(return_value=mock_me)

        with patch(
            "claude_session_player.watcher.telegram_publisher.check_telegram_available",
            return_value=True,
        ):
            with patch("aiogram.Bot", return_value=mock_bot):
                await publisher.validate()

        assert publisher._validated is True
        assert publisher._bot is mock_bot

    @pytest.mark.asyncio
    async def test_validate_auth_failure(self) -> None:
        """Auth failure raises TelegramAuthError."""
        publisher = TelegramPublisher(token="invalid-token")

        mock_bot = MagicMock()
        mock_bot.get_me = AsyncMock(
            side_effect=make_telegram_api_error("Unauthorized", "get_me")
        )

        with patch(
            "claude_session_player.watcher.telegram_publisher.check_telegram_available",
            return_value=True,
        ):
            with patch("aiogram.Bot", return_value=mock_bot):
                with pytest.raises(TelegramAuthError, match="validation failed"):
                    await publisher.validate()

    @pytest.mark.asyncio
    async def test_validate_aiogram_not_installed(self) -> None:
        """Raises TelegramError if aiogram not installed."""
        publisher = TelegramPublisher(token="test-token")

        with patch(
            "claude_session_player.watcher.telegram_publisher.check_telegram_available",
            return_value=False,
        ):
            with pytest.raises(TelegramError, match="aiogram library not installed"):
                await publisher.validate()


class TestTelegramPublisherSendMessage:
    """Tests for TelegramPublisher.send_message()."""

    @pytest.fixture
    def validated_publisher(self) -> TelegramPublisher:
        """Create a pre-validated publisher with mock bot."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True
        publisher._bot = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_send_message_success(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Successfully sends message."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        message_id = await validated_publisher.send_message(
            chat_id="123456789",
            text="Hello world",
        )

        assert message_id == 123
        validated_publisher._bot.send_message.assert_called_once_with(
            chat_id="123456789",
            text="Hello world",
            parse_mode="HTML",
            reply_markup=None,
            message_thread_id=None,
        )

    @pytest.mark.asyncio
    async def test_send_message_truncates_long_text(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Truncates long messages."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        long_text = "x" * 5000
        await validated_publisher.send_message(
            chat_id="123456789",
            text=long_text,
        )

        # Check the text was truncated
        call_args = validated_publisher._bot.send_message.call_args
        sent_text = call_args.kwargs["text"]
        assert len(sent_text) <= 4096
        assert sent_text.endswith("... [truncated]")

    @pytest.mark.asyncio
    async def test_send_message_retry_on_failure(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Retries once on API failure."""
        mock_result = MagicMock()
        mock_result.message_id = 123

        # First call fails, second succeeds
        validated_publisher._bot.send_message = AsyncMock(
            side_effect=[
                make_telegram_api_error("Temporary error", "send"),
                mock_result,
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            message_id = await validated_publisher.send_message(
                chat_id="123456789",
                text="Hello",
            )

        assert message_id == 123
        assert validated_publisher._bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_message_raises_after_retry_fails(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Raises TelegramError after retry fails."""
        validated_publisher._bot.send_message = AsyncMock(
            side_effect=make_telegram_api_error("Permanent error", "send")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TelegramError, match="Send failed"):
                await validated_publisher.send_message(
                    chat_id="123456789",
                    text="Hello",
                )

    @pytest.mark.asyncio
    async def test_send_message_validates_first(self) -> None:
        """Validates before sending if not validated."""
        publisher = TelegramPublisher(token="test-token")

        mock_bot = MagicMock()
        mock_me = MagicMock()
        mock_me.username = "test_bot"
        mock_bot.get_me = AsyncMock(return_value=mock_me)

        mock_result = MagicMock()
        mock_result.message_id = 123
        mock_bot.send_message = AsyncMock(return_value=mock_result)

        with patch(
            "claude_session_player.watcher.telegram_publisher.check_telegram_available",
            return_value=True,
        ):
            with patch("aiogram.Bot", return_value=mock_bot):
                message_id = await publisher.send_message(
                    chat_id="123456789",
                    text="Hello",
                )

        assert message_id == 123
        assert publisher._validated is True

    @pytest.mark.asyncio
    async def test_send_message_with_reply_markup(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Successfully sends message with inline keyboard."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Option A", callback_data="q:123:0:0")]
            ]
        )

        message_id = await validated_publisher.send_message(
            chat_id="123456789",
            text="Choose an option",
            reply_markup=keyboard,
        )

        assert message_id == 123
        validated_publisher._bot.send_message.assert_called_once_with(
            chat_id="123456789",
            text="Choose an option",
            parse_mode="HTML",
            reply_markup=keyboard,
            message_thread_id=None,
        )

    @pytest.mark.asyncio
    async def test_send_message_with_thread_id(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Successfully sends message to a topic thread."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        message_id = await validated_publisher.send_message(
            chat_id="123456789",
            text="Hello",
            message_thread_id=42,
        )

        assert message_id == 123
        validated_publisher._bot.send_message.assert_called_once_with(
            chat_id="123456789",
            text="Hello",
            parse_mode="HTML",
            reply_markup=None,
            message_thread_id=42,
        )


class TestTelegramPublisherEditMessage:
    """Tests for TelegramPublisher.edit_message()."""

    @pytest.fixture
    def validated_publisher(self) -> TelegramPublisher:
        """Create a pre-validated publisher with mock bot."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True
        publisher._bot = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_edit_message_success(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Successfully edits message."""
        validated_publisher._bot.edit_message_text = AsyncMock()

        result = await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text="Updated text",
        )

        assert result is True
        validated_publisher._bot.edit_message_text.assert_called_once_with(
            chat_id="123456789",
            message_id=123,
            text="Updated text",
            parse_mode="HTML",
            reply_markup=None,
        )

    @pytest.mark.asyncio
    async def test_edit_message_not_modified_returns_true(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Returns True when message is not modified."""
        validated_publisher._bot.edit_message_text = AsyncMock(
            side_effect=make_telegram_api_error("message is not modified", "edit")
        )

        result = await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text="Same text",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_edit_message_not_found_returns_false(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Returns False when message not found."""
        validated_publisher._bot.edit_message_text = AsyncMock(
            side_effect=make_telegram_api_error("message to edit not found", "edit")
        )

        result = await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text="Updated text",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_edit_message_retry_on_failure(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Retries once on API failure."""
        # First call fails, second succeeds
        validated_publisher._bot.edit_message_text = AsyncMock(
            side_effect=[
                make_telegram_api_error("Temporary error", "edit"),
                None,  # Success returns None for edit
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await validated_publisher.edit_message(
                chat_id="123456789",
                message_id=123,
                text="Updated",
            )

        assert result is True
        assert validated_publisher._bot.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_edit_message_returns_false_after_retry_fails(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Returns False after retry fails."""
        validated_publisher._bot.edit_message_text = AsyncMock(
            side_effect=make_telegram_api_error("Permanent error", "edit")
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await validated_publisher.edit_message(
                chat_id="123456789",
                message_id=123,
                text="Updated",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_edit_message_truncates_long_text(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Truncates long messages."""
        validated_publisher._bot.edit_message_text = AsyncMock()

        long_text = "x" * 5000
        await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text=long_text,
        )

        call_args = validated_publisher._bot.edit_message_text.call_args
        sent_text = call_args.kwargs["text"]
        assert len(sent_text) <= 4096
        assert sent_text.endswith("... [truncated]")

    @pytest.mark.asyncio
    async def test_edit_message_with_reply_markup(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Successfully edits message with inline keyboard."""
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        validated_publisher._bot.edit_message_text = AsyncMock()

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Option A", callback_data="q:123:0:0")]
            ]
        )

        result = await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text="Updated with keyboard",
            reply_markup=keyboard,
        )

        assert result is True
        validated_publisher._bot.edit_message_text.assert_called_once_with(
            chat_id="123456789",
            message_id=123,
            text="Updated with keyboard",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    @pytest.mark.asyncio
    async def test_edit_message_remove_keyboard(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Removes keyboard by passing None."""
        validated_publisher._bot.edit_message_text = AsyncMock()

        result = await validated_publisher.edit_message(
            chat_id="123456789",
            message_id=123,
            text="No keyboard",
            reply_markup=None,
        )

        assert result is True
        call_args = validated_publisher._bot.edit_message_text.call_args
        assert call_args.kwargs["reply_markup"] is None


# ---------------------------------------------------------------------------
# Session message tests
# ---------------------------------------------------------------------------


class TestTelegramPublisherSendSessionMessage:
    """Tests for TelegramPublisher.send_session_message()."""

    @pytest.fixture
    def validated_publisher(self) -> TelegramPublisher:
        """Create a pre-validated publisher with mock bot."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True
        publisher._bot = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_send_session_message_wraps_in_pre(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Wraps content in <pre> tags with HTML escaping."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        message_id = await validated_publisher.send_session_message(
            chat_id="123456789",
            content="Hello <world> & friends",
        )

        assert message_id == 123
        call_args = validated_publisher._bot.send_message.call_args
        assert call_args.kwargs["text"] == "<pre>Hello &lt;world&gt; &amp; friends</pre>"
        assert call_args.kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_send_session_message_with_thread_id(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Passes thread_id to send_message."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        message_id = await validated_publisher.send_session_message(
            chat_id="123456789",
            content="Hello",
            thread_id=42,
        )

        assert message_id == 123
        call_args = validated_publisher._bot.send_message.call_args
        assert call_args.kwargs["message_thread_id"] == 42


class TestTelegramPublisherUpdateSessionMessage:
    """Tests for TelegramPublisher.update_session_message()."""

    @pytest.fixture
    def validated_publisher(self) -> TelegramPublisher:
        """Create a pre-validated publisher with mock bot."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True
        publisher._bot = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_update_session_message_wraps_in_pre(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Wraps content in <pre> tags with HTML escaping."""
        validated_publisher._bot.edit_message_text = AsyncMock()

        result = await validated_publisher.update_session_message(
            chat_id="123456789",
            message_id=123,
            content="Updated <content> & more",
        )

        assert result is True
        call_args = validated_publisher._bot.edit_message_text.call_args
        assert (
            call_args.kwargs["text"] == "<pre>Updated &lt;content&gt; &amp; more</pre>"
        )
        assert call_args.kwargs["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_update_session_message_returns_false_on_not_found(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Returns False when message not found."""
        validated_publisher._bot.edit_message_text = AsyncMock(
            side_effect=make_telegram_api_error("message to edit not found", "edit")
        )

        result = await validated_publisher.update_session_message(
            chat_id="123456789",
            message_id=123,
            content="Updated",
        )

        assert result is False


# ---------------------------------------------------------------------------
# Question message tests
# ---------------------------------------------------------------------------


class TestTelegramPublisherSendQuestion:
    """Tests for TelegramPublisher.send_question()."""

    @pytest.fixture
    def validated_publisher(self) -> TelegramPublisher:
        """Create a pre-validated publisher with mock bot."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True
        publisher._bot = MagicMock()
        return publisher

    @pytest.mark.asyncio
    async def test_send_question_with_keyboard(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Sends question with inline keyboard buttons."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        content = QuestionContent(
            tool_use_id="tool-123",
            questions=[
                Question(
                    question="Which option?",
                    header="Choose",
                    options=[
                        QuestionOption(label="Option A", description="First"),
                        QuestionOption(label="Option B", description="Second"),
                    ],
                )
            ],
        )

        message_id = await validated_publisher.send_question(
            chat_id="123456789",
            content=content,
        )

        assert message_id == 123
        call_args = validated_publisher._bot.send_message.call_args
        assert call_args.kwargs["parse_mode"] == "HTML"
        assert call_args.kwargs["reply_markup"] is not None
        # Check keyboard has buttons
        keyboard = call_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 2

    @pytest.mark.asyncio
    async def test_send_question_with_thread_id(
        self, validated_publisher: TelegramPublisher
    ) -> None:
        """Passes thread_id when sending question."""
        mock_result = MagicMock()
        mock_result.message_id = 123
        validated_publisher._bot.send_message = AsyncMock(return_value=mock_result)

        content = QuestionContent(
            tool_use_id="tool-123",
            questions=[
                Question(
                    question="Q?",
                    header="H",
                    options=[QuestionOption(label="A", description="a")],
                )
            ],
        )

        await validated_publisher.send_question(
            chat_id="123456789",
            content=content,
            thread_id=42,
        )

        call_args = validated_publisher._bot.send_message.call_args
        assert call_args.kwargs["message_thread_id"] == 42


class TestTelegramPublisherClose:
    """Tests for TelegramPublisher.close()."""

    @pytest.mark.asyncio
    async def test_close_with_bot(self) -> None:
        """Close shuts down bot session."""
        publisher = TelegramPublisher(token="test-token")
        publisher._validated = True

        mock_session = AsyncMock()
        publisher._bot = MagicMock()
        publisher._bot.session = mock_session

        await publisher.close()

        mock_session.close.assert_called_once()
        assert publisher._bot is None
        assert publisher._validated is False

    @pytest.mark.asyncio
    async def test_close_without_bot(self) -> None:
        """Close handles no bot gracefully."""
        publisher = TelegramPublisher(token="test-token")
        publisher._bot = None

        # Should not raise
        await publisher.close()
        assert publisher._bot is None


# ---------------------------------------------------------------------------
# Module import tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports and __all__."""

    def test_import_telegram_publisher_from_watcher(self) -> None:
        """Can import TelegramPublisher from watcher package."""
        from claude_session_player.watcher import TelegramPublisher as TP

        assert TP is TelegramPublisher

    def test_import_exceptions_from_watcher(self) -> None:
        """Can import exceptions from watcher package."""
        from claude_session_player.watcher import TelegramAuthError as TAE
        from claude_session_player.watcher import TelegramError as TE

        assert TE is TelegramError
        assert TAE is TelegramAuthError

    def test_import_escape_html_from_watcher(self) -> None:
        """Can import escape_html from watcher package."""
        from claude_session_player.watcher import escape_html as eh

        assert eh is escape_html

    def test_import_question_functions_from_watcher(self) -> None:
        """Can import question formatting functions from watcher package."""
        from claude_session_player.watcher import format_question_keyboard as fqk
        from claude_session_player.watcher import format_question_text as fqt

        assert fqk is format_question_keyboard
        assert fqt is format_question_text

    def test_exports_in_all(self) -> None:
        """All exports are in __all__."""
        from claude_session_player import watcher

        assert "TelegramPublisher" in watcher.__all__
        assert "TelegramError" in watcher.__all__
        assert "TelegramAuthError" in watcher.__all__
        assert "escape_html" in watcher.__all__
        assert "format_question_keyboard" in watcher.__all__
        assert "format_question_text" in watcher.__all__
        assert "MAX_QUESTION_BUTTONS" in watcher.__all__


# ---------------------------------------------------------------------------
# Question keyboard tests
# ---------------------------------------------------------------------------


class TestFormatQuestionKeyboard:
    """Tests for format_question_keyboard function."""

    def test_single_question_with_options(self) -> None:
        """Creates keyboard with buttons for each option."""
        content = QuestionContent(
            tool_use_id="tool-123",
            questions=[
                Question(
                    question="Which option?",
                    header="Choose",
                    options=[
                        QuestionOption(label="Option A", description="First option"),
                        QuestionOption(label="Option B", description="Second option"),
                    ],
                )
            ],
        )

        keyboard = format_question_keyboard(content)

        assert keyboard is not None
        # Two buttons, one per row
        assert len(keyboard.inline_keyboard) == 2
        assert keyboard.inline_keyboard[0][0].text == "Option A"
        assert keyboard.inline_keyboard[1][0].text == "Option B"
        # Check callback data format
        assert keyboard.inline_keyboard[0][0].callback_data == "q:tool-123:0:0"
        assert keyboard.inline_keyboard[1][0].callback_data == "q:tool-123:0:1"

    def test_truncates_at_max_buttons(self) -> None:
        """Only shows MAX_QUESTION_BUTTONS options."""
        options = [
            QuestionOption(label=f"Option {i}", description=f"Desc {i}")
            for i in range(10)
        ]
        content = QuestionContent(
            tool_use_id="tool-456",
            questions=[
                Question(
                    question="Pick one",
                    header="Many options",
                    options=options,
                )
            ],
        )

        keyboard = format_question_keyboard(content)

        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == MAX_QUESTION_BUTTONS
        # Verify only first 5 options are shown
        for i in range(MAX_QUESTION_BUTTONS):
            assert keyboard.inline_keyboard[i][0].text == f"Option {i}"

    def test_answered_question_returns_none(self) -> None:
        """Returns None for answered questions."""
        content = QuestionContent(
            tool_use_id="tool-789",
            questions=[
                Question(
                    question="Which?",
                    header="Q",
                    options=[
                        QuestionOption(label="A", description="a"),
                    ],
                )
            ],
            answers={"Which?": "A"},
        )

        keyboard = format_question_keyboard(content)

        assert keyboard is None

    def test_truncates_long_labels(self) -> None:
        """Truncates labels longer than 30 characters."""
        long_label = "A" * 50
        content = QuestionContent(
            tool_use_id="tool-long",
            questions=[
                Question(
                    question="Q",
                    header="H",
                    options=[
                        QuestionOption(label=long_label, description="d"),
                    ],
                )
            ],
        )

        keyboard = format_question_keyboard(content)

        assert keyboard is not None
        button_text = keyboard.inline_keyboard[0][0].text
        assert len(button_text) == 30
        assert button_text.endswith("...")

    def test_empty_options_returns_none(self) -> None:
        """Returns None when no options available."""
        content = QuestionContent(
            tool_use_id="tool-empty",
            questions=[
                Question(
                    question="Q",
                    header="H",
                    options=[],
                )
            ],
        )

        keyboard = format_question_keyboard(content)

        assert keyboard is None


class TestFormatQuestionText:
    """Tests for format_question_text function."""

    def test_basic_question_text(self) -> None:
        """Formats question with header and text in HTML."""
        content = QuestionContent(
            tool_use_id="tool-123",
            questions=[
                Question(
                    question="What is your choice?",
                    header="Permission",
                    options=[
                        QuestionOption(label="Yes", description="y"),
                        QuestionOption(label="No", description="n"),
                    ],
                )
            ],
        )

        text = format_question_text(content)

        assert "<b>❓ Permission</b>" in text
        assert "<pre>What is your choice?</pre>" in text
        assert "<i>(respond in CLI)</i>" in text

    def test_shows_overflow_message(self) -> None:
        """Shows overflow message when more than MAX_QUESTION_BUTTONS options."""
        options = [
            QuestionOption(label=f"Option {i}", description=f"d{i}") for i in range(8)
        ]
        content = QuestionContent(
            tool_use_id="tool-overflow",
            questions=[
                Question(
                    question="Pick",
                    header="Many",
                    options=options,
                )
            ],
        )

        text = format_question_text(content)

        overflow_count = 8 - MAX_QUESTION_BUTTONS
        assert f"...and {overflow_count} more options in CLI" in text

    def test_singular_overflow_message(self) -> None:
        """Uses singular 'option' when only one extra."""
        options = [
            QuestionOption(label=f"Option {i}", description=f"d{i}")
            for i in range(MAX_QUESTION_BUTTONS + 1)
        ]
        content = QuestionContent(
            tool_use_id="tool-one-more",
            questions=[
                Question(
                    question="Pick",
                    header="H",
                    options=options,
                )
            ],
        )

        text = format_question_text(content)

        assert "...and 1 more option in CLI" in text
        assert "options" not in text.split("...and 1 more")[1].split("\n")[0]

    def test_escapes_html_in_header(self) -> None:
        """Escapes HTML special chars in header."""
        content = QuestionContent(
            tool_use_id="tool-esc",
            questions=[
                Question(
                    question="Q",
                    header="Use <tag> here",
                    options=[QuestionOption(label="A", description="a")],
                )
            ],
        )

        text = format_question_text(content)

        assert "&lt;tag&gt;" in text

    def test_default_header(self) -> None:
        """Uses 'Question' as default header when none provided."""
        content = QuestionContent(
            tool_use_id="tool-no-header",
            questions=[
                Question(
                    question="What?",
                    header="",
                    options=[QuestionOption(label="A", description="a")],
                )
            ],
        )

        text = format_question_text(content)

        assert "<b>❓ Question</b>" in text


# ---------------------------------------------------------------------------
# format_ttl_keyboard tests
# ---------------------------------------------------------------------------


class TestFormatTTLKeyboard:
    """Tests for format_ttl_keyboard function."""

    def test_live_keyboard_has_both_buttons(self) -> None:
        """Live keyboard has ⚡ Live indicator and +30s button."""
        keyboard = format_ttl_keyboard(message_id=12345, is_live=True)

        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        row = keyboard.inline_keyboard[0]
        assert len(row) == 2

        # First button is live indicator
        assert row[0].text == "⚡ Live"
        assert row[0].callback_data == "noop"

        # Second button is +30s
        assert row[1].text == "+30s"
        assert row[1].callback_data == "extend:12345"

    def test_expired_keyboard_has_only_extend_button(self) -> None:
        """Expired keyboard has only +30s button."""
        keyboard = format_ttl_keyboard(message_id=67890, is_live=False)

        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        row = keyboard.inline_keyboard[0]
        assert len(row) == 1

        # Only +30s button
        assert row[0].text == "+30s"
        assert row[0].callback_data == "extend:67890"

    def test_callback_data_format(self) -> None:
        """Callback data follows extend:{message_id} format."""
        keyboard = format_ttl_keyboard(message_id=999, is_live=True)

        assert keyboard is not None
        row = keyboard.inline_keyboard[0]
        extend_button = row[1]  # Second button

        assert extend_button.callback_data == "extend:999"
        assert extend_button.callback_data.startswith("extend:")
        parts = extend_button.callback_data.split(":")
        assert len(parts) == 2
        assert parts[0] == "extend"
        assert parts[1] == "999"

    def test_callback_data_within_limit(self) -> None:
        """Callback data fits within 64-byte limit."""
        # Test with a large message_id
        keyboard = format_ttl_keyboard(message_id=999999999999, is_live=True)

        assert keyboard is not None
        row = keyboard.inline_keyboard[0]
        extend_button = row[1]

        # Telegram's callback_data limit is 64 bytes
        assert len(extend_button.callback_data.encode("utf-8")) <= 64

    def test_default_is_live(self) -> None:
        """Default is_live parameter is True."""
        keyboard = format_ttl_keyboard(message_id=123)

        assert keyboard is not None
        row = keyboard.inline_keyboard[0]
        # Should have both buttons since is_live defaults to True
        assert len(row) == 2
        assert row[0].text == "⚡ Live"
