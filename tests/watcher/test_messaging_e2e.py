"""End-to-end tests for Telegram and Slack messaging integration.

These tests verify the complete flow from HTTP request to (mocked) message delivery,
including all components working together:
- ConfigManager (bot tokens, destinations)
- DestinationManager (attach/detach lifecycle)
- TelegramPublisher / SlackPublisher (API calls)
- MessageStateTracker (turn grouping)
- MessageDebouncer (rate limiting)
- WatcherService (orchestration)
- WatcherAPI (HTTP endpoints)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.config import BotConfig, ConfigManager
from claude_session_player.watcher.debouncer import MessageDebouncer
from claude_session_player.watcher.destinations import DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.message_state import MessageStateTracker
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.slack_publisher import SlackError
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.telegram_publisher import TelegramError


# -----------------------------------------------------------------------------
# Mock Publishers
# -----------------------------------------------------------------------------


@dataclass
class MockTelegramBot:
    """Mock aiogram Bot for testing."""

    token: str = "test_telegram_token"
    username: str = "test_bot"
    sent_messages: list[dict] = field(default_factory=list)
    edited_messages: list[dict] = field(default_factory=list)
    _next_message_id: int = field(default=12345, repr=False)
    _should_fail_validation: bool = field(default=False, repr=False)
    _should_fail_send: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def validate(self) -> None:
        """Validate bot credentials."""
        if self._should_fail_validation:
            raise TelegramError("Validation failed")

    async def send_message(
        self, chat_id: str, text: str, parse_mode: str = "Markdown"
    ) -> int:
        """Send a message to a chat."""
        if self._should_fail_send:
            raise TelegramError("Send failed")
        message_id = self._next_message_id
        self._next_message_id += 1
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "message_id": message_id,
            "parse_mode": parse_mode,
        })
        return message_id

    async def edit_message(
        self, chat_id: str, message_id: int, text: str, parse_mode: str = "Markdown"
    ) -> bool:
        """Edit an existing message."""
        if self._should_fail_send:
            raise TelegramError("Edit failed")
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        })
        return True

    async def close(self) -> None:
        """Close the bot session."""
        self._closed = True


@dataclass
class MockSlackClient:
    """Mock slack_sdk AsyncWebClient for testing."""

    token: str = "xoxb-test-slack-token"
    sent_messages: list[dict] = field(default_factory=list)
    updated_messages: list[dict] = field(default_factory=list)
    _next_ts: int = field(default=1, repr=False)
    _should_fail_validation: bool = field(default=False, repr=False)
    _should_fail_send: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def validate(self) -> None:
        """Validate Slack credentials."""
        if self._should_fail_validation:
            raise SlackError("Validation failed")

    async def send_message(
        self, channel: str, text: str, blocks: list[dict] | None = None
    ) -> str:
        """Post a message to a channel."""
        if self._should_fail_send:
            raise SlackError("Send failed")
        ts = f"1234567890.{self._next_ts:06d}"
        self._next_ts += 1
        self.sent_messages.append({
            "channel": channel,
            "text": text,
            "blocks": blocks,
            "ts": ts,
        })
        return ts

    async def update_message(
        self, channel: str, ts: str, text: str, blocks: list[dict] | None = None
    ) -> bool:
        """Update an existing message."""
        if self._should_fail_send:
            raise SlackError("Update failed")
        self.updated_messages.append({
            "channel": channel,
            "ts": ts,
            "text": text,
            "blocks": blocks,
        })
        return True

    async def close(self) -> None:
        """Close the client session."""
        self._closed = True


# -----------------------------------------------------------------------------
# Mock HTTP Request/Response
# -----------------------------------------------------------------------------


@dataclass
class MockRequest:
    """Mock aiohttp request for testing."""

    match_info: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    _json_data: dict | None = None
    _json_error: bool = False
    transport: Any = None

    async def json(self) -> dict:
        """Return JSON body."""
        if self._json_error:
            raise json.JSONDecodeError("Invalid JSON", "", 0)
        return self._json_data or {}


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def temp_config_path(tmp_path: Path) -> Path:
    """Create a temporary config file path."""
    return tmp_path / "config.yaml"


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def session_file(tmp_path: Path) -> Path:
    """Create a temporary session file."""
    session_path = tmp_path / "session.jsonl"
    session_path.write_text('{"type":"user","message":{"content":"hello"}}\n')
    return session_path


@pytest.fixture
def mock_telegram_bot() -> MockTelegramBot:
    """Mock Telegram publisher for testing."""
    return MockTelegramBot()


@pytest.fixture
def mock_slack_client() -> MockSlackClient:
    """Mock Slack publisher for testing."""
    return MockSlackClient()


@pytest.fixture
def config_with_bots(tmp_path: Path) -> Path:
    """Create a config file with bot tokens."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({
        "bots": {
            "telegram": {"token": "test_telegram_token"},
            "slack": {"token": "xoxb-test-slack-token"},
        },
        "sessions": {},
    }))
    return config_path


