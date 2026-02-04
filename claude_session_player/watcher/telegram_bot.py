"""Telegram bot initialization with webhook setup and polling fallback.

This module provides:
- setup_telegram_webhook(): Configure bot to receive updates via webhooks
- start_telegram_polling(): Start long-polling for local development
- initialize_telegram_bot(): Mode selection based on config
- shutdown_telegram_bot(): Graceful cleanup

Webhook mode is more efficient for production but requires a public HTTPS endpoint.
Polling mode is simpler for local development without a public URL.

Configuration (config.yaml):
    bots:
      telegram:
        token: "BOT_TOKEN"
        mode: webhook           # "webhook" or "polling"
        webhook_url: "https://your-server.com"  # Required if mode=webhook
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bot Command Definitions
# ---------------------------------------------------------------------------


@dataclass
class BotCommandDef:
    """Definition of a bot command shown in Telegram UI."""

    command: str
    description: str


# Commands visible in Telegram's command menu
DEFAULT_BOT_COMMANDS: list[BotCommandDef] = [
    BotCommandDef("search", "Search sessions: /search [query]"),
    BotCommandDef("projects", "Browse all projects"),
    BotCommandDef("recent", "Show recent sessions"),
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class TelegramBotConfig:
    """Configuration for Telegram bot initialization."""

    token: str
    mode: str = "webhook"  # "webhook" or "polling"
    webhook_url: str | None = None
    allowed_updates: list[str] = field(
        default_factory=lambda: ["message", "callback_query"]
    )
    drop_pending_updates: bool = True

    def validate(self) -> None:
        """Validate configuration.

        Raises:
            ValueError: If configuration is invalid.
        """
        if not self.token:
            raise ValueError("Telegram bot token is required")

        if self.mode not in ("webhook", "polling"):
            raise ValueError(f"Unknown Telegram mode: {self.mode}")

        if self.mode == "webhook" and not self.webhook_url:
            raise ValueError("webhook_url is required when mode=webhook")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TelegramBotConfig | None:
        """Create config from dict (e.g., from YAML config).

        Args:
            data: Dict with telegram bot config fields.

        Returns:
            TelegramBotConfig or None if token not present.
        """
        token = data.get("token")
        if not token:
            return None

        return cls(
            token=token,
            mode=data.get("mode", "webhook"),
            webhook_url=data.get("webhook_url"),
            allowed_updates=data.get("allowed_updates", ["message", "callback_query"]),
            drop_pending_updates=data.get("drop_pending_updates", True),
        )


# ---------------------------------------------------------------------------
# Webhook URL Construction
# ---------------------------------------------------------------------------


def build_webhook_url(base_url: str, path: str = "/telegram/webhook") -> str:
    """Build the full webhook URL.

    Args:
        base_url: Base URL (e.g., "https://your-server.com").
        path: Webhook path (default "/telegram/webhook").

    Returns:
        Full webhook URL.
    """
    # Remove trailing slash from base URL
    base = base_url.rstrip("/")
    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


# ---------------------------------------------------------------------------
# Webhook Setup
# ---------------------------------------------------------------------------


async def setup_telegram_webhook(
    bot_token: str,
    webhook_url: str,
    allowed_updates: list[str] | None = None,
    drop_pending_updates: bool = True,
    commands: list[BotCommandDef] | None = None,
) -> Bot:
    """Configure Telegram bot to use webhooks.

    Sets the webhook URL and registers bot commands visible in Telegram UI.

    Args:
        bot_token: Telegram bot token from BotFather.
        webhook_url: Base URL for webhook (e.g., "https://your-server.com").
        allowed_updates: Update types to receive (default: message, callback_query).
        drop_pending_updates: Don't process old messages on restart.
        commands: Bot commands to register (default: search, projects, recent).

    Returns:
        Configured Bot instance.

    Raises:
        ImportError: If aiogram is not installed.
        TelegramAPIError: If webhook setup fails.
    """
    try:
        from aiogram import Bot
        from aiogram.types import BotCommand
    except ImportError as e:
        raise ImportError(
            "aiogram library not installed. Install with: pip install aiogram"
        ) from e

    if allowed_updates is None:
        allowed_updates = ["message", "callback_query"]

    if commands is None:
        commands = DEFAULT_BOT_COMMANDS

    bot = Bot(token=bot_token)

    # Build full webhook URL
    full_webhook_url = build_webhook_url(webhook_url)

    # Set webhook URL
    await bot.set_webhook(
        url=full_webhook_url,
        allowed_updates=allowed_updates,
        drop_pending_updates=drop_pending_updates,
    )

    # Register bot commands (shown in Telegram UI)
    bot_commands = [
        BotCommand(command=cmd.command, description=cmd.description)
        for cmd in commands
    ]
    await bot.set_my_commands(bot_commands)

    logger.info(f"Telegram webhook configured: {full_webhook_url}")
    logger.info(f"Registered {len(bot_commands)} bot commands")

    return bot


async def delete_telegram_webhook(bot: Bot) -> None:
    """Delete the webhook from Telegram.

    Args:
        bot: Bot instance to delete webhook for.
    """
    await bot.delete_webhook()
    logger.info("Telegram webhook deleted")


# ---------------------------------------------------------------------------
# Polling Mode
# ---------------------------------------------------------------------------


# Type alias for message handler
# Using Any to avoid import dependency on aiogram at runtime
MessageHandler = Callable[[Any], Awaitable[None]]
CallbackHandler = Callable[[Any], Awaitable[None]]


@dataclass
class TelegramPollingRunner:
    """Runner for Telegram polling mode.

    Manages the dispatcher and polling task for local development.
    """

    bot: Bot
    dispatcher: Dispatcher
    polling_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start polling in background task."""
        if self.polling_task is not None:
            logger.warning("Polling already started")
            return

        logger.info("Starting Telegram polling mode")

        # Start polling in background task
        self.polling_task = asyncio.create_task(
            self._run_polling(),
            name="telegram_polling",
        )

    async def _run_polling(self) -> None:
        """Run the polling loop."""
        try:
            await self.dispatcher.start_polling(self.bot)
        except asyncio.CancelledError:
            logger.info("Telegram polling cancelled")
        except Exception as e:
            logger.exception(f"Telegram polling error: {e}")

    async def stop(self) -> None:
        """Stop polling gracefully."""
        if self.polling_task is None:
            return

        logger.info("Stopping Telegram polling")
        self.polling_task.cancel()

        try:
            await self.polling_task
        except asyncio.CancelledError:
            pass

        self.polling_task = None
        logger.info("Telegram polling stopped")


