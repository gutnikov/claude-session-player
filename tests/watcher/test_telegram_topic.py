"""Tests for Telegram supergroup topic support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_session_player.watcher.config import (
    ConfigManager,
    SessionConfig,
    SessionDestinations,
    TelegramDestination,
)
from claude_session_player.watcher.destinations import (
    AttachedDestination,
    DestinationManager,
    make_telegram_identifier,
    parse_telegram_identifier,
)


# ---------------------------------------------------------------------------
# Identifier Helper Tests
# ---------------------------------------------------------------------------


class TestMakeTelegramIdentifier:
    """Tests for make_telegram_identifier helper."""

    def test_without_thread_id(self) -> None:
        """Returns chat_id when no thread_id."""
        result = make_telegram_identifier("123456789")
        assert result == "123456789"

    def test_with_thread_id(self) -> None:
        """Returns chat_id:thread_id format when thread_id provided."""
        result = make_telegram_identifier("123456789", 456)
        assert result == "123456789:456"

    def test_negative_chat_id(self) -> None:
        """Handles negative chat_ids correctly."""
        result = make_telegram_identifier("-1001234567890")
        assert result == "-1001234567890"

    def test_negative_chat_id_with_thread_id(self) -> None:
        """Handles negative chat_ids with thread_id."""
        result = make_telegram_identifier("-1001234567890", 123)
        assert result == "-1001234567890:123"

    def test_thread_id_none_explicit(self) -> None:
        """Explicitly passing None for thread_id returns just chat_id."""
        result = make_telegram_identifier("123", None)
        assert result == "123"


class TestParseTelegramIdentifier:
    """Tests for parse_telegram_identifier helper."""

    def test_simple_chat_id(self) -> None:
        """Parses simple chat_id without colon."""
        chat_id, thread_id = parse_telegram_identifier("123456789")
        assert chat_id == "123456789"
        assert thread_id is None

    def test_chat_id_with_thread_id(self) -> None:
        """Parses chat_id:thread_id format."""
        chat_id, thread_id = parse_telegram_identifier("123456789:456")
        assert chat_id == "123456789"
        assert thread_id == 456

    def test_negative_chat_id(self) -> None:
        """Parses negative chat_id correctly."""
        chat_id, thread_id = parse_telegram_identifier("-1001234567890")
        assert chat_id == "-1001234567890"
        assert thread_id is None

    def test_negative_chat_id_with_thread_id(self) -> None:
        """Parses negative chat_id with thread_id using rsplit."""
        chat_id, thread_id = parse_telegram_identifier("-1001234567890:123")
        assert chat_id == "-1001234567890"
        assert thread_id == 123

    def test_invalid_thread_id_returns_full_string(self) -> None:
        """Invalid thread_id (non-integer) returns original identifier."""
        chat_id, thread_id = parse_telegram_identifier("123:abc")
        assert chat_id == "123:abc"
        assert thread_id is None

    def test_roundtrip(self) -> None:
        """make and parse are inverses."""
        original_chat = "-1001234567890"
        original_thread = 456

        identifier = make_telegram_identifier(original_chat, original_thread)
        parsed_chat, parsed_thread = parse_telegram_identifier(identifier)

        assert parsed_chat == original_chat
        assert parsed_thread == original_thread


# ---------------------------------------------------------------------------
# TelegramDestination Tests
# ---------------------------------------------------------------------------


class TestTelegramDestinationIdentifier:
    """Tests for TelegramDestination.identifier property."""

    def test_identifier_without_thread_id(self) -> None:
        """identifier returns just chat_id when no thread_id."""
        dest = TelegramDestination(chat_id="123456789")
        assert dest.identifier == "123456789"

    def test_identifier_with_thread_id(self) -> None:
        """identifier returns combined format when thread_id set."""
        dest = TelegramDestination(chat_id="123456789", thread_id=456)
        assert dest.identifier == "123456789:456"

    def test_identifier_with_negative_chat_id(self) -> None:
        """identifier handles negative chat_id."""
        dest = TelegramDestination(chat_id="-1001234567890", thread_id=123)
        assert dest.identifier == "-1001234567890:123"


class TestTelegramDestinationSerialization:
    """Tests for TelegramDestination to_dict/from_dict."""

    def test_to_dict_without_thread_id(self) -> None:
        """to_dict omits thread_id when None."""
        dest = TelegramDestination(chat_id="123")
        d = dest.to_dict()
        assert d == {"chat_id": "123"}
        assert "thread_id" not in d

    def test_to_dict_with_thread_id(self) -> None:
        """to_dict includes thread_id when set."""
        dest = TelegramDestination(chat_id="123", thread_id=456)
        d = dest.to_dict()
        assert d == {"chat_id": "123", "thread_id": 456}

    def test_from_dict_without_thread_id(self) -> None:
        """from_dict creates destination without thread_id."""
        dest = TelegramDestination.from_dict({"chat_id": "123"})
        assert dest.chat_id == "123"
        assert dest.thread_id is None

    def test_from_dict_with_thread_id(self) -> None:
        """from_dict creates destination with thread_id."""
        dest = TelegramDestination.from_dict({"chat_id": "123", "thread_id": 456})
        assert dest.chat_id == "123"
        assert dest.thread_id == 456

    def test_roundtrip_serialization(self) -> None:
        """to_dict and from_dict are inverses."""
        original = TelegramDestination(chat_id="-1001234567890", thread_id=123)
        d = original.to_dict()
        restored = TelegramDestination.from_dict(d)
        assert restored.chat_id == original.chat_id
        assert restored.thread_id == original.thread_id
        assert restored.identifier == original.identifier


# ---------------------------------------------------------------------------
# Destination Manager with Thread ID Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_manager(tmp_path: Path) -> MagicMock:
    """Create a mock ConfigManager."""
    config = MagicMock(spec=ConfigManager)
    config.get.return_value = None
    config.load.return_value = []
    config.add_destination.return_value = True
    config.remove_destination.return_value = True
    return config


@pytest.fixture
def on_session_start() -> AsyncMock:
    """Create async mock for on_session_start callback."""
    return AsyncMock()


@pytest.fixture
def on_session_stop() -> AsyncMock:
    """Create async mock for on_session_stop callback."""
    return AsyncMock()


@pytest.fixture
def destination_manager(
    mock_config_manager: MagicMock,
    on_session_start: AsyncMock,
    on_session_stop: AsyncMock,
) -> DestinationManager:
    """Create a DestinationManager with mocks."""
    return DestinationManager(
        _config=mock_config_manager,
        _on_session_start=on_session_start,
        _on_session_stop=on_session_stop,
        _keep_alive_seconds=1,
    )


@pytest.fixture
def session_jsonl(tmp_path: Path) -> Path:
    """Create a temporary JSONL session file."""
    session_file = tmp_path / "session.jsonl"
    session_file.write_text('{"type": "user"}\n')
    return session_file


class TestAttachWithThreadId:
    """Tests for attaching destinations with thread_id."""

    @pytest.mark.asyncio
    async def test_attach_with_thread_id(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        session_jsonl: Path,
    ) -> None:
        """Attach with compound identifier containing thread_id."""
        identifier = make_telegram_identifier("-1001234567890", 123)
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=identifier,
        )

        # Verify config was updated with correct TelegramDestination
        mock_config_manager.add_destination.assert_called_once()
        call_args = mock_config_manager.add_destination.call_args
        config_dest = call_args[0][1]
        assert isinstance(config_dest, TelegramDestination)
        assert config_dest.chat_id == "-1001234567890"
        assert config_dest.thread_id == 123

    @pytest.mark.asyncio
    async def test_different_threads_are_separate_destinations(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Same chat_id with different thread_ids are separate destinations."""
        # Attach to topic 123
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 123),
        )

        # Attach to topic 456 (same chat, different topic)
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 456),
        )

        # Both should be tracked separately
        destinations = destination_manager.get_destinations("test-session")
        assert len(destinations) == 2
        identifiers = [d.identifier for d in destinations]
        assert "-1001234567890:123" in identifiers
        assert "-1001234567890:456" in identifiers

    @pytest.mark.asyncio
    async def test_attach_idempotent_with_same_thread(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Attaching same chat_id:thread_id is idempotent."""
        identifier = make_telegram_identifier("-1001234567890", 123)

        result1 = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=identifier,
        )

        result2 = await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=identifier,
        )

        assert result1 is True
        assert result2 is False  # Idempotent

        destinations = destination_manager.get_destinations("test-session")
        assert len(destinations) == 1


class TestDetachWithThreadId:
    """Tests for detaching destinations with thread_id."""

    @pytest.mark.asyncio
    async def test_detach_exact_thread_match(
        self,
        destination_manager: DestinationManager,
        mock_config_manager: MagicMock,
        session_jsonl: Path,
    ) -> None:
        """Detach requires exact thread_id match."""
        # Attach to topic 123
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 123),
        )

        # Try to detach without thread_id - should fail
        result = await destination_manager.detach(
            session_id="test-session",
            destination_type="telegram",
            identifier="-1001234567890",  # No thread_id
        )
        assert result is False

        # Detach with correct thread_id - should succeed
        result = await destination_manager.detach(
            session_id="test-session",
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 123),
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_detach_different_thread_fails(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Detaching with wrong thread_id fails."""
        # Attach to topic 123
        await destination_manager.attach(
            session_id="test-session",
            path=session_jsonl,
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 123),
        )

        # Try to detach topic 456 - should fail
        result = await destination_manager.detach(
            session_id="test-session",
            destination_type="telegram",
            identifier=make_telegram_identifier("-1001234567890", 456),
        )
        assert result is False

        # Original destination still exists
        destinations = destination_manager.get_destinations("test-session")
        assert len(destinations) == 1


