"""Tests for telegram_bot.py module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.telegram_bot import (
    BotCommandDef,
    TelegramBotConfig,
    TelegramBotState,
    TelegramPollingRunner,
    build_webhook_url,
    create_combined_callback_handler,
    create_extend_ttl_callback_handler,
    create_noop_callback_handler,
    create_question_callback_handler,
    delete_telegram_webhook,
    get_bot_info,
    get_webhook_info,
    initialize_telegram_bot,
    setup_telegram_webhook,
    shutdown_telegram_bot,
    start_telegram_polling,
    DEFAULT_BOT_COMMANDS,
)


# ---------------------------------------------------------------------------
# BotCommandDef Tests
# ---------------------------------------------------------------------------


class TestBotCommandDef:
    """Tests for BotCommandDef dataclass."""

    def test_create(self) -> None:
        """Test creating a bot command definition."""
        cmd = BotCommandDef(command="search", description="Search sessions")
        assert cmd.command == "search"
        assert cmd.description == "Search sessions"

    def test_default_commands(self) -> None:
        """Test that default commands are defined."""
        assert len(DEFAULT_BOT_COMMANDS) == 3
        commands = {cmd.command for cmd in DEFAULT_BOT_COMMANDS}
        assert commands == {"search", "projects", "recent"}


# ---------------------------------------------------------------------------
# TelegramBotConfig Tests
# ---------------------------------------------------------------------------


class TestTelegramBotConfig:
    """Tests for TelegramBotConfig dataclass."""

    def test_defaults(self) -> None:
        """Test default configuration values."""
        config = TelegramBotConfig(token="test_token")
        assert config.token == "test_token"
        assert config.mode == "webhook"
        assert config.webhook_url is None
        assert config.allowed_updates == ["message", "callback_query"]
        assert config.drop_pending_updates is True

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = TelegramBotConfig(
            token="test_token",
            mode="polling",
            webhook_url="https://example.com",
            allowed_updates=["message"],
            drop_pending_updates=False,
        )
        assert config.mode == "polling"
        assert config.webhook_url == "https://example.com"
        assert config.allowed_updates == ["message"]
        assert config.drop_pending_updates is False

    def test_validate_missing_token(self) -> None:
        """Test validation fails without token."""
        config = TelegramBotConfig(token="")
        with pytest.raises(ValueError, match="token is required"):
            config.validate()

    def test_validate_invalid_mode(self) -> None:
        """Test validation fails with invalid mode."""
        config = TelegramBotConfig(token="test", mode="invalid")
        with pytest.raises(ValueError, match="Unknown Telegram mode"):
            config.validate()

    def test_validate_webhook_missing_url(self) -> None:
        """Test validation fails in webhook mode without URL."""
        config = TelegramBotConfig(token="test", mode="webhook")
        with pytest.raises(ValueError, match="webhook_url is required"):
            config.validate()

    def test_validate_webhook_with_url(self) -> None:
        """Test validation passes in webhook mode with URL."""
        config = TelegramBotConfig(
            token="test",
            mode="webhook",
            webhook_url="https://example.com",
        )
        config.validate()  # Should not raise

    def test_validate_polling_mode(self) -> None:
        """Test validation passes in polling mode without URL."""
        config = TelegramBotConfig(token="test", mode="polling")
        config.validate()  # Should not raise

    def test_from_dict_minimal(self) -> None:
        """Test creating config from minimal dict."""
        config = TelegramBotConfig.from_dict({"token": "test_token"})
        assert config is not None
        assert config.token == "test_token"
        assert config.mode == "webhook"

    def test_from_dict_full(self) -> None:
        """Test creating config from full dict."""
        config = TelegramBotConfig.from_dict({
            "token": "test_token",
            "mode": "polling",
            "webhook_url": "https://example.com",
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        })
        assert config is not None
        assert config.mode == "polling"
        assert config.webhook_url == "https://example.com"
        assert config.allowed_updates == ["message"]
        assert config.drop_pending_updates is False

    def test_from_dict_no_token(self) -> None:
        """Test from_dict returns None without token."""
        config = TelegramBotConfig.from_dict({})
        assert config is None

        config = TelegramBotConfig.from_dict({"mode": "polling"})
        assert config is None


# ---------------------------------------------------------------------------
# Webhook URL Tests
# ---------------------------------------------------------------------------


class TestBuildWebhookUrl:
    """Tests for build_webhook_url function."""

    def test_simple_url(self) -> None:
        """Test building URL with simple base."""
        url = build_webhook_url("https://example.com")
        assert url == "https://example.com/telegram/webhook"

    def test_url_with_trailing_slash(self) -> None:
        """Test building URL strips trailing slash."""
        url = build_webhook_url("https://example.com/")
        assert url == "https://example.com/telegram/webhook"

    def test_url_with_path(self) -> None:
        """Test building URL with base path."""
        url = build_webhook_url("https://example.com/api")
        assert url == "https://example.com/api/telegram/webhook"

    def test_custom_path(self) -> None:
        """Test building URL with custom path."""
        url = build_webhook_url("https://example.com", "/custom/path")
        assert url == "https://example.com/custom/path"

    def test_custom_path_without_slash(self) -> None:
        """Test building URL with custom path adds leading slash."""
        url = build_webhook_url("https://example.com", "webhook")
        assert url == "https://example.com/webhook"


# ---------------------------------------------------------------------------
# Webhook Setup Tests
# ---------------------------------------------------------------------------


class TestSetupTelegramWebhook:
    """Tests for setup_telegram_webhook function."""

    @pytest.mark.asyncio
    async def test_webhook_url_construction(self) -> None:
        """Test webhook URL is constructed correctly."""
        url = build_webhook_url("https://my-server.com")
        assert url == "https://my-server.com/telegram/webhook"

    @pytest.mark.asyncio
    async def test_webhook_url_with_trailing_slash(self) -> None:
        """Test webhook URL strips trailing slash."""
        url = build_webhook_url("https://my-server.com/")
        assert url == "https://my-server.com/telegram/webhook"

    @pytest.mark.asyncio
    async def test_webhook_url_with_custom_path(self) -> None:
        """Test webhook URL with custom path."""
        url = build_webhook_url("https://my-server.com", "/api/telegram")
        assert url == "https://my-server.com/api/telegram"


class TestDeleteTelegramWebhook:
    """Tests for delete_telegram_webhook function."""

    @pytest.mark.asyncio
    async def test_delete_webhook(self) -> None:
        """Test webhook deletion."""
        mock_bot = AsyncMock()
        mock_bot.delete_webhook = AsyncMock()

        await delete_telegram_webhook(mock_bot)

        mock_bot.delete_webhook.assert_called_once()


# ---------------------------------------------------------------------------
# Polling Tests
# ---------------------------------------------------------------------------


class TestTelegramPollingRunner:
    """Tests for TelegramPollingRunner class."""

    @pytest.mark.asyncio
    async def test_start_polling(self) -> None:
        """Test starting polling creates task."""
        mock_bot = AsyncMock()
        mock_dp = AsyncMock()
        mock_dp.start_polling = AsyncMock()

        runner = TelegramPollingRunner(bot=mock_bot, dispatcher=mock_dp)

        # Start returns immediately, polling runs in background
        await runner.start()

        assert runner.polling_task is not None

        # Clean up
        await runner.stop()

    @pytest.mark.asyncio
    async def test_start_polling_twice(self) -> None:
        """Test starting polling twice is safe."""
        mock_bot = AsyncMock()
        mock_dp = AsyncMock()

        runner = TelegramPollingRunner(bot=mock_bot, dispatcher=mock_dp)

        await runner.start()
        await runner.start()  # Should log warning but not fail

        assert runner.polling_task is not None

        await runner.stop()

    @pytest.mark.asyncio
    async def test_stop_polling(self) -> None:
        """Test stopping polling cancels task."""
        mock_bot = AsyncMock()
        mock_dp = AsyncMock()

        runner = TelegramPollingRunner(bot=mock_bot, dispatcher=mock_dp)

        await runner.start()
        await runner.stop()

        assert runner.polling_task is None

    @pytest.mark.asyncio
    async def test_stop_not_started(self) -> None:
        """Test stopping when not started is safe."""
        mock_bot = AsyncMock()
        mock_dp = AsyncMock()

        runner = TelegramPollingRunner(bot=mock_bot, dispatcher=mock_dp)
        await runner.stop()  # Should not raise


class TestStartTelegramPolling:
    """Tests for start_telegram_polling function."""

    def test_polling_runner_has_required_attributes(self) -> None:
        """Test TelegramPollingRunner has required attributes."""
        mock_bot = MagicMock()
        mock_dp = MagicMock()

        runner = TelegramPollingRunner(bot=mock_bot, dispatcher=mock_dp)

        assert runner.bot is mock_bot
        assert runner.dispatcher is mock_dp
        assert runner.polling_task is None


# ---------------------------------------------------------------------------
# Mode Selection Tests
# ---------------------------------------------------------------------------


class TestInitializeTelegramBot:
    """Tests for initialize_telegram_bot function."""

    @pytest.mark.asyncio
    async def test_invalid_config(self) -> None:
        """Test initialization fails with invalid config."""
        config = TelegramBotConfig(token="", mode="webhook")

        with pytest.raises(ValueError, match="token is required"):
            await initialize_telegram_bot(config)

    @pytest.mark.asyncio
    async def test_webhook_mode_missing_url(self) -> None:
        """Test initialization fails without webhook URL."""
        config = TelegramBotConfig(token="test", mode="webhook")

        with pytest.raises(ValueError, match="webhook_url is required"):
            await initialize_telegram_bot(config)


class TestShutdownTelegramBot:
    """Tests for shutdown_telegram_bot function."""

    @pytest.mark.asyncio
    async def test_shutdown_webhook_mode(self) -> None:
        """Test shutdown in webhook mode."""
        mock_bot = AsyncMock()
        mock_bot.session = AsyncMock()
        mock_bot.session.close = AsyncMock()

        state = TelegramBotState(mode="webhook", bot=mock_bot)

        await shutdown_telegram_bot(state)

        mock_bot.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_polling_mode(self) -> None:
        """Test shutdown in polling mode stops runner."""
        mock_bot = AsyncMock()
        mock_bot.session = AsyncMock()
        mock_bot.session.close = AsyncMock()

        mock_runner = AsyncMock(spec=TelegramPollingRunner)

        state = TelegramBotState(
            mode="polling",
            bot=mock_bot,
            polling_runner=mock_runner,
        )

        await shutdown_telegram_bot(state)

        mock_runner.stop.assert_called_once()
        mock_bot.session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Utility Function Tests
# ---------------------------------------------------------------------------


class TestGetBotInfo:
    """Tests for get_bot_info function."""

    @pytest.mark.asyncio
    async def test_get_bot_info(self) -> None:
        """Test getting bot information."""
        mock_me = MagicMock()
        mock_me.id = 123456789
        mock_me.username = "test_bot"
        mock_me.first_name = "Test Bot"
        mock_me.can_join_groups = True
        mock_me.can_read_all_group_messages = False
        mock_me.supports_inline_queries = True

        mock_bot = AsyncMock()
        mock_bot.get_me = AsyncMock(return_value=mock_me)

        info = await get_bot_info(mock_bot)

        assert info["id"] == 123456789
        assert info["username"] == "test_bot"
        assert info["first_name"] == "Test Bot"
        assert info["can_join_groups"] is True
        assert info["can_read_all_group_messages"] is False
        assert info["supports_inline_queries"] is True


class TestGetWebhookInfo:
    """Tests for get_webhook_info function."""

    @pytest.mark.asyncio
    async def test_get_webhook_info(self) -> None:
        """Test getting webhook information."""
        mock_info = MagicMock()
        mock_info.url = "https://example.com/telegram/webhook"
        mock_info.has_custom_certificate = False
        mock_info.pending_update_count = 5
        mock_info.last_error_date = None
        mock_info.last_error_message = None
        mock_info.max_connections = 40
        mock_info.allowed_updates = ["message", "callback_query"]

        mock_bot = AsyncMock()
        mock_bot.get_webhook_info = AsyncMock(return_value=mock_info)

        info = await get_webhook_info(mock_bot)

        assert info["url"] == "https://example.com/telegram/webhook"
        assert info["has_custom_certificate"] is False
        assert info["pending_update_count"] == 5
        assert info["max_connections"] == 40
        assert info["allowed_updates"] == ["message", "callback_query"]


# ---------------------------------------------------------------------------
# Config Integration Tests
# ---------------------------------------------------------------------------


class TestConfigIntegration:
    """Tests for config.py integration with telegram_bot.py."""

    def test_bot_config_to_telegram_config(self) -> None:
        """Test converting BotConfig fields to TelegramBotConfig."""
        from claude_session_player.watcher.config import BotConfig

        bot_config = BotConfig(
            telegram_token="test_token",
            telegram_mode="polling",
            telegram_webhook_url="https://example.com",
        )

        telegram_config = TelegramBotConfig.from_dict({
            "token": bot_config.telegram_token,
            "mode": bot_config.telegram_mode,
            "webhook_url": bot_config.telegram_webhook_url,
        })

        assert telegram_config is not None
        assert telegram_config.token == "test_token"
        assert telegram_config.mode == "polling"
        assert telegram_config.webhook_url == "https://example.com"

    def test_bot_config_serialization(self) -> None:
        """Test BotConfig serialization with telegram mode fields."""
        from claude_session_player.watcher.config import BotConfig

        bot_config = BotConfig(
            telegram_token="test_token",
            telegram_mode="polling",
            telegram_webhook_url="https://example.com",
        )

        data = bot_config.to_dict()

        assert data["telegram"]["token"] == "test_token"
        assert data["telegram"]["mode"] == "polling"
        assert data["telegram"]["webhook_url"] == "https://example.com"

    def test_bot_config_serialization_webhook_default(self) -> None:
        """Test BotConfig serialization omits default webhook mode."""
        from claude_session_player.watcher.config import BotConfig

        bot_config = BotConfig(
            telegram_token="test_token",
            telegram_mode="webhook",  # Default
            telegram_webhook_url="https://example.com",
        )

        data = bot_config.to_dict()

        assert "mode" not in data["telegram"]  # Omitted because it's default
        assert data["telegram"]["token"] == "test_token"
        assert data["telegram"]["webhook_url"] == "https://example.com"

    def test_bot_config_deserialization(self) -> None:
        """Test BotConfig deserialization with telegram mode fields."""
        from claude_session_player.watcher.config import BotConfig

        data = {
            "telegram": {
                "token": "test_token",
                "mode": "polling",
                "webhook_url": "https://example.com",
            }
        }

        bot_config = BotConfig.from_dict(data)

        assert bot_config.telegram_token == "test_token"
        assert bot_config.telegram_mode == "polling"
        assert bot_config.telegram_webhook_url == "https://example.com"

    def test_bot_config_deserialization_defaults(self) -> None:
        """Test BotConfig deserialization uses defaults for missing fields."""
        from claude_session_player.watcher.config import BotConfig

        data = {
            "telegram": {
                "token": "test_token",
            }
        }

        bot_config = BotConfig.from_dict(data)

        assert bot_config.telegram_token == "test_token"
        assert bot_config.telegram_mode == "webhook"  # Default
        assert bot_config.telegram_webhook_url is None


# ---------------------------------------------------------------------------
# Bot Commands Tests
# ---------------------------------------------------------------------------


class TestBotCommandsRegistration:
    """Tests for bot commands registration."""

    def test_default_commands_content(self) -> None:
        """Test default commands have correct content."""
        cmd_map = {cmd.command: cmd.description for cmd in DEFAULT_BOT_COMMANDS}

        assert "search" in cmd_map
        assert "Search sessions" in cmd_map["search"]

        assert "projects" in cmd_map
        assert "Browse" in cmd_map["projects"]

        assert "recent" in cmd_map
        assert "recent" in cmd_map["recent"].lower()

    def test_custom_commands(self) -> None:
        """Test using custom commands list."""
        custom_commands = [
            BotCommandDef("help", "Get help"),
            BotCommandDef("status", "Check status"),
        ]

        assert len(custom_commands) == 2
        assert custom_commands[0].command == "help"
        assert custom_commands[1].command == "status"


# ---------------------------------------------------------------------------
# Question Callback Handler Tests
# ---------------------------------------------------------------------------


class TestCreateQuestionCallbackHandler:
    """Tests for create_question_callback_handler function."""

    @pytest.mark.asyncio
    async def test_handler_answers_question_callback(self) -> None:
        """Handler answers callback with CLI message."""
        handler = create_question_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "q:tool-123:0:1"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_called_once_with(
            text="Please respond to this question in the Claude CLI",
            show_alert=False,
        )

    @pytest.mark.asyncio
    async def test_handler_ignores_non_question_callbacks(self) -> None:
        """Handler ignores callbacks not starting with q:."""
        handler = create_question_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "search:page:2"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_ignores_empty_callback_data(self) -> None:
        """Handler ignores callbacks with no data."""
        handler = create_question_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = None
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_ignores_empty_string_callback_data(self) -> None:
        """Handler ignores callbacks with empty string data."""
        handler = create_question_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = ""
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Noop Callback Handler Tests
# ---------------------------------------------------------------------------


class TestCreateNoopCallbackHandler:
    """Tests for create_noop_callback_handler function."""

    @pytest.mark.asyncio
    async def test_handler_acknowledges_noop_callback(self) -> None:
        """Handler acknowledges noop callback silently."""
        handler = create_noop_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "noop"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handler_ignores_other_callbacks(self) -> None:
        """Handler ignores non-noop callbacks."""
        handler = create_noop_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "extend:123"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()


# ---------------------------------------------------------------------------
# Extend TTL Callback Handler Tests
# ---------------------------------------------------------------------------


class TestCreateExtendTTLCallbackHandler:
    """Tests for create_extend_ttl_callback_handler function."""

    @pytest.mark.asyncio
    async def test_handler_extends_ttl_successfully(self) -> None:
        """Handler calls on_extend and shows success toast."""
        on_extend = AsyncMock(return_value=True)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_message = MagicMock()
        mock_message.chat.id = 123456789

        mock_callback = AsyncMock()
        mock_callback.data = "extend:42"
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_called_once_with("123456789", "42")
        mock_callback.answer.assert_called_once_with(
            text="+30s added", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_handler_handles_binding_not_found(self) -> None:
        """Handler shows error toast when binding not found."""
        on_extend = AsyncMock(return_value=False)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_message = MagicMock()
        mock_message.chat.id = 123456789

        mock_callback = AsyncMock()
        mock_callback.data = "extend:42"
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_called_once_with("123456789", "42")
        mock_callback.answer.assert_called_once_with(
            text="Session not found", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_handler_ignores_non_extend_callbacks(self) -> None:
        """Handler ignores callbacks not starting with extend:."""
        on_extend = AsyncMock(return_value=True)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_callback = AsyncMock()
        mock_callback.data = "q:tool-123:0:1"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_not_called()
        mock_callback.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_handles_missing_message(self) -> None:
        """Handler shows error when message is missing."""
        on_extend = AsyncMock(return_value=True)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_callback = AsyncMock()
        mock_callback.data = "extend:42"
        mock_callback.message = None
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_not_called()
        mock_callback.answer.assert_called_once_with(
            text="Unable to find chat", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_handler_handles_empty_message_id(self) -> None:
        """Handler shows error for empty message_id after colon."""
        on_extend = AsyncMock(return_value=True)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_message = MagicMock()
        mock_message.chat.id = 123456789

        mock_callback = AsyncMock()
        mock_callback.data = "extend:"  # Empty message_id
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        # Should call on_extend with empty string
        on_extend.assert_called_once_with("123456789", "")

    @pytest.mark.asyncio
    async def test_handler_handles_negative_chat_id(self) -> None:
        """Handler handles negative chat IDs (group chats)."""
        on_extend = AsyncMock(return_value=True)
        handler = create_extend_ttl_callback_handler(on_extend)

        mock_message = MagicMock()
        mock_message.chat.id = -1001234567890  # Supergroup ID

        mock_callback = AsyncMock()
        mock_callback.data = "extend:99"
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_called_once_with("-1001234567890", "99")
        mock_callback.answer.assert_called_once_with(
            text="+30s added", show_alert=False
        )


# ---------------------------------------------------------------------------
# Combined Callback Handler Tests
# ---------------------------------------------------------------------------


class TestCreateCombinedCallbackHandler:
    """Tests for create_combined_callback_handler function."""

    @pytest.mark.asyncio
    async def test_handles_question_callback(self) -> None:
        """Combined handler handles question callbacks."""
        handler = create_combined_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "q:tool-123:0:1"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_called_once_with(
            text="Please respond to this question in the Claude CLI",
            show_alert=False,
        )

    @pytest.mark.asyncio
    async def test_handles_noop_callback(self) -> None:
        """Combined handler handles noop callbacks."""
        handler = create_combined_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "noop"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_handles_extend_callback_with_handler(self) -> None:
        """Combined handler handles extend callbacks when on_extend provided."""
        on_extend = AsyncMock(return_value=True)
        handler = create_combined_callback_handler(on_extend=on_extend)

        mock_message = MagicMock()
        mock_message.chat.id = 123456789

        mock_callback = AsyncMock()
        mock_callback.data = "extend:42"
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        on_extend.assert_called_once_with("123456789", "42")
        mock_callback.answer.assert_called_once_with(
            text="+30s added", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_handles_extend_callback_without_handler(self) -> None:
        """Combined handler shows error when extend called without on_extend."""
        handler = create_combined_callback_handler()  # No on_extend

        mock_message = MagicMock()
        mock_message.chat.id = 123456789

        mock_callback = AsyncMock()
        mock_callback.data = "extend:42"
        mock_callback.message = mock_message
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_called_once_with(
            text="Not configured", show_alert=False
        )

    @pytest.mark.asyncio
    async def test_ignores_empty_callback_data(self) -> None:
        """Combined handler ignores callbacks with no data."""
        handler = create_combined_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = None
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_unknown_callback_data(self) -> None:
        """Combined handler ignores unknown callback types."""
        handler = create_combined_callback_handler()

        mock_callback = AsyncMock()
        mock_callback.data = "unknown:data"
        mock_callback.answer = AsyncMock()

        await handler(mock_callback)

        mock_callback.answer.assert_not_called()