async def start_telegram_polling(
    bot_token: str,
    message_handler: MessageHandler | None = None,
    callback_handler: CallbackHandler | None = None,
    commands: list[BotCommandDef] | None = None,
) -> TelegramPollingRunner:
    """Start long-polling for local development.

    Creates a bot and dispatcher, registers handlers, and starts polling.
    Use this when you don't have a public HTTPS endpoint for webhooks.

    Args:
        bot_token: Telegram bot token from BotFather.
        message_handler: Optional handler for message updates.
        callback_handler: Optional handler for callback queries.
        commands: Bot commands to register (default: search, projects, recent).

    Returns:
        TelegramPollingRunner to manage the polling lifecycle.

    Raises:
        ImportError: If aiogram is not installed.
    """
    try:
        from aiogram import Bot, Dispatcher
        from aiogram.types import BotCommand
    except ImportError as e:
        raise ImportError(
            "aiogram library not installed. Install with: pip install aiogram"
        ) from e

    if commands is None:
        commands = DEFAULT_BOT_COMMANDS

    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # Register handlers
    if message_handler is not None:
        dp.message.register(message_handler)

    if callback_handler is not None:
        dp.callback_query.register(callback_handler)

    # Delete any existing webhook
    await bot.delete_webhook()

    # Register bot commands (shown in Telegram UI)
    bot_commands = [
        BotCommand(command=cmd.command, description=cmd.description)
        for cmd in commands
    ]
    await bot.set_my_commands(bot_commands)

    logger.info(f"Registered {len(bot_commands)} bot commands for polling mode")

    # Create runner and start
    runner = TelegramPollingRunner(bot=bot, dispatcher=dp)
    await runner.start()

    return runner


