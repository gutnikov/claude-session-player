"""Integration tests for messaging components in WatcherService.

Tests the end-to-end flow from file changes to Telegram/Slack message delivery.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    DurationContent,
    ProcessingContext,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)
from claude_session_player.watcher.config import BotConfig, ConfigManager
from claude_session_player.watcher.debouncer import MessageDebouncer
from claude_session_player.watcher.destinations import DestinationManager
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.file_watcher import FileWatcher
from claude_session_player.watcher.message_state import (
    MessageStateTracker,
    NoAction,
    SendNewMessage,
    UpdateExistingMessage,
)
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.slack_publisher import SlackError, SlackPublisher
from claude_session_player.watcher.sse import SSEManager
from claude_session_player.watcher.state import StateManager
from claude_session_player.watcher.telegram_publisher import TelegramError, TelegramPublisher


# --- Mock Publishers ---


@dataclass
class MockTelegramPublisher:
    """Mock TelegramPublisher for testing."""

    token: str | None = None
    validated: bool = False
    sent_messages: list[dict] = field(default_factory=list)
    edited_messages: list[dict] = field(default_factory=list)
    _next_message_id: int = field(default=1, repr=False)
    _should_fail: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def validate(self) -> None:
        if self._should_fail:
            raise TelegramError("Validation failed")
        self.validated = True

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: object = None,
        message_thread_id: int | None = None,
    ) -> int:
        if self._should_fail:
            raise TelegramError("Send failed")
        message_id = self._next_message_id
        self._next_message_id += 1
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "message_id": message_id,
            "message_thread_id": message_thread_id,
        })
        return message_id

    async def edit_message(
        self, chat_id: str, message_id: int, text: str, parse_mode: str = "Markdown"
    ) -> bool:
        if self._should_fail:
            raise TelegramError("Edit failed")
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        })
        return True

    async def close(self) -> None:
        self._closed = True


@dataclass
class MockSlackPublisher:
    """Mock SlackPublisher for testing."""

    token: str | None = None
    validated: bool = False
    sent_messages: list[dict] = field(default_factory=list)
    updated_messages: list[dict] = field(default_factory=list)
    _next_ts: int = field(default=1, repr=False)
    _should_fail: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def validate(self) -> None:
        if self._should_fail:
            raise SlackError("Validation failed")
        self.validated = True

    async def send_message(
        self, channel: str, text: str, blocks: list[dict] | None = None
    ) -> str:
        if self._should_fail:
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
        if self._should_fail:
            raise SlackError("Update failed")
        self.updated_messages.append({
            "channel": channel,
            "ts": ts,
            "text": text,
            "blocks": blocks,
        })
        return True

    async def close(self) -> None:
        self._closed = True


# --- Fixtures ---


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
def mock_telegram_publisher() -> MockTelegramPublisher:
    """Create a mock Telegram publisher."""
    return MockTelegramPublisher(token="test-telegram-token")


@pytest.fixture
def mock_slack_publisher() -> MockSlackPublisher:
    """Create a mock Slack publisher."""
    return MockSlackPublisher(token="test-slack-token")


@pytest.fixture
def watcher_service_with_messaging(
    temp_config_path: Path,
    temp_state_dir: Path,
    mock_telegram_publisher: MockTelegramPublisher,
    mock_slack_publisher: MockSlackPublisher,
) -> WatcherService:
    """Create a WatcherService with mock messaging publishers."""
    # Create config manager with bot tokens
    config_manager = ConfigManager(temp_config_path)
    # Mock the bot config
    config_manager._bot_config = BotConfig(
        telegram_token="test-telegram-token",
        slack_token="test-slack-token",
    )

    service = WatcherService(
        config_path=temp_config_path,
        state_dir=temp_state_dir,
        config_manager=config_manager,
        telegram_publisher=mock_telegram_publisher,
        slack_publisher=mock_slack_publisher,
        port=8899,
    )

    return service


# --- Tests for Service Initialization ---


class TestServiceMessagingInitialization:
    """Tests for messaging component initialization in WatcherService."""

    def test_creates_message_state_tracker(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service creates MessageStateTracker."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service.message_state is not None
        assert isinstance(service.message_state, MessageStateTracker)

    def test_creates_message_debouncer(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service creates MessageDebouncer."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service.message_debouncer is not None
        assert isinstance(service.message_debouncer, MessageDebouncer)

    def test_creates_telegram_publisher_if_configured(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service creates TelegramPublisher when token is configured."""
        config_manager = ConfigManager(temp_config_path)
        config_manager._bot_config = BotConfig(telegram_token="test-token")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            config_manager=config_manager,
        )

        assert service.telegram_publisher is not None

    def test_creates_slack_publisher_if_configured(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service creates SlackPublisher when token is configured."""
        config_manager = ConfigManager(temp_config_path)
        config_manager._bot_config = BotConfig(slack_token="xoxb-test-token")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            config_manager=config_manager,
        )

        assert service.slack_publisher is not None

    def test_no_publishers_without_tokens(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Service doesn't create publishers without tokens."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        assert service.telegram_publisher is None
        assert service.slack_publisher is None

    def test_accepts_injected_publishers(
        self,
        temp_config_path: Path,
        temp_state_dir: Path,
        mock_telegram_publisher: MockTelegramPublisher,
        mock_slack_publisher: MockSlackPublisher,
    ) -> None:
        """Service accepts injected publishers for testing."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            telegram_publisher=mock_telegram_publisher,
            slack_publisher=mock_slack_publisher,
        )

        assert service.telegram_publisher is mock_telegram_publisher
        assert service.slack_publisher is mock_slack_publisher


