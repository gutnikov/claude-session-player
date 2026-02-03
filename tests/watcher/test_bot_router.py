"""Tests for the BotRouter module."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from claude_session_player.watcher.bot_router import (
    SLACK_TIMESTAMP_MAX_AGE,
    BotRouter,
    _parse_form_data,
    register_bot_routes,
    verify_slack_signature,
)
from claude_session_player.watcher.config import BotConfig


# --- Mock HTTP Request/Response ---


@dataclass
class MockRequest:
    """Mock aiohttp request for testing."""

    headers: dict[str, str] = field(default_factory=dict)
    _body: bytes = b""
    _json_data: dict | None = None
    _json_error: bool = False

    async def read(self) -> bytes:
        """Return raw body bytes."""
        return self._body

    async def json(self) -> dict:
        """Return JSON body."""
        if self._json_error:
            raise json.JSONDecodeError("Invalid JSON", "", 0)
        return self._json_data or {}


def make_slack_signature(body: str, timestamp: str, signing_secret: str) -> str:
    """Generate a valid Slack signature for testing."""
    sig_basestring = f"v0:{timestamp}:{body}"
    return (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )


# --- Fixtures ---


@pytest.fixture
def bot_config() -> BotConfig:
    """Create a BotConfig with test credentials."""
    return BotConfig(
        telegram_token="test-telegram-token",
        slack_token="xoxb-test-slack-token",
        slack_signing_secret="test-signing-secret-12345",
    )


@pytest.fixture
def bot_config_no_slack_secret() -> BotConfig:
    """Create a BotConfig without Slack signing secret."""
    return BotConfig(
        telegram_token="test-telegram-token",
        slack_token="xoxb-test-slack-token",
        slack_signing_secret=None,
    )


@pytest.fixture
def router(bot_config: BotConfig) -> BotRouter:
    """Create a BotRouter instance."""
    return BotRouter(bot_config=bot_config)


@pytest.fixture
def current_timestamp() -> str:
    """Return current Unix timestamp as string."""
    return str(int(time.time()))


# --- Tests for verify_slack_signature ---


class TestVerifySlackSignatureValid:
    """Tests for valid Slack signature verification."""

    def test_valid_signature(self) -> None:
        """Valid signature returns True."""
        body = b"command=/search&text=auth"
        timestamp = str(int(time.time()))
        signing_secret = "test-secret"
        signature = make_slack_signature(body.decode(), timestamp, signing_secret)

        result = verify_slack_signature(body, timestamp, signature, signing_secret)

        assert result is True

    def test_valid_signature_with_special_chars(self) -> None:
        """Valid signature with special characters in body returns True."""
        body = b"command=/search&text=auth%20bug%20%22test%22"
        timestamp = str(int(time.time()))
        signing_secret = "test-secret-abc123"
        signature = make_slack_signature(body.decode(), timestamp, signing_secret)

        result = verify_slack_signature(body, timestamp, signature, signing_secret)

        assert result is True


class TestVerifySlackSignatureInvalid:
    """Tests for invalid Slack signature verification."""

    def test_invalid_signature(self) -> None:
        """Invalid signature returns False."""
        body = b"command=/search&text=auth"
        timestamp = str(int(time.time()))
        signing_secret = "test-secret"
        wrong_signature = "v0=invalid_signature_hash"

        result = verify_slack_signature(body, timestamp, wrong_signature, signing_secret)

        assert result is False

    def test_tampered_body(self) -> None:
        """Signature for different body returns False."""
        original_body = b"command=/search&text=auth"
        tampered_body = b"command=/search&text=hack"
        timestamp = str(int(time.time()))
        signing_secret = "test-secret"
        signature = make_slack_signature(original_body.decode(), timestamp, signing_secret)

        result = verify_slack_signature(tampered_body, timestamp, signature, signing_secret)

        assert result is False

    def test_wrong_signing_secret(self) -> None:
        """Signature with different secret returns False."""
        body = b"command=/search&text=auth"
        timestamp = str(int(time.time()))
        signature = make_slack_signature(body.decode(), timestamp, "correct-secret")

        result = verify_slack_signature(body, timestamp, signature, "wrong-secret")

        assert result is False


class TestVerifySlackSignatureExpiredTimestamp:
    """Tests for Slack signature with expired timestamp."""

    def test_old_timestamp(self) -> None:
        """Timestamp older than 5 minutes returns False."""
        body = b"command=/search&text=auth"
        old_timestamp = str(int(time.time()) - SLACK_TIMESTAMP_MAX_AGE - 60)  # 6 minutes old
        signing_secret = "test-secret"
        signature = make_slack_signature(body.decode(), old_timestamp, signing_secret)

        result = verify_slack_signature(body, old_timestamp, signature, signing_secret)

        assert result is False

    def test_future_timestamp(self) -> None:
        """Timestamp more than 5 minutes in future returns False."""
        body = b"command=/search&text=auth"
        future_timestamp = str(int(time.time()) + SLACK_TIMESTAMP_MAX_AGE + 60)  # 6 minutes future
        signing_secret = "test-secret"
        signature = make_slack_signature(body.decode(), future_timestamp, signing_secret)

        result = verify_slack_signature(body, future_timestamp, signature, signing_secret)

        assert result is False

    def test_timestamp_at_boundary(self) -> None:
        """Timestamp exactly at 5 minute boundary returns True."""
        body = b"command=/search&text=auth"
        # 4 minutes 59 seconds old should be OK
        boundary_timestamp = str(int(time.time()) - SLACK_TIMESTAMP_MAX_AGE + 1)
        signing_secret = "test-secret"
        signature = make_slack_signature(body.decode(), boundary_timestamp, signing_secret)

        result = verify_slack_signature(body, boundary_timestamp, signature, signing_secret)

        assert result is True


class TestVerifySlackSignatureMissingFields:
    """Tests for Slack signature with missing fields."""

    def test_missing_timestamp(self) -> None:
        """Missing timestamp returns False."""
        body = b"command=/search&text=auth"
        signature = "v0=somehash"
        signing_secret = "test-secret"

        result = verify_slack_signature(body, None, signature, signing_secret)

        assert result is False

    def test_missing_signature(self) -> None:
        """Missing signature returns False."""
        body = b"command=/search&text=auth"
        timestamp = str(int(time.time()))
        signing_secret = "test-secret"

        result = verify_slack_signature(body, timestamp, None, signing_secret)

        assert result is False

    def test_empty_timestamp(self) -> None:
        """Empty timestamp returns False."""
        body = b"command=/search&text=auth"
        signing_secret = "test-secret"

        result = verify_slack_signature(body, "", "v0=hash", signing_secret)

        assert result is False

    def test_invalid_timestamp_format(self) -> None:
        """Non-numeric timestamp returns False."""
        body = b"command=/search&text=auth"
        signing_secret = "test-secret"

        result = verify_slack_signature(body, "not-a-number", "v0=hash", signing_secret)

        assert result is False


# --- Tests for BotRouter Slack command handling ---


class TestSlackCommandRouting:
    """Tests for Slack command routing."""

    async def test_route_search_command(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Route /search command to registered handler."""
        # Register handler
        handler_called = False
        handler_args: tuple = ()

        async def search_handler(
            command: str, text: str, user_id: str, channel_id: str, response_url: str
        ) -> dict | None:
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (command, text, user_id, channel_id, response_url)
            return None

        router.register_slack_command("/search", search_handler)

        # Create valid request
        body = "command=%2Fsearch&text=auth+bug&user_id=U123&channel_id=C456&response_url=https%3A%2F%2Fhooks.slack.com%2Ftest"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 200
        assert handler_called
        assert handler_args[0] == "/search"
        assert handler_args[1] == "auth bug"
        assert handler_args[2] == "U123"
        assert handler_args[3] == "C456"
        assert "hooks.slack.com" in handler_args[4]

    async def test_handler_returns_immediate_response(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Handler can return an immediate response dict."""
        async def handler(
            command: str, text: str, user_id: str, channel_id: str, response_url: str
        ) -> dict:
            return {"text": "Processing...", "response_type": "ephemeral"}

        router.register_slack_command("/search", handler)

        body = "command=%2Fsearch&text=test"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 200
        assert response.content_type == "application/json"

    async def test_unknown_command_returns_400(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Unknown command returns 400."""
        body = "command=%2Funknown&text=test"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 400


class TestSlackCommandSignatureVerification:
    """Tests for Slack command signature verification."""

    async def test_invalid_signature_returns_401(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Invalid signature returns 401."""
        body = "command=%2Fsearch&text=test"
        invalid_signature = "v0=invalid"

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": invalid_signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 401

    async def test_expired_timestamp_returns_401(
        self, router: BotRouter
    ) -> None:
        """Expired timestamp returns 401."""
        old_timestamp = str(int(time.time()) - 600)  # 10 minutes old
        body = "command=%2Fsearch&text=test"
        signature = make_slack_signature(
            body, old_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": old_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 401

    async def test_no_signing_secret_returns_401(
        self, bot_config_no_slack_secret: BotConfig, current_timestamp: str
    ) -> None:
        """No signing secret configured returns 401."""
        router = BotRouter(bot_config=bot_config_no_slack_secret)
        body = "command=%2Fsearch&text=test"

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": "v0=hash",
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_command(request)

        assert response.status == 401


# --- Tests for BotRouter Slack interaction handling ---


class TestSlackInteractionRouting:
    """Tests for Slack interaction routing."""

    async def test_route_watch_action(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Route watch button action to registered handler."""
        handler_called = False
        handler_args: tuple = ()

        async def watch_handler(
            action_id: str, value: str | None, payload: dict
        ) -> None:
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (action_id, value, payload)

        router.register_slack_interaction("watch:", watch_handler)

        payload = {
            "type": "block_actions",
            "actions": [
                {"action_id": "watch:session123", "value": "abc123"}
            ],
            "channel": {"id": "C456"},
            "user": {"id": "U123"},
        }
        body = f"payload={json.dumps(payload)}"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_interaction(request)

        assert response.status == 200
        assert handler_called
        assert handler_args[0] == "watch:session123"
        assert handler_args[1] == "abc123"
        assert handler_args[2]["channel"]["id"] == "C456"

    async def test_selected_option_value(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Extract value from selected_option for dropdown menus."""
        handler_called = False
        received_value: str | None = None

        async def handler(action_id: str, value: str | None, payload: dict) -> None:
            nonlocal handler_called, received_value
            handler_called = True
            received_value = value

        router.register_slack_interaction("select:", handler)

        payload = {
            "type": "block_actions",
            "actions": [
                {
                    "action_id": "select:menu",
                    "selected_option": {"value": "option1"}
                }
            ],
        }
        body = f"payload={json.dumps(payload)}"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        await router.handle_slack_interaction(request)

        assert handler_called
        assert received_value == "option1"

    async def test_no_handler_returns_200(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """No handler for action still returns 200 to acknowledge."""
        payload = {
            "type": "block_actions",
            "actions": [{"action_id": "unknown:action", "value": "test"}],
        }
        body = f"payload={json.dumps(payload)}"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_interaction(request)

        # Slack expects 200 even without handler
        assert response.status == 200


# --- Tests for BotRouter Telegram webhook handling ---


class TestTelegramMessageCommandRouting:
    """Tests for Telegram message command routing."""

    async def test_route_search_command(self, router: BotRouter) -> None:
        """Route /search command to registered handler."""
        handler_called = False
        handler_args: tuple = ()

        async def search_handler(
            command: str, args: str, chat_id: int, message_id: int
        ) -> None:
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (command, args, chat_id, message_id)

        router.register_telegram_command("search", search_handler)

        request = MockRequest(
            _json_data={
                "update_id": 123456789,
                "message": {
                    "message_id": 100,
                    "chat": {"id": 987654321},
                    "text": "/search auth bug",
                },
            }
        )

        response = await router.handle_telegram_webhook(request)

        assert response.status == 200
        assert handler_called
        assert handler_args[0] == "search"
        assert handler_args[1] == "auth bug"
        assert handler_args[2] == 987654321
        assert handler_args[3] == 100

    async def test_command_without_args(self, router: BotRouter) -> None:
        """Route command without arguments."""
        received_args: str | None = None

        async def handler(command: str, args: str, chat_id: int, message_id: int) -> None:
            nonlocal received_args
            received_args = args

        router.register_telegram_command("search", handler)

        request = MockRequest(
            _json_data={
                "update_id": 123,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123},
                    "text": "/search",
                },
            }
        )

        await router.handle_telegram_webhook(request)

        assert received_args == ""

    async def test_command_with_bot_mention(self, router: BotRouter) -> None:
        """Handle /command@botname format in groups."""
        received_command: str | None = None

        async def handler(command: str, args: str, chat_id: int, message_id: int) -> None:
            nonlocal received_command
            received_command = command

        router.register_telegram_command("search", handler)

        request = MockRequest(
            _json_data={
                "update_id": 123,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123},
                    "text": "/search@mybot query",
                },
            }
        )

        await router.handle_telegram_webhook(request)

        assert received_command == "search"

    async def test_non_command_message_ignored(self, router: BotRouter) -> None:
        """Non-command messages don't trigger handlers."""
        handler_called = False

        async def handler(command: str, args: str, chat_id: int, message_id: int) -> None:
            nonlocal handler_called
            handler_called = True

        router.register_telegram_command("search", handler)

        request = MockRequest(
            _json_data={
                "update_id": 123,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123},
                    "text": "Hello, this is not a command",
                },
            }
        )

        await router.handle_telegram_webhook(request)

        assert not handler_called


class TestTelegramCallbackQueryRouting:
    """Tests for Telegram callback query routing."""

    async def test_route_watch_callback(self, router: BotRouter) -> None:
        """Route watch callback to registered handler."""
        handler_called = False
        handler_args: tuple = ()

        async def watch_handler(
            callback_data: str, chat_id: int, message_id: int, callback_query_id: str
        ) -> None:
            nonlocal handler_called, handler_args
            handler_called = True
            handler_args = (callback_data, chat_id, message_id, callback_query_id)

        router.register_telegram_callback("w:", watch_handler)

        request = MockRequest(
            _json_data={
                "update_id": 123456789,
                "callback_query": {
                    "id": "callback123",
                    "data": "w:0:abc123",
                    "message": {
                        "message_id": 100,
                        "chat": {"id": 987654321},
                    },
                },
            }
        )

        response = await router.handle_telegram_webhook(request)

        assert response.status == 200
        assert handler_called
        assert handler_args[0] == "w:0:abc123"
        assert handler_args[1] == 987654321
        assert handler_args[2] == 100
        assert handler_args[3] == "callback123"

    async def test_route_preview_callback(self, router: BotRouter) -> None:
        """Route preview callback to different handler."""
        watch_called = False
        preview_called = False

        async def watch_handler(
            callback_data: str, chat_id: int, message_id: int, callback_query_id: str
        ) -> None:
            nonlocal watch_called
            watch_called = True

        async def preview_handler(
            callback_data: str, chat_id: int, message_id: int, callback_query_id: str
        ) -> None:
            nonlocal preview_called
            preview_called = True

        router.register_telegram_callback("w:", watch_handler)
        router.register_telegram_callback("p:", preview_handler)

        request = MockRequest(
            _json_data={
                "update_id": 123,
                "callback_query": {
                    "id": "cb1",
                    "data": "p:1:def456",
                    "message": {"message_id": 1, "chat": {"id": 123}},
                },
            }
        )

        await router.handle_telegram_webhook(request)

        assert not watch_called
        assert preview_called

    async def test_no_handler_still_returns_200(self, router: BotRouter) -> None:
        """Unknown callback data still returns 200."""
        request = MockRequest(
            _json_data={
                "update_id": 123,
                "callback_query": {
                    "id": "cb1",
                    "data": "unknown:action",
                    "message": {"message_id": 1, "chat": {"id": 123}},
                },
            }
        )

        response = await router.handle_telegram_webhook(request)

        assert response.status == 200


class TestTelegramInvalidPayload:
    """Tests for Telegram webhook with invalid payloads."""

    async def test_invalid_json(self, router: BotRouter) -> None:
        """Invalid JSON returns 200 (Telegram expects this)."""
        request = MockRequest(_json_error=True)

        response = await router.handle_telegram_webhook(request)

        # Telegram expects 200 even on errors
        assert response.status == 200

    async def test_empty_update(self, router: BotRouter) -> None:
        """Empty update object returns 200."""
        request = MockRequest(_json_data={"update_id": 123})

        response = await router.handle_telegram_webhook(request)

        assert response.status == 200


# --- Tests for _parse_form_data ---


class TestParseFormData:
    """Tests for form data parsing."""

    def test_simple_fields(self) -> None:
        """Parse simple URL-encoded fields."""
        data = "key1=value1&key2=value2"

        result = _parse_form_data(data)

        assert result["key1"] == "value1"
        assert result["key2"] == "value2"

    def test_url_encoded_values(self) -> None:
        """Parse URL-encoded special characters."""
        data = "text=auth+bug&url=https%3A%2F%2Fexample.com"

        result = _parse_form_data(data)

        assert result["text"] == "auth bug"
        assert result["url"] == "https://example.com"

    def test_empty_value(self) -> None:
        """Parse field with empty value."""
        data = "empty=&filled=value"

        result = _parse_form_data(data)

        assert result["empty"] == ""
        assert result["filled"] == "value"


# --- Tests for register_bot_routes ---


class TestRegisterBotRoutes:
    """Tests for route registration."""

    def test_registers_all_routes(self, router: BotRouter) -> None:
        """Registers all three bot webhook routes."""
        from aiohttp import web

        app = web.Application()

        register_bot_routes(app, router)

        routes = {r.resource.canonical for r in app.router.routes() if r.resource}
        assert "/slack/commands" in routes
        assert "/slack/interactions" in routes
        assert "/telegram/webhook" in routes


# --- Tests for handler error handling ---


class TestHandlerErrorHandling:
    """Tests for error handling in handlers."""

    async def test_slack_command_handler_exception(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Handler exception still returns 200 for Slack."""
        async def bad_handler(
            command: str, text: str, user_id: str, channel_id: str, response_url: str
        ) -> None:
            raise RuntimeError("Handler crashed")

        router.register_slack_command("/search", bad_handler)

        body = "command=%2Fsearch&text=test"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        # Should not raise, returns 200 to acknowledge
        response = await router.handle_slack_command(request)
        assert response.status == 200

    async def test_telegram_command_handler_exception(self, router: BotRouter) -> None:
        """Handler exception still returns 200 for Telegram."""
        async def bad_handler(
            command: str, args: str, chat_id: int, message_id: int
        ) -> None:
            raise RuntimeError("Handler crashed")

        router.register_telegram_command("search", bad_handler)

        request = MockRequest(
            _json_data={
                "update_id": 123,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 123},
                    "text": "/search test",
                },
            }
        )

        # Should not raise, returns 200 to acknowledge
        response = await router.handle_telegram_webhook(request)
        assert response.status == 200

    async def test_slack_interaction_handler_exception(
        self, router: BotRouter, current_timestamp: str
    ) -> None:
        """Interaction handler exception still returns 200."""
        async def bad_handler(
            action_id: str, value: str | None, payload: dict
        ) -> None:
            raise RuntimeError("Handler crashed")

        router.register_slack_interaction("watch:", bad_handler)

        payload = {
            "type": "block_actions",
            "actions": [{"action_id": "watch:test", "value": "x"}],
        }
        body = f"payload={json.dumps(payload)}"
        signature = make_slack_signature(
            body, current_timestamp, router.bot_config.slack_signing_secret
        )

        request = MockRequest(
            headers={
                "X-Slack-Request-Timestamp": current_timestamp,
                "X-Slack-Signature": signature,
            },
            _body=body.encode(),
        )

        response = await router.handle_slack_interaction(request)
        assert response.status == 200


# --- Tests for handler registration ---


class TestHandlerRegistration:
    """Tests for handler registration methods."""

    def test_register_multiple_slack_commands(self, router: BotRouter) -> None:
        """Can register multiple Slack commands."""
        async def handler1(*args: Any) -> None:
            pass

        async def handler2(*args: Any) -> None:
            pass

        router.register_slack_command("/search", handler1)
        router.register_slack_command("/projects", handler2)

        assert "/search" in router._slack_command_handlers
        assert "/projects" in router._slack_command_handlers

    def test_register_multiple_telegram_commands(self, router: BotRouter) -> None:
        """Can register multiple Telegram commands."""
        async def handler1(*args: Any) -> None:
            pass

        async def handler2(*args: Any) -> None:
            pass

        router.register_telegram_command("search", handler1)
        router.register_telegram_command("projects", handler2)

        assert "search" in router._telegram_command_handlers
        assert "projects" in router._telegram_command_handlers

    def test_overwrite_handler(self, router: BotRouter) -> None:
        """Registering same command overwrites previous handler."""
        async def handler1(*args: Any) -> None:
            pass

        async def handler2(*args: Any) -> None:
            pass

        router.register_slack_command("/search", handler1)
        router.register_slack_command("/search", handler2)

        assert router._slack_command_handlers["/search"] is handler2