# ---------------------------------------------------------------------------
# Mode Selection
# ---------------------------------------------------------------------------


@dataclass
class TelegramBotState:
    """State of the initialized Telegram bot.

    Tracks the mode and references to bot/runner for cleanup.
    """

    mode: str  # "webhook" or "polling"
    bot: Bot
    polling_runner: TelegramPollingRunner | None = None


async def initialize_telegram_bot(
    config: TelegramBotConfig,
    message_handler: MessageHandler | None = None,
    callback_handler: CallbackHandler | None = None,
) -> TelegramBotState | None:
    """Initialize Telegram bot based on config.

    Selects between webhook and polling mode based on config.mode.

    Args:
        config: Telegram bot configuration.
        message_handler: Handler for message updates (polling mode only).
        callback_handler: Handler for callback queries (polling mode only).

    Returns:
        TelegramBotState if initialized, None if not configured.

    Raises:
        ValueError: If configuration is invalid.
        ImportError: If aiogram is not installed.
    """
    # Validate configuration
    config.validate()

    if config.mode == "webhook":
        bot = await setup_telegram_webhook(
            bot_token=config.token,
            webhook_url=config.webhook_url,
            allowed_updates=config.allowed_updates,
            drop_pending_updates=config.drop_pending_updates,
        )
        return TelegramBotState(mode="webhook", bot=bot)

    elif config.mode == "polling":
        runner = await start_telegram_polling(
            bot_token=config.token,
            message_handler=message_handler,
            callback_handler=callback_handler,
        )
        return TelegramBotState(
            mode="polling",
            bot=runner.bot,
            polling_runner=runner,
        )

    # Should not reach here due to validate()
    raise ValueError(f"Unknown mode: {config.mode}")


async def shutdown_telegram_bot(state: TelegramBotState) -> None:
    """Clean shutdown of Telegram bot.

    Cancels polling task (if in polling mode) and closes bot session.

    Args:
        state: Bot state from initialize_telegram_bot().
    """
    logger.info(f"Shutting down Telegram bot (mode={state.mode})")

    if state.polling_runner is not None:
        await state.polling_runner.stop()

    # Close bot session
    await state.bot.session.close()

    logger.info("Telegram bot shutdown complete")


# ---------------------------------------------------------------------------
# Question Callback Handler
# ---------------------------------------------------------------------------


def create_question_callback_handler() -> CallbackHandler:
    """Create a callback handler for question button presses.

    When a user clicks a question option button (callback data starting with "q:"),
    we show a toast message indicating they should respond in the CLI.
    This is informational only - actual responses happen in the CLI.

    Returns:
        Async callback handler function.
    """

    async def handler(callback: CallbackQuery) -> None:
        """Handle question button callback."""
        # Only handle our question callbacks
        if not callback.data or not callback.data.startswith("q:"):
            return

        # Show toast notification to user
        await callback.answer(
            text="Please respond to this question in the Claude CLI",
            show_alert=False,
        )

    return handler


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


async def get_bot_info(bot: Bot) -> dict[str, Any]:
    """Get information about the bot.

    Args:
        bot: Bot instance.

    Returns:
        Dict with bot info (id, username, first_name, etc.).
    """
    me = await bot.get_me()
    return {
        "id": me.id,
        "username": me.username,
        "first_name": me.first_name,
        "can_join_groups": me.can_join_groups,
        "can_read_all_group_messages": me.can_read_all_group_messages,
        "supports_inline_queries": me.supports_inline_queries,
    }


async def get_webhook_info(bot: Bot) -> dict[str, Any]:
    """Get current webhook info for the bot.

    Args:
        bot: Bot instance.

    Returns:
        Dict with webhook info (url, pending_update_count, etc.).
    """
    info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message,
        "max_connections": info.max_connections,
        "allowed_updates": info.allowed_updates,
    }