# --- Tests for Event Flow to Messaging ---


class TestEventFlowToMessaging:
    """Tests for event flow from file changes to messaging destinations."""

    async def test_user_block_sends_telegram_message(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """USER block sends new Telegram message."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

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

            # Simulate user message event
            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello, Claude!"),
            )
            event = AddBlock(block=user_block)
            await service._publish_to_messaging("test-session", event)

            # Verify message was sent
            assert len(publisher.sent_messages) == 1
            msg = publisher.sent_messages[0]
            assert msg["chat_id"] == "123456789"
            assert "Hello" in msg["text"]

        finally:
            await service.stop()

    async def test_assistant_block_sends_slack_message(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """ASSISTANT block sends new Slack message."""
        service = watcher_service_with_messaging
        publisher = service.slack_publisher

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

            # Simulate assistant message event
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Hello! How can I help?"),
            )
            event = AddBlock(block=assistant_block)
            await service._publish_to_messaging("test-session", event)

            # Verify message was sent
            assert len(publisher.sent_messages) == 1
            msg = publisher.sent_messages[0]
            assert msg["channel"] == "C0123456789"

        finally:
            await service.stop()

    async def test_no_message_without_destinations(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """No messages sent when no destinations attached."""
        service = watcher_service_with_messaging
        telegram_publisher = service.telegram_publisher
        slack_publisher = service.slack_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Don't attach any destinations

            # Simulate event
            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello!"),
            )
            event = AddBlock(block=user_block)
            await service._publish_to_messaging("test-session", event)

            # Verify no messages sent
            assert len(telegram_publisher.sent_messages) == 0
            assert len(slack_publisher.sent_messages) == 0

        finally:
            await service.stop()

    async def test_turn_grouping(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Multiple events in a turn produce update, not new messages."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

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

            # Send initial assistant message
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Let me help."),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=assistant_block)
            )

            # First message sent
            assert len(publisher.sent_messages) == 1
            message_id = publisher.sent_messages[0]["message_id"]

            # Record message ID to enable updates
            service.message_state.record_message_id(
                "test-session",
                f"turn-asst-1",
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
            await service._publish_to_messaging(
                "test-session", AddBlock(block=tool_block)
            )

            # Should schedule update, not new message
            # Wait for debouncer
            await asyncio.sleep(0.6)

            # Should have 1 sent and 1 edited
            assert len(publisher.sent_messages) == 1
            assert len(publisher.edited_messages) == 1
            assert publisher.edited_messages[0]["message_id"] == message_id

        finally:
            await service.stop()

    async def test_message_update_debounced(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Rapid updates are debounced."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

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

            # Send initial assistant message
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Let me help."),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=assistant_block)
            )

            message_id = publisher.sent_messages[0]["message_id"]
            service.message_state.record_message_id(
                "test-session",
                f"turn-asst-1",
                "telegram",
                "123456789",
                message_id,
            )

            # Rapidly add multiple tool calls
            for i in range(5):
                tool_block = Block(
                    id=f"tool-{i}",
                    type=BlockType.TOOL_CALL,
                    content=ToolCallContent(
                        tool_name="Read",
                        tool_use_id=f"tu-{i}",
                        label=f"file{i}.py",
                    ),
                )
                await service._publish_to_messaging(
                    "test-session", AddBlock(block=tool_block)
                )

            # Wait for debouncer (Telegram: 500ms)
            await asyncio.sleep(0.6)

            # Should have only 1 edit (last one wins)
            assert len(publisher.edited_messages) == 1

        finally:
            await service.stop()


# --- Tests for Replay ---


class TestReplayToDestination:
    """Tests for replay functionality."""

    async def test_replay_sends_catch_up_message(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Replay sends batched catch-up message."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Add some events to buffer
            for i in range(5):
                user_block = Block(
                    id=f"user-{i}",
                    type=BlockType.USER,
                    content=UserContent(text=f"Message {i}"),
                )
                service.event_buffer.add_event(
                    "test-session", AddBlock(block=user_block)
                )

            # Replay to Telegram destination
            replayed = await service.replay_to_destination(
                session_id="test-session",
                destination_type="telegram",
                identifier="123456789",
                count=3,
            )

            assert replayed == 3
            assert len(publisher.sent_messages) == 1
            assert "Catching up" in publisher.sent_messages[0]["text"]

        finally:
            await service.stop()

    async def test_replay_returns_zero_when_no_events(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Replay returns 0 when no events in buffer."""
        service = watcher_service_with_messaging

        try:
            await service.start()
            await service.watch("test-session", session_file)

            replayed = await service.replay_to_destination(
                session_id="test-session",
                destination_type="telegram",
                identifier="123456789",
                count=10,
            )

            assert replayed == 0

        finally:
            await service.stop()


# --- Tests for Shutdown ---


class TestMessagingShutdown:
    """Tests for graceful shutdown of messaging components."""

    async def test_shutdown_flushes_debouncer(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Shutdown flushes pending debounced updates."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

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

            # Send initial message
            assistant_block = Block(
                id="asst-1",
                type=BlockType.ASSISTANT,
                content=AssistantContent(text="Initial"),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=assistant_block)
            )

            message_id = publisher.sent_messages[0]["message_id"]
            service.message_state.record_message_id(
                "test-session",
                f"turn-asst-1",
                "telegram",
                "123456789",
                message_id,
            )

            # Schedule update (not yet delivered)
            tool_block = Block(
                id="tool-1",
                type=BlockType.TOOL_CALL,
                content=ToolCallContent(
                    tool_name="Read",
                    tool_use_id="tu-1",
                    label="file.py",
                ),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=tool_block)
            )

            # Before debounce timeout, edited_messages should be empty
            assert len(publisher.edited_messages) == 0

            # Stop should flush pending updates
            await service.stop()

            # After stop, update should be delivered
            assert len(publisher.edited_messages) == 1

        except Exception:
            if service.is_running:
                await service.stop()
            raise

    async def test_shutdown_closes_publishers(
        self,
        watcher_service_with_messaging: WatcherService,
    ) -> None:
        """Shutdown closes messaging publishers."""
        service = watcher_service_with_messaging
        telegram = service.telegram_publisher
        slack = service.slack_publisher

        await service.start()
        await service.stop()

        assert telegram._closed
        assert slack._closed