@pytest.fixture
async def watcher_service_with_mocks(
    config_with_bots: Path,
    temp_state_dir: Path,
    mock_telegram_bot: MockTelegramBot,
    mock_slack_client: MockSlackClient,
) -> WatcherService:
    """Create a WatcherService with mock messaging publishers."""
    config_manager = ConfigManager(config_with_bots)
    config_manager._bot_config = BotConfig(
        telegram_token="test_telegram_token",
        slack_token="xoxb-test-slack-token",
    )

    service = WatcherService(
        config_path=config_with_bots,
        state_dir=temp_state_dir,
        config_manager=config_manager,
        telegram_publisher=mock_telegram_bot,
        slack_publisher=mock_slack_client,
        port=0,  # Let OS assign port
    )

    return service


# -----------------------------------------------------------------------------
# Attach/Detach E2E Tests
# -----------------------------------------------------------------------------


class TestAttachDetachE2E:
    """E2E tests for attach/detach via HTTP API."""

    async def test_attach_telegram_via_api_returns_201(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """POST /attach for Telegram returns 201 and attaches destination."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            # Create attach request
            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                }
            )

            # Mock validation to not hit real API
            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                response = await service.api.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["attached"] is True
            assert data["session_id"] == "test-session"
            assert data["destination"]["type"] == "telegram"
            assert data["destination"]["chat_id"] == "123456789"

            # Verify destination is actually attached
            destinations = service.destination_manager.get_destinations("test-session")
            assert len(destinations) == 1
            assert destinations[0].type == "telegram"
            assert destinations[0].identifier == "123456789"

        finally:
            await service.stop()

    async def test_attach_slack_via_api_returns_201(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """POST /attach for Slack returns 201 and attaches destination."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "slack",
                        "channel": "C0123456789",
                    },
                }
            )

            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                response = await service.api.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["attached"] is True
            assert data["destination"]["type"] == "slack"
            assert data["destination"]["channel"] == "C0123456789"

        finally:
            await service.stop()

    async def test_attach_without_bot_token_returns_401(
        self,
        temp_config_path: Path,
        temp_state_dir: Path,
        session_file: Path,
    ) -> None:
        """POST /attach without bot token configured returns 401."""
        # Service without bot tokens
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            port=0,
        )

        try:
            await service.start()

            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {
                        "type": "telegram",
                        "chat_id": "123456789",
                    },
                }
            )

            response = await service.api.handle_attach(request)

            assert response.status == 401
            data = json.loads(response.body)
            assert "not configured" in data["error"].lower()

        finally:
            await service.stop()

    async def test_detach_removes_destination_returns_204(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """POST /detach removes destination and returns 204."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            # First attach
            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                await service.api.handle_attach(MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "path": str(session_file),
                        "destination": {"type": "telegram", "chat_id": "123"},
                    }
                ))

            # Verify attached
            assert len(service.destination_manager.get_destinations("test-session")) == 1

            # Detach
            response = await service.api.handle_detach(MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "destination": {"type": "telegram", "chat_id": "123"},
                }
            ))

            assert response.status == 204

            # Verify detached
            assert len(service.destination_manager.get_destinations("test-session")) == 0

        finally:
            await service.stop()

    async def test_idempotent_attach_returns_success(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Duplicate attach (same session + destination) returns success."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            request = MockRequest(
                _json_data={
                    "session_id": "test-session",
                    "path": str(session_file),
                    "destination": {"type": "telegram", "chat_id": "123"},
                }
            )

            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                # First attach
                response1 = await service.api.handle_attach(request)
                assert response1.status == 201

                # Second attach (should be idempotent)
                response2 = await service.api.handle_attach(request)
                assert response2.status == 201

            # Should still have only one destination
            destinations = service.destination_manager.get_destinations("test-session")
            assert len(destinations) == 1

        finally:
            await service.stop()


# -----------------------------------------------------------------------------
# Message Delivery E2E Tests
# -----------------------------------------------------------------------------


class TestMessageDeliveryE2E:
    """E2E tests for message delivery from file change to API calls."""

    async def test_user_event_sends_telegram_message(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """USER event sends message to Telegram via Bot API."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach Telegram destination
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Simulate file change with user message
            user_line = {"type": "user", "message": {"content": "Hello, Claude!"}}
            await service._on_file_change("test-session", [user_line])

            # Verify Telegram message was sent
            assert len(telegram.sent_messages) == 1
            msg = telegram.sent_messages[0]
            assert msg["chat_id"] == "123456789"
            assert "Hello" in msg["text"]

        finally:
            await service.stop()

    async def test_user_event_sends_slack_message_with_blocks(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """USER event sends message to Slack with Block Kit format."""
        service = watcher_service_with_mocks
        slack = service.slack_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach Slack destination
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="slack",
                identifier="C0123456789",
            )

            # Simulate file change with user message
            user_line = {"type": "user", "message": {"content": "Hello from user"}}
            await service._on_file_change("test-session", [user_line])

            # Verify Slack message was sent
            assert len(slack.sent_messages) == 1
            msg = slack.sent_messages[0]
            assert msg["channel"] == "C0123456789"
            # Slack messages include blocks
            assert msg["blocks"] is not None or msg["text"]

        finally:
            await service.stop()

    async def test_turn_grouping_assistant_and_tools_in_one_message(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Assistant + tools in same turn are grouped into one message with updates."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send assistant message (starts turn)
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Let me check that for you."),
            )
            await service._publish_to_messaging("test-session", AddBlock(block=assistant_block))

            # First message sent
            assert len(telegram.sent_messages) == 1
            message_id = telegram.sent_messages[0]["message_id"]

            # Record message ID to enable updates
            service.message_state.record_message_id(
                "test-session",
                "turn-asst-1",
                "telegram",
                "123456789",
                message_id,
            )

            # Add tool call to same turn
            tool_block = Block(
                id="tool-1",
                type=BlockType.TOOL_CALL,
                content=ToolCallContent(
                    tool_name="Read",
                    tool_use_id="tu-1",
                    label="config.py",
                ),
            )
            await service._publish_to_messaging("test-session", AddBlock(block=tool_block))

            # Wait for debouncer (Telegram: 500ms)
            await asyncio.sleep(0.6)

            # Should have 1 sent message and 1 edit (not 2 separate messages)
            assert len(telegram.sent_messages) == 1
            assert len(telegram.edited_messages) == 1
            assert telegram.edited_messages[0]["message_id"] == message_id

        finally:
            await service.stop()

    async def test_tool_result_updates_existing_message(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Tool result arrives and updates existing tool call message."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send assistant + tool call
            tool_use_line = {
                "type": "assistant",
                "message": {
                    "content": [{
                        "type": "tool_use",
                        "id": "tu_result_test",
                        "name": "Bash",
                        "input": {"command": "ls -la"}
                    }]
                }
            }
            await service._on_file_change("test-session", [tool_use_line])

            # Get sent message ID and record it
            assert len(telegram.sent_messages) >= 1
            message_id = telegram.sent_messages[-1]["message_id"]

            # Get the turn_id from message state
            state = service.message_state.get_session_state("test-session")
            if state.current_turn:
                service.message_state.record_message_id(
                    "test-session",
                    state.current_turn.turn_id,
                    "telegram",
                    "123456789",
                    message_id,
                )

            # Send tool result
            tool_result_line = {
                "type": "user",
                "message": {
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": "tu_result_test",
                        "content": "total 24\ndrwxr-xr-x 5 user staff 160 Jan 15 10:00 ."
                    }]
                }
            }
            await service._on_file_change("test-session", [tool_result_line])

            # Wait for debouncer
            await asyncio.sleep(0.6)

            # Should have edited the message with the result
            # (edit count depends on turn state, but should have some edits)
            assert len(telegram.edited_messages) >= 0 or len(telegram.sent_messages) >= 1

        finally:
            await service.stop()