class TestRestoreFromConfigWithThreadId:
    """Tests for restore_from_config with thread_id."""

    @pytest.mark.asyncio
    async def test_restore_preserves_thread_id(
        self,
        mock_config_manager: MagicMock,
        on_session_start: AsyncMock,
        on_session_stop: AsyncMock,
        session_jsonl: Path,
    ) -> None:
        """restore_from_config preserves thread_id in identifier."""
        mock_config_manager.load.return_value = [
            SessionConfig(
                session_id="session-1",
                path=session_jsonl,
                destinations=SessionDestinations(
                    telegram=[
                        TelegramDestination(chat_id="-1001234567890", thread_id=123),
                        TelegramDestination(chat_id="-1001234567890", thread_id=456),
                    ],
                    slack=[],
                ),
            ),
        ]

        manager = DestinationManager(
            _config=mock_config_manager,
            _on_session_start=on_session_start,
            _on_session_stop=on_session_stop,
        )

        await manager.restore_from_config()

        destinations = manager.get_destinations("session-1")
        assert len(destinations) == 2
        identifiers = [d.identifier for d in destinations]
        assert "-1001234567890:123" in identifiers
        assert "-1001234567890:456" in identifiers


# ---------------------------------------------------------------------------
# Module Imports Tests
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports."""

    def test_import_helpers_from_destinations(self) -> None:
        """Can import identifier helpers from destinations module."""
        from claude_session_player.watcher.destinations import (
            make_telegram_identifier,
            parse_telegram_identifier,
        )

        assert callable(make_telegram_identifier)
        assert callable(parse_telegram_identifier)

    def test_import_helpers_from_watcher_package(self) -> None:
        """Can import identifier helpers from watcher package."""
        from claude_session_player.watcher import (
            make_telegram_identifier,
            parse_telegram_identifier,
        )

        assert callable(make_telegram_identifier)
        assert callable(parse_telegram_identifier)


# ---------------------------------------------------------------------------
# Integration Tests: Message Sending to Topics
# ---------------------------------------------------------------------------


@dataclass
class MockTelegramPublisherWithThreads:
    """Mock TelegramPublisher that tracks message_thread_id."""

    token: str | None = None
    validated: bool = False
    sent_messages: list[dict] = field(default_factory=list)
    edited_messages: list[dict] = field(default_factory=list)
    _next_message_id: int = field(default=1, repr=False)

    async def validate(self) -> None:
        self.validated = True

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: object = None,
        message_thread_id: int | None = None,
    ) -> int:
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
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: object = None,
    ) -> bool:
        self.edited_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        })
        return True

    async def close(self) -> None:
        pass


class TestSendMessageToTopic:
    """Integration tests for sending messages to Telegram topics."""

    @pytest.mark.asyncio
    async def test_send_message_includes_thread_id(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Messages sent to topic destination include thread_id."""
        from claude_session_player.watcher.config import BotConfig, ConfigManager
        from claude_session_player.watcher.service import WatcherService

        # Create temporary config
        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        config_manager._bot_config = BotConfig(telegram_token="test-token")

        mock_publisher = MockTelegramPublisherWithThreads(token="test-token")

        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            telegram_publisher=mock_publisher,
            port=18080,
        )

        try:
            await service.start()
            await service.watch("test-session", session_jsonl)

            # Attach to a topic (thread_id=123)
            identifier = make_telegram_identifier("-1001234567890", 123)
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_jsonl,
                destination_type="telegram",
                identifier=identifier,
            )

            # Send a user block event
            from claude_session_player.events import (
                AddBlock,
                Block,
                BlockType,
                UserContent,
            )

            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello from topic!"),
            )
            await service._publish_to_messaging("test-session", AddBlock(block=user_block))

            # Verify message was sent with thread_id
            assert len(mock_publisher.sent_messages) == 1
            msg = mock_publisher.sent_messages[0]
            assert msg["chat_id"] == "-1001234567890"
            assert msg["message_thread_id"] == 123

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_send_message_without_thread_id(
        self,
        destination_manager: DestinationManager,
        session_jsonl: Path,
    ) -> None:
        """Messages sent to chat without topic have thread_id=None."""
        from claude_session_player.watcher.config import BotConfig, ConfigManager
        from claude_session_player.watcher.service import WatcherService

        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        config_manager._bot_config = BotConfig(telegram_token="test-token")

        mock_publisher = MockTelegramPublisherWithThreads(token="test-token")

        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            telegram_publisher=mock_publisher,
            port=18081,
        )

        try:
            await service.start()
            await service.watch("test-session", session_jsonl)

            # Attach without thread_id
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_jsonl,
                destination_type="telegram",
                identifier="-1001234567890",
            )

            from claude_session_player.events import (
                AddBlock,
                Block,
                BlockType,
                UserContent,
            )

            user_block = Block(
                id="user-1",
                type=BlockType.USER,
                content=UserContent(text="Hello from General!"),
            )
            await service._publish_to_messaging("test-session", AddBlock(block=user_block))

            # Verify message was sent without thread_id
            assert len(mock_publisher.sent_messages) == 1
            msg = mock_publisher.sent_messages[0]
            assert msg["chat_id"] == "-1001234567890"
            assert msg["message_thread_id"] is None

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_replay_includes_thread_id(
        self,
        session_jsonl: Path,
    ) -> None:
        """Replay to topic destination includes thread_id."""
        from claude_session_player.watcher.config import BotConfig, ConfigManager
        from claude_session_player.watcher.service import WatcherService
        from claude_session_player.events import (
            AddBlock,
            Block,
            BlockType,
            UserContent,
        )

        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        config_manager._bot_config = BotConfig(telegram_token="test-token")

        mock_publisher = MockTelegramPublisherWithThreads(token="test-token")

        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            telegram_publisher=mock_publisher,
            port=18082,
        )

        try:
            await service.start()
            await service.watch("test-session", session_jsonl)

            # Add events to buffer
            for i in range(3):
                user_block = Block(
                    id=f"user-{i}",
                    type=BlockType.USER,
                    content=UserContent(text=f"Message {i}"),
                )
                service.event_buffer.add_event("test-session", AddBlock(block=user_block))

            # Replay to topic
            identifier = make_telegram_identifier("-1001234567890", 456)
            replayed = await service.replay_to_destination(
                session_id="test-session",
                destination_type="telegram",
                identifier=identifier,
                count=3,
            )

            assert replayed == 3
            assert len(mock_publisher.sent_messages) == 1
            msg = mock_publisher.sent_messages[0]
            assert msg["chat_id"] == "-1001234567890"
            assert msg["message_thread_id"] == 456

        finally:
            await service.stop()