# --- Tests for Error Handling ---


class TestMessagingErrorHandling:
    """Tests for error handling in messaging operations."""

    async def test_send_failure_logged_not_raised(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Send failures are logged but don't raise exceptions."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher
        publisher._should_fail = True

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach destination
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send event (should fail but not raise)
            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello!"),
            )
            # Should not raise
            await service._publish_to_messaging(
                "test-session", AddBlock(block=user_block)
            )

        finally:
            await service.stop()

    async def test_validates_destination_on_demand(
        self,
        watcher_service_with_messaging: WatcherService,
    ) -> None:
        """validate_destination validates bot credentials."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

        await service.validate_destination("telegram")
        assert publisher.validated


# --- Tests for ClearAll Event ---


class TestClearAllEvent:
    """Tests for ClearAll (context compaction) handling."""

    async def test_clear_all_sends_compaction_message(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """ClearAll sends context compaction message."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach destination
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_file,
                destination_type="telegram",
                identifier="123456789",
            )

            # Send ClearAll event
            await service._publish_to_messaging("test-session", ClearAll())

            # Should send compaction message
            assert len(publisher.sent_messages) == 1
            assert "compacted" in publisher.sent_messages[0]["text"].lower()

        finally:
            await service.stop()


# --- Tests for Multiple Destinations ---