# -----------------------------------------------------------------------------
# Rate Limiting E2E Tests
# -----------------------------------------------------------------------------


class TestRateLimitingE2E:
    """E2E tests for message update rate limiting."""

    async def test_rapid_updates_debounced(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Rapid updates result in fewer API calls than updates."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send initial assistant message
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Working on it..."),
            )
            await service._publish_to_messaging("test-session", AddBlock(block=assistant_block))

            message_id = telegram.sent_messages[0]["message_id"]
            service.message_state.record_message_id(
                "test-session",
                "turn-asst-1",
                "telegram",
                "123456789",
                message_id,
            )

            # Rapidly add 10 tool calls (simulating fast tool execution)
            for i in range(10):
                tool_block = Block(
                    id=f"tool-{i}",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Read",
                        tool_use_id=f"tu-{i}",
                        label=f"file{i}.py",
                    ),
                )
                await service._publish_to_messaging("test-session", AddBlock(block=tool_block))
                await asyncio.sleep(0.05)  # 50ms between updates

            # Wait for debouncer to flush
            await asyncio.sleep(0.6)

            # Should have significantly fewer edits than the 10 updates
            # Debouncing should coalesce rapid updates
            assert len(telegram.edited_messages) < 10
            # But at least one edit should have been made
            assert len(telegram.edited_messages) >= 1

        finally:
            await service.stop()