# ---------------------------------------------------------------------------
# API Endpoint Tests for Thread ID
# ---------------------------------------------------------------------------


class TestAPIThreadIdValidation:
    """Tests for API endpoint thread_id handling."""

    @pytest.mark.asyncio
    async def test_attach_rejects_thread_id_1(self, session_jsonl: Path) -> None:
        """API rejects thread_id=1 (reserved for General topic)."""
        from aiohttp.test_utils import TestClient, TestServer

        from claude_session_player.watcher.config import ConfigManager
        from claude_session_player.watcher.service import WatcherService

        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            port=18083,
        )

        try:
            await service.start()

            # Build test app using the service's API
            app = service.api.create_app()

            async with TestClient(TestServer(app)) as client:
                resp = await client.post(
                    "/attach",
                    json={
                        "session_id": "test-session",
                        "path": str(session_jsonl),
                        "destination": {
                            "type": "telegram",
                            "chat_id": "-1001234567890",
                            "thread_id": 1,  # Should be rejected
                        },
                    },
                )
                assert resp.status == 400
                data = await resp.json()
                assert "thread_id=1" in data["error"] or "General" in data["error"]

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_attach_accepts_valid_thread_id(self, session_jsonl: Path) -> None:
        """API accepts valid thread_id values."""
        from aiohttp.test_utils import TestClient, TestServer

        from claude_session_player.watcher.config import BotConfig, ConfigManager
        from claude_session_player.watcher.service import WatcherService

        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        config_manager.set_bot_config(BotConfig(telegram_token="test-token"))

        mock_publisher = MockTelegramPublisherWithThreads(token="test-token")
        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            telegram_publisher=mock_publisher,
            port=18084,
        )

        try:
            await service.start()
            await service.watch("test-session", session_jsonl)

            app = service.api.create_app()

            # Mock the _validate_destination to skip actual API calls
            with patch.object(service.api, "_validate_destination", new_callable=AsyncMock):
                async with TestClient(TestServer(app)) as client:
                    resp = await client.post(
                        "/attach",
                        json={
                            "session_id": "test-session",
                            "path": str(session_jsonl),
                            "destination": {
                                "type": "telegram",
                                "chat_id": "-1001234567890",
                                "thread_id": 123,
                            },
                        },
                    )
                    assert resp.status == 201  # 201 Created for new attachment
                    data = await resp.json()
                    assert data["attached"] is True

        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_list_sessions_includes_thread_id(self, session_jsonl: Path) -> None:
        """GET /sessions response includes thread_id for topics."""
        from aiohttp.test_utils import TestClient, TestServer

        from claude_session_player.watcher.config import BotConfig, ConfigManager
        from claude_session_player.watcher.service import WatcherService

        config_path = session_jsonl.parent / "config.yaml"
        state_dir = session_jsonl.parent / "state"
        state_dir.mkdir()

        config_manager = ConfigManager(config_path)
        config_manager.set_bot_config(BotConfig(telegram_token="test-token"))

        mock_publisher = MockTelegramPublisherWithThreads(token="test-token")
        service = WatcherService(
            config_path=config_path,
            state_dir=state_dir,
            config_manager=config_manager,
            telegram_publisher=mock_publisher,
            port=18085,
        )

        try:
            await service.start()
            await service.watch("test-session", session_jsonl)

            # Attach with thread_id
            identifier = make_telegram_identifier("-1001234567890", 789)
            await service.destination_manager.attach(
                session_id="test-session",
                path=session_jsonl,
                destination_type="telegram",
                identifier=identifier,
            )

            app = service.api.create_app()

            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/sessions")
                assert resp.status == 200
                data = await resp.json()

                session = data["sessions"][0]
                tg_dest = session["destinations"]["telegram"][0]
                assert tg_dest["chat_id"] == "-1001234567890"
                assert tg_dest["thread_id"] == 789

        finally:
            await service.stop()
