"""Bot router for Slack and Telegram webhook routing.

This module provides:
- BotRouter: Routes incoming webhooks from Slack and Telegram to appropriate handlers
- verify_slack_signature(): Verifies Slack request signatures using HMAC-SHA256
- register_bot_routes(): Registers bot webhook routes on an aiohttp application

Endpoint Reference:
- POST /slack/commands: Slack slash commands
- POST /slack/interactions: Slack button clicks, menu selections
- POST /telegram/webhook: All Telegram updates (messages, callbacks)

Security:
- Slack: HMAC-SHA256 signature verification with timestamp validation
- Telegram: No built-in signature; security via secret webhook URL path
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

if TYPE_CHECKING:
    from claude_session_player.watcher.config import BotConfig

logger = logging.getLogger(__name__)

# Type aliases for command handlers
# SlackCommandHandler receives: command, text, user_id, channel_id, response_url
SlackCommandHandler = Callable[
    [str, str, str, str, str], Awaitable[Optional[dict[str, Any]]]
]
# SlackInteractionHandler receives: action_id, value, payload
SlackInteractionHandler = Callable[
    [str, Optional[str], dict[str, Any]], Awaitable[None]
]
# TelegramCommandHandler receives: command, args, chat_id, message_id, thread_id
TelegramCommandHandler = Callable[[str, str, int, int, Optional[int]], Awaitable[None]]
# TelegramCallbackHandler receives: callback_data, chat_id, message_id, callback_query_id, thread_id
TelegramCallbackHandler = Callable[[str, int, int, str, Optional[int]], Awaitable[None]]


# Maximum age for Slack request timestamps (5 minutes in seconds)
SLACK_TIMESTAMP_MAX_AGE = 300


def verify_slack_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str,
) -> bool:
    """Verify a Slack request signature.

    Slack signs requests with HMAC-SHA256 using the signing secret.
    The signature is computed over "v0:{timestamp}:{body}".

    Args:
        body: Raw request body bytes.
        timestamp: X-Slack-Request-Timestamp header value.
        signature: X-Slack-Signature header value (format: "v0=...").
        signing_secret: Slack app signing secret.

    Returns:
        True if signature is valid and timestamp is recent, False otherwise.
    """
    if not timestamp or not signature:
        return False

    # Check timestamp is recent (within 5 minutes)
    try:
        request_time = int(timestamp)
        current_time = int(time.time())
        if abs(current_time - request_time) > SLACK_TIMESTAMP_MAX_AGE:
            logger.warning(
                "Slack timestamp too old: %d (current: %d)", request_time, current_time
            )
            return False
    except ValueError:
        logger.warning("Invalid Slack timestamp: %s", timestamp)
        return False

    # Compute expected signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_sig = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_sig, signature):
        logger.warning("Slack signature mismatch")
        return False

    return True


@dataclass
class BotRouter:
    """Routes incoming webhooks from Slack and Telegram to handlers.

    Handles signature verification for Slack requests and parses payloads
    for both platforms. Routes commands and interactions to registered handlers.

    Example:
        router = BotRouter(bot_config)

        # Register handlers
        router.register_slack_command("/search", handle_search)
        router.register_telegram_command("search", handle_search)

        # Register routes on app
        register_bot_routes(app, router)
    """

    bot_config: BotConfig

    # Handler registries
    _slack_command_handlers: dict[str, SlackCommandHandler] = field(
        default_factory=dict, repr=False
    )
    _slack_interaction_handlers: dict[str, SlackInteractionHandler] = field(
        default_factory=dict, repr=False
    )
    _telegram_command_handlers: dict[str, TelegramCommandHandler] = field(
        default_factory=dict, repr=False
    )
    _telegram_callback_handlers: dict[str, TelegramCallbackHandler] = field(
        default_factory=dict, repr=False
    )

    def register_slack_command(
        self, command: str, handler: SlackCommandHandler
    ) -> None:
        """Register a handler for a Slack slash command.

        Args:
            command: Command name including leading slash (e.g., "/search").
            handler: Async function to handle the command.
        """
        self._slack_command_handlers[command] = handler

    def register_slack_interaction(
        self, action_prefix: str, handler: SlackInteractionHandler
    ) -> None:
        """Register a handler for Slack interactions by action_id prefix.

        Args:
            action_prefix: Prefix for action_id (e.g., "watch:" matches "watch:abc123").
            handler: Async function to handle the interaction.
        """
        self._slack_interaction_handlers[action_prefix] = handler

    def register_telegram_command(
        self, command: str, handler: TelegramCommandHandler
    ) -> None:
        """Register a handler for a Telegram bot command.

        Args:
            command: Command name without leading slash (e.g., "search").
            handler: Async function to handle the command.
        """
        self._telegram_command_handlers[command] = handler

    def register_telegram_callback(
        self, action_prefix: str, handler: TelegramCallbackHandler
    ) -> None:
        """Register a handler for Telegram callback queries by data prefix.

        Args:
            action_prefix: Prefix for callback_data (e.g., "w:" matches "w:0:abc").
            handler: Async function to handle the callback.
        """
        self._telegram_callback_handlers[action_prefix] = handler

    async def handle_slack_command(self, request: web.Request) -> web.Response:
        """Handle POST /slack/commands - Slack slash commands.

        Verifies request signature, parses form data, and routes to
        the appropriate command handler.

        Args:
            request: aiohttp Request object.

        Returns:
            200 OK if valid and handler found.
            400 Bad Request if unknown command.
            401 Unauthorized if signature verification fails.
        """
        # Read body for signature verification
        body = await request.read()

        # Verify signature
        if not self.bot_config.slack_signing_secret:
            logger.warning("Slack signing secret not configured")
            return web.Response(status=401, text="Signing secret not configured")

        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")

        if not verify_slack_signature(
            body, timestamp, signature, self.bot_config.slack_signing_secret
        ):
            return web.Response(status=401, text="Invalid signature")

        # Parse form data
        # Note: We can't use request.post() after reading body, so parse manually
        try:
            form_data = _parse_form_data(body.decode("utf-8"))
        except Exception as e:
            logger.warning("Failed to parse Slack command form data: %s", e)
            return web.Response(status=400, text="Invalid form data")

        command = form_data.get("command", "")
        text = form_data.get("text", "")
        user_id = form_data.get("user_id", "")
        channel_id = form_data.get("channel_id", "")
        response_url = form_data.get("response_url", "")

        logger.info(
            "Received Slack command: %s %s from user %s in %s",
            command,
            text,
            user_id,
            channel_id,
        )

        # Find handler
        handler = self._slack_command_handlers.get(command)
        if not handler:
            logger.warning("Unknown Slack command: %s", command)
            return web.Response(status=400, text=f"Unknown command: {command}")

        # Call handler - returns immediate response or None for async processing
        try:
            immediate_response = await handler(
                command, text, user_id, channel_id, response_url
            )
            if immediate_response:
                return web.json_response(immediate_response)
            return web.Response(status=200)
        except Exception as e:
            logger.exception("Error handling Slack command %s: %s", command, e)
            return web.Response(status=200)  # Slack expects 200 even on errors

    async def handle_slack_interaction(self, request: web.Request) -> web.Response:
        """Handle POST /slack/interactions - button clicks, menu selections.

        Verifies request signature, parses JSON payload from form data,
        and routes to the appropriate interaction handler.

        Args:
            request: aiohttp Request object.

        Returns:
            200 OK if valid and handler found.
            400 Bad Request if invalid payload.
            401 Unauthorized if signature verification fails.
        """
        # Read body for signature verification
        body = await request.read()

        # Verify signature
        if not self.bot_config.slack_signing_secret:
            logger.warning("Slack signing secret not configured")
            return web.Response(status=401, text="Signing secret not configured")

        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")

        if not verify_slack_signature(
            body, timestamp, signature, self.bot_config.slack_signing_secret
        ):
            return web.Response(status=401, text="Invalid signature")

        # Parse form data to get payload JSON
        try:
            form_data = _parse_form_data(body.decode("utf-8"))
            payload_str = form_data.get("payload", "")
            if not payload_str:
                return web.Response(status=400, text="Missing payload")
            payload = json.loads(payload_str)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse Slack interaction payload: %s", e)
            return web.Response(status=400, text="Invalid payload")

        # Extract action info
        actions = payload.get("actions", [])
        if not actions:
            logger.warning("No actions in Slack interaction payload")
            return web.Response(status=400, text="No actions")

        action = actions[0]
        action_id = action.get("action_id", "")
        # Value can be in 'value' or 'selected_option.value'
        value = action.get("value")
        if value is None:
            selected_option = action.get("selected_option", {})
            value = selected_option.get("value")

        logger.info("Received Slack interaction: action_id=%s value=%s", action_id, value)

        # Find handler by prefix match
        handler = None
        for prefix, h in self._slack_interaction_handlers.items():
            if action_id.startswith(prefix) or action_id == prefix:
                handler = h
                break

        if not handler:
            logger.warning("No handler for Slack interaction: %s", action_id)
            return web.Response(status=200)  # Acknowledge even without handler

        # Call handler
        try:
            await handler(action_id, value, payload)
        except Exception as e:
            logger.exception("Error handling Slack interaction %s: %s", action_id, e)

        return web.Response(status=200)

    async def handle_telegram_webhook(self, request: web.Request) -> web.Response:
        """Handle POST /telegram/webhook - all Telegram updates.

        Parses Update JSON and routes message commands and callback queries
        to the appropriate handlers.

        Args:
            request: aiohttp Request object.

        Returns:
            200 OK always (Telegram expects this).
        """
        try:
            update = await request.json()
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse Telegram update: %s", e)
            return web.Response(status=200)  # Telegram expects 200 even on errors

        # Handle message with text (commands)
        message = update.get("message")
        if message and message.get("text"):
            text = message["text"]
            chat = message.get("chat", {})
            chat_id = chat.get("id", 0)
            message_id = message.get("message_id", 0)
            # Extract thread_id for supergroup topics
            thread_id = message.get("message_thread_id")

            # Check if it's a command (starts with /)
            if text.startswith("/"):
                # Parse command and args
                parts = text.split(maxsplit=1)
                command_part = parts[0][1:]  # Remove leading /
                # Handle @botname suffix in groups
                if "@" in command_part:
                    command_part = command_part.split("@")[0]
                args = parts[1] if len(parts) > 1 else ""

                logger.info(
                    "Received Telegram command: /%s %s from chat %s (thread=%s)",
                    command_part,
                    args,
                    chat_id,
                    thread_id,
                )

                # Find handler
                handler = self._telegram_command_handlers.get(command_part)
                if handler:
                    try:
                        await handler(command_part, args, chat_id, message_id, thread_id)
                    except Exception as e:
                        logger.exception(
                            "Error handling Telegram command %s: %s", command_part, e
                        )
                else:
                    logger.debug("No handler for Telegram command: %s", command_part)

        # Handle callback query (button clicks)
        callback_query = update.get("callback_query")
        if callback_query:
            callback_data = callback_query.get("data", "")
            callback_id = callback_query.get("id", "")
            callback_message = callback_query.get("message", {})
            chat = callback_message.get("chat", {})
            chat_id = chat.get("id", 0)
            message_id = callback_message.get("message_id", 0)
            # Extract thread_id from the message that contains the button
            thread_id = callback_message.get("message_thread_id")

            logger.info(
                "Received Telegram callback: data=%s from chat %s (thread=%s)",
                callback_data,
                chat_id,
                thread_id,
            )

            # Find handler by prefix match
            handler = None
            for prefix, h in self._telegram_callback_handlers.items():
                if callback_data.startswith(prefix):
                    handler = h
                    break

            if handler:
                try:
                    await handler(callback_data, chat_id, message_id, callback_id, thread_id)
                except Exception as e:
                    logger.exception(
                        "Error handling Telegram callback %s: %s", callback_data, e
                    )
            else:
                logger.debug("No handler for Telegram callback: %s", callback_data)

        return web.Response(status=200)


def _parse_form_data(data: str) -> dict[str, str]:
    """Parse URL-encoded form data.

    Args:
        data: URL-encoded string (key1=value1&key2=value2).

    Returns:
        Dict mapping keys to decoded values.
    """
    from urllib.parse import parse_qs, unquote_plus

    parsed = parse_qs(data, keep_blank_values=True)
    # parse_qs returns lists, we want single values
    return {k: unquote_plus(v[0]) if v else "" for k, v in parsed.items()}


def register_bot_routes(app: web.Application, router: BotRouter) -> None:
    """Register Slack and Telegram webhook routes on an aiohttp application.

    Args:
        app: aiohttp Application to register routes on.
        router: BotRouter instance to handle requests.
    """
    app.router.add_post("/slack/commands", router.handle_slack_command)
    app.router.add_post("/slack/interactions", router.handle_slack_interaction)
    app.router.add_post("/telegram/webhook", router.handle_telegram_webhook)