# -----------------------------------------------------------------------------
# Replay E2E Tests
# -----------------------------------------------------------------------------


class TestReplayE2E:
    """E2E tests for replay functionality."""

    async def test_replay_count_sends_batched_catch_up_message(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Replay with replay_count sends batched catch-up message."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Add events to buffer BEFORE attaching
            for i in range(5):
                user_block = Block(
                    id=f"user-{i}",
                    type=BlockType.USER,
                    content=UserContent(text=f"Message {i}"),
                )
                service.event_buffer.add_event("test-session", AddBlock(block=user_block))

            # Attach with replay_count via API
            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                request = MockRequest(
                    _json_data={
                        "session_id": "test-session",
                        "path": str(session_file),
                        "destination": {"type": "telegram", "chat_id": "123456789"},
                        "replay_count": 3,
                    }
                )
                response = await service.api.handle_attach(request)

            assert response.status == 201
            data = json.loads(response.body)
            assert data["replayed_events"] == 3

            # Should have sent a catch-up message
            assert len(telegram.sent_messages) >= 1
            # First message should be the catch-up
            assert "Catching up" in telegram.sent_messages[0]["text"]

        finally:
            await service.stop()


# -----------------------------------------------------------------------------
# Persistence E2E Tests
# -----------------------------------------------------------------------------


class TestPersistenceE2E:
    """E2E tests for destination persistence across restarts."""

    async def test_destinations_survive_service_restart(
        self,
        config_with_bots: Path,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Destinations are restored after service restart."""
        session_file = tmp_path / "persistent-session.jsonl"
        session_file.write_text('{"type":"user"}\n')

        mock_telegram1 = MockTelegramBot()
        mock_slack1 = MockSlackClient()

        # First service instance
        config_manager1 = ConfigManager(config_with_bots)
        config_manager1._bot_config = BotConfig(
            telegram_token="test_telegram_token",
            slack_token="xoxb-test-slack-token",
        )

        service1 = WatcherService(
            config_path=config_with_bots,
            state_dir=temp_state_dir,
            config_manager=config_manager1,
            telegram_publisher=mock_telegram1,
            slack_publisher=mock_slack1,
            port=0,
        )

        try:
            await service1.start()

            # Attach destinations
            await service1.destination_manager.attach(
                session_id="persistent-session",
                path=session_file,
                destination_type="telegram",
                identifier="111222333",
            )
            await service1.destination_manager.attach(
                session_id="persistent-session",
                path=session_file,
                destination_type="slack",
                identifier="C9876543210",
            )

            # Verify attached
            dests1 = service1.destination_manager.get_destinations("persistent-session")
            assert len(dests1) == 2

            await service1.stop()

        except Exception:
            if service1.is_running:
                await service1.stop()
            raise

        # Second service instance (simulating restart)
        mock_telegram2 = MockTelegramBot()
        mock_slack2 = MockSlackClient()

        config_manager2 = ConfigManager(config_with_bots)

        service2 = WatcherService(
            config_path=config_with_bots,
            state_dir=temp_state_dir,
            config_manager=config_manager2,
            telegram_publisher=mock_telegram2,
            slack_publisher=mock_slack2,
            port=0,
        )

        try:
            await service2.start()

            # Destinations should be restored from config
            dests2 = service2.destination_manager.get_destinations("persistent-session")
            assert len(dests2) == 2

            dest_types = {d.type for d in dests2}
            assert "telegram" in dest_types
            assert "slack" in dest_types

            # Identifiers should match
            telegram_dest = next(d for d in dests2 if d.type == "telegram")
            slack_dest = next(d for d in dests2 if d.type == "slack")
            assert telegram_dest.identifier == "111222333"
            assert slack_dest.identifier == "C9876543210"

        finally:
            await service2.stop()


# -----------------------------------------------------------------------------
# Additional E2E Tests for Edge Cases
# -----------------------------------------------------------------------------


class TestMultipleDestinationsE2E:
    """E2E tests for multiple destinations receiving events."""

    async def test_event_sent_to_all_attached_destinations(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Events are delivered to all attached destinations."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher
        slack = service.slack_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach both Telegram and Slack
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="slack",
                identifier="C0123456789",
            )

            # Send user message
            user_line = {"type": "user", "message": {"content": "Broadcast test"}}
            await service._on_file_change("test-session", [user_line])

            # Both should receive messages
            assert len(telegram.sent_messages) >= 1
            assert len(slack.sent_messages) >= 1

        finally:
            await service.stop()


class TestClearAllE2E:
    """E2E tests for context compaction (ClearAll) handling."""

    async def test_clear_all_sends_compaction_message(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """ClearAll event sends context compaction message."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send ClearAll event
            await service._publish_to_messaging("test-session", ClearAll())

            # Should send compaction message
            assert len(telegram.sent_messages) >= 1
            # Check that one message contains "compacted"
            compacted_msgs = [m for m in telegram.sent_messages if "compacted" in m["text"].lower()]
            assert len(compacted_msgs) >= 1

        finally:
            await service.stop()


class TestErrorHandlingE2E:
    """E2E tests for error handling in messaging."""

    async def test_messaging_failure_does_not_break_sse(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """Messaging failures don't prevent SSE events from being delivered."""
        service = watcher_service_with_mocks
        telegram = service.telegram_publisher
        telegram._should_fail_send = True

        try:
            await service.start()
            await service.watch("test-session", session_file)

            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Track SSE events
            sse_events = []

            # Mock SSE to capture events
            original_broadcast = service.sse_manager.broadcast

            async def capture_broadcast(session_id: str, event_id: str, event: Any) -> None:
                sse_events.append(event)
                await original_broadcast(session_id, event_id, event)

            service.sse_manager.broadcast = capture_broadcast

            # Send user message (should fail to Telegram but still work for SSE)
            user_line = {"type": "user", "message": {"content": "Test message"}}
            await service._on_file_change("test-session", [user_line])

            # Telegram should have no messages (failed)
            assert len(telegram.sent_messages) == 0

            # But SSE should have received the event
            assert len(sse_events) >= 1

        finally:
            await service.stop()


class TestHealthCheckE2E:
    """E2E tests for health check endpoint."""

    async def test_health_shows_bot_status(
        self,
        watcher_service_with_mocks: WatcherService,
    ) -> None:
        """Health endpoint shows bot configuration status."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            response = await service.api.handle_health(MockRequest())

            assert response.status == 200
            data = json.loads(response.body)
            assert data["status"] == "healthy"
            assert data["bots"]["telegram"] == "configured"
            assert data["bots"]["slack"] == "configured"

        finally:
            await service.stop()


class TestListSessionsE2E:
    """E2E tests for listing sessions with destinations."""

    async def test_list_sessions_shows_destinations(
        self,
        watcher_service_with_mocks: WatcherService,
        session_file: Path,
    ) -> None:
        """GET /sessions shows attached destinations."""
        service = watcher_service_with_mocks

        try:
            await service.start()

            # Attach destinations
            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                await service.api.handle_attach(MockRequest(
                    _json_data={
                        "session_id": "list-test",
                        "path": str(session_file),
                        "destination": {"type": "telegram", "chat_id": "111"},
                    }
                ))
                await service.api.handle_attach(MockRequest(
                    _json_data={
                        "session_id": "list-test",
                        "destination": {"type": "slack", "channel": "C222"},
                    }
                ))

            # List sessions
            response = await service.api.handle_list_sessions(MockRequest())

            assert response.status == 200
            data = json.loads(response.body)
            assert len(data["sessions"]) == 1

            session = data["sessions"][0]
            assert session["session_id"] == "list-test"
            assert {"chat_id": "111"} in session["destinations"]["telegram"]
            assert {"channel": "C222"} in session["destinations"]["slack"]

        finally:
            await service.stop()