class TestMultipleDestinations:
    """Tests for publishing to multiple destinations."""

    async def test_sends_to_all_destinations(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Events are sent to all attached destinations."""
        service = watcher_service_with_messaging
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

            # Send event
            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello!"),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=user_block)
            )

            # Both should receive messages
            assert len(telegram.sent_messages) == 1
            assert len(slack.sent_messages) == 1

        finally:
            await service.stop()

    async def test_sends_to_multiple_chats(
        self,
        watcher_service_with_messaging: WatcherService,
        session_file: Path,
    ) -> None:
        """Events are sent to multiple chats of same type."""
        service = watcher_service_with_messaging
        publisher = service.telegram_publisher

        try:
            await service.start()
            await service.watch("test-session", session_file)

            # Attach multiple Telegram chats
            for chat_id in ["111", "222", "333"]:
                await service.destination_manager.attach(
                    session_id="test-session",
                    path=session_file,
                    destination_type="telegram",
                    identifier=chat_id,
                )

            # Send event
            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello!"),
            )
            await service._publish_to_messaging(
                "test-session", AddBlock(block=user_block)
            )

            # All chats should receive messages
            assert len(publisher.sent_messages) == 3
            chat_ids = [m["chat_id"] for m in publisher.sent_messages]
            assert set(chat_ids) == {"111", "222", "333"}

        finally:
            await service.stop()


# --- Tests for Service Start with Destinations ---


class TestServiceStartWithDestinations:
    """Tests for service startup restoring destinations."""

    async def test_start_restores_destinations(
        self, temp_config_path: Path, temp_state_dir: Path, tmp_path: Path
    ) -> None:
        """Service startup restores destinations from config."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}\n')

        # Pre-populate config with destinations
        import yaml

        config_data = {
            "bots": {
                "telegram": {"token": "test-token"},
            },
            "sessions": {
                "restored-session": {
                    "path": str(session_file),
                    "destinations": {
                        "telegram": [{"chat_id": "123456"}],
                    },
                }
            },
        }
        temp_config_path.write_text(yaml.dump(config_data))

        mock_telegram = MockTelegramPublisher(token="test-token")

        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            telegram_publisher=mock_telegram,
            port=8898,
        )

        try:
            await service.start()

            # Destinations should be restored
            destinations = service.destination_manager.get_destinations("restored-session")
            assert len(destinations) == 1
            assert destinations[0].type == "telegram"
            assert destinations[0].identifier == "123456"

        finally:
            await service.stop()
