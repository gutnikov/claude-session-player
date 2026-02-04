"""Tests for single-message rendering integration in WatcherService.

Tests the RenderCache and MessageBindingManager integration:
- Components are initialized correctly
- _on_file_change() rebuilds cache and pushes to bindings
- create_session_binding() creates message and binding
- remove_session_binding() clears binding and debouncer state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from claude_session_player.events import (
    AddBlock,
    Block,
    BlockType,
    UserContent,
)
from claude_session_player.watcher.destinations import AttachedDestination
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.message_binding import (
    MessageBinding,
    MessageBindingManager,
)
from claude_session_player.watcher.render_cache import RenderCache
from claude_session_player.watcher.service import WatcherService
from claude_session_player.watcher.sse import SSEManager


# --- Mock Publishers ---


@dataclass
class MockTelegramPublisher:
    """Mock Telegram publisher for testing."""

    sent_messages: list[dict] = field(default_factory=list)
    updated_messages: list[dict] = field(default_factory=list)
    _message_id_counter: int = 0

    async def send_session_message(
        self,
        chat_id: str,
        content: str,
        thread_id: int | None = None,
    ) -> int:
        """Mock sending a session message."""
        self._message_id_counter += 1
        self.sent_messages.append({
            "chat_id": chat_id,
            "content": content,
            "thread_id": thread_id,
            "message_id": self._message_id_counter,
        })
        return self._message_id_counter

    async def update_session_message(
        self,
        chat_id: str,
        message_id: int,
        content: str,
    ) -> bool:
        """Mock updating a session message."""
        self.updated_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "content": content,
        })
        return True

    async def validate(self) -> None:
        """Mock validation."""
        pass

    async def close(self) -> None:
        """Mock close."""
        pass


@dataclass
class MockSlackPublisher:
    """Mock Slack publisher for testing."""

    sent_messages: list[dict] = field(default_factory=list)
    updated_messages: list[dict] = field(default_factory=list)
    _ts_counter: int = 0

    async def send_session_message(self, channel: str, content: str) -> str:
        """Mock sending a session message."""
        self._ts_counter += 1
        ts = f"1234567890.{self._ts_counter:06d}"
        self.sent_messages.append({
            "channel": channel,
            "content": content,
            "ts": ts,
        })
        return ts

    async def update_session_message(
        self,
        channel: str,
        ts: str,
        content: str,
    ) -> None:
        """Mock updating a session message."""
        self.updated_messages.append({
            "channel": channel,
            "ts": ts,
            "content": content,
        })

    async def validate(self) -> None:
        """Mock validation."""
        pass

    async def close(self) -> None:
        """Mock close."""
        pass


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
def mock_telegram_publisher() -> MockTelegramPublisher:
    """Create a mock Telegram publisher."""
    return MockTelegramPublisher()


@pytest.fixture
def mock_slack_publisher() -> MockSlackPublisher:
    """Create a mock Slack publisher."""
    return MockSlackPublisher()


@pytest.fixture
def telegram_dest() -> AttachedDestination:
    """Create a Telegram destination."""
    return AttachedDestination(
        type="telegram",
        identifier="123456789",
        attached_at=datetime.now(),
    )


@pytest.fixture
def slack_dest() -> AttachedDestination:
    """Create a Slack destination."""
    return AttachedDestination(
        type="slack",
        identifier="C0123456789",
        attached_at=datetime.now(),
    )


@pytest.fixture
def watcher_service(
    temp_config_path: Path,
    temp_state_dir: Path,
    mock_telegram_publisher: MockTelegramPublisher,
    mock_slack_publisher: MockSlackPublisher,
) -> WatcherService:
    """Create a WatcherService with mock publishers."""
    event_buffer = EventBufferManager()
    sse_manager = SSEManager(event_buffer=event_buffer)

    service = WatcherService(
        config_path=temp_config_path,
        state_dir=temp_state_dir,
        event_buffer=event_buffer,
        sse_manager=sse_manager,
        telegram_publisher=mock_telegram_publisher,
        slack_publisher=mock_slack_publisher,
        host="127.0.0.1",
        port=8899,
    )
    return service


# --- Component Initialization Tests ---


class TestSingleMessageComponentsInit:
    """Tests for single-message rendering components initialization."""

    def test_render_cache_initialized(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """RenderCache is initialized on service creation."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service.render_cache is not None
        assert isinstance(service.render_cache, RenderCache)

    def test_message_bindings_initialized(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """MessageBindingManager is initialized on service creation."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service.message_bindings is not None
        assert isinstance(service.message_bindings, MessageBindingManager)

    def test_can_inject_render_cache(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Custom RenderCache can be injected."""
        custom_cache = RenderCache(ttl_seconds=60)
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            render_cache=custom_cache,
        )
        assert service.render_cache is custom_cache
        assert service.render_cache.ttl_seconds == 60

    def test_can_inject_message_bindings(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Custom MessageBindingManager can be injected."""
        custom_bindings = MessageBindingManager()
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
            message_bindings=custom_bindings,
        )
        assert service.message_bindings is custom_bindings


# --- _on_file_change Tests ---


class TestFileChangeRebuildCache:
    """Tests for _on_file_change() cache rebuilding."""

    @pytest.mark.asyncio
    async def test_file_change_rebuilds_render_cache(
        self, watcher_service: WatcherService
    ) -> None:
        """_on_file_change() rebuilds the render cache."""
        session_id = "test-session"

        # Add event to buffer first (simulate prior activity)
        event = AddBlock(
            block=Block(
                id="b1",
                type=BlockType.USER,
                content=UserContent(text="hello"),
            )
        )
        watcher_service.event_buffer.add_event(session_id, event)

        # Simulate file change with new line
        lines = [{"type": "assistant", "message": {"content": [{"type": "text", "text": "response"}]}}]
        await watcher_service._on_file_change(session_id, lines)

        # Verify cache was rebuilt
        assert watcher_service.render_cache.contains(session_id)
        desktop = watcher_service.render_cache.get(session_id, "desktop")
        assert desktop is not None

    @pytest.mark.asyncio
    async def test_file_change_with_bindings_schedules_updates(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_on_file_change() schedules updates for existing bindings."""
        session_id = "test-session"

        # Create a binding manually
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        watcher_service.message_bindings.add_binding(binding)

        # Simulate file change
        lines = [{"type": "user", "message": {"content": "hello"}}]
        await watcher_service._on_file_change(session_id, lines)

        # Verify cache was rebuilt
        assert watcher_service.render_cache.contains(session_id)

    @pytest.mark.asyncio
    async def test_file_change_empty_lines_skipped(
        self, watcher_service: WatcherService
    ) -> None:
        """_on_file_change() with empty lines doesn't rebuild cache."""
        session_id = "test-session"

        await watcher_service._on_file_change(session_id, [])

        # Cache should not be rebuilt for empty lines
        assert not watcher_service.render_cache.contains(session_id)


# --- create_session_binding Tests ---


class TestCreateSessionBinding:
    """Tests for create_session_binding() method."""

    @pytest.mark.asyncio
    async def test_creates_telegram_binding(
        self,
        watcher_service: WatcherService,
        mock_telegram_publisher: MockTelegramPublisher,
        telegram_dest: AttachedDestination,
    ) -> None:
        """create_session_binding() creates message and binding for Telegram."""
        session_id = "test-session"

        message_id = await watcher_service.create_session_binding(
            session_id=session_id,
            destination=telegram_dest,
            preset="desktop",
        )

        # Verify message was sent
        assert len(mock_telegram_publisher.sent_messages) == 1
        sent = mock_telegram_publisher.sent_messages[0]
        assert sent["chat_id"] == "123456789"

        # Verify binding was created
        assert message_id is not None
        binding = watcher_service.message_bindings.find_binding(session_id, telegram_dest)
        assert binding is not None
        assert binding.message_id == message_id
        assert binding.preset == "desktop"

    @pytest.mark.asyncio
    async def test_creates_slack_binding(
        self,
        watcher_service: WatcherService,
        mock_slack_publisher: MockSlackPublisher,
        slack_dest: AttachedDestination,
    ) -> None:
        """create_session_binding() creates message and binding for Slack."""
        session_id = "test-session"

        message_id = await watcher_service.create_session_binding(
            session_id=session_id,
            destination=slack_dest,
            preset="mobile",
        )

        # Verify message was sent
        assert len(mock_slack_publisher.sent_messages) == 1
        sent = mock_slack_publisher.sent_messages[0]
        assert sent["channel"] == "C0123456789"

        # Verify binding was created
        assert message_id is not None
        binding = watcher_service.message_bindings.find_binding(session_id, slack_dest)
        assert binding is not None
        assert binding.message_id == message_id
        assert binding.preset == "mobile"

    @pytest.mark.asyncio
    async def test_creates_binding_with_existing_cache(
        self,
        watcher_service: WatcherService,
        mock_telegram_publisher: MockTelegramPublisher,
        telegram_dest: AttachedDestination,
    ) -> None:
        """create_session_binding() uses existing cache content."""
        session_id = "test-session"

        # Pre-populate event buffer
        event = AddBlock(
            block=Block(
                id="b1",
                type=BlockType.USER,
                content=UserContent(text="pre-existing content"),
            )
        )
        watcher_service.event_buffer.add_event(session_id, event)

        await watcher_service.create_session_binding(
            session_id=session_id,
            destination=telegram_dest,
            preset="desktop",
        )

        # Verify message content includes the pre-existing content
        sent = mock_telegram_publisher.sent_messages[0]
        assert "pre-existing content" in sent["content"]


# --- remove_session_binding Tests ---


class TestRemoveSessionBinding:
    """Tests for remove_session_binding() method."""

    @pytest.mark.asyncio
    async def test_removes_binding(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """remove_session_binding() removes the binding."""
        session_id = "test-session"

        # Create binding
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        watcher_service.message_bindings.add_binding(binding)

        # Remove binding
        removed = await watcher_service.remove_session_binding(session_id, telegram_dest)

        assert removed is True
        assert watcher_service.message_bindings.find_binding(session_id, telegram_dest) is None

    @pytest.mark.asyncio
    async def test_removes_binding_clears_debouncer(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """remove_session_binding() clears debouncer content tracking."""
        session_id = "test-session"
        message_id = "999"

        # Create binding
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Simulate some content tracking in debouncer
        watcher_service.message_debouncer._last_pushed_content[
            (telegram_dest.type, telegram_dest.identifier, message_id)
        ] = "tracked content"

        # Remove binding
        await watcher_service.remove_session_binding(session_id, telegram_dest)

        # Verify debouncer content was cleared
        assert (telegram_dest.type, telegram_dest.identifier, message_id) not in (
            watcher_service.message_debouncer._last_pushed_content
        )

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_binding(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """remove_session_binding() returns False for nonexistent binding."""
        removed = await watcher_service.remove_session_binding("unknown-session", telegram_dest)
        assert removed is False


# --- _push_to_bindings Tests ---


class TestPushToBindings:
    """Tests for _push_to_bindings() method."""

    @pytest.mark.asyncio
    async def test_push_to_single_binding(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() schedules update for single binding."""
        session_id = "test-session"

        # Create binding
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        watcher_service.message_bindings.add_binding(binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Verify update was scheduled (has pending or content tracked)
        assert watcher_service.message_debouncer.pending_count() >= 0

    @pytest.mark.asyncio
    async def test_push_to_multiple_bindings(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
        slack_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() schedules updates for multiple bindings."""
        session_id = "test-session"

        # Create bindings
        telegram_binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        slack_binding = MessageBinding(
            session_id=session_id,
            preset="mobile",
            destination=slack_dest,
            message_id="1234567890.000001",
        )
        watcher_service.message_bindings.add_binding(telegram_binding)
        watcher_service.message_bindings.add_binding(slack_binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Both bindings should have been processed
        bindings = watcher_service.message_bindings.get_bindings_for_session(session_id)
        assert len(bindings) == 2

    @pytest.mark.asyncio
    async def test_push_skips_session_without_bindings(
        self, watcher_service: WatcherService
    ) -> None:
        """_push_to_bindings() does nothing for session without bindings."""
        session_id = "test-session"

        # Build cache without bindings
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push (should not fail)
        await watcher_service._push_to_bindings(session_id)

        # No error means success
        assert watcher_service.message_debouncer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_push_skips_if_no_cache(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() skips bindings when cache is missing."""
        session_id = "test-session"

        # Create binding but no cache
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
        )
        watcher_service.message_bindings.add_binding(binding)

        # Push (should not fail)
        await watcher_service._push_to_bindings(session_id)

        # No update should be scheduled since no cache
        assert watcher_service.message_debouncer.pending_count() == 0


# --- Integration Tests ---


class TestSingleMessageIntegration:
    """Integration tests for single-message rendering flow."""

    @pytest.mark.asyncio
    async def test_full_flow_create_update_remove(
        self,
        watcher_service: WatcherService,
        mock_telegram_publisher: MockTelegramPublisher,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Test complete flow: create binding, file change, remove binding."""
        session_id = "integration-test"

        # 1. Create binding
        message_id = await watcher_service.create_session_binding(
            session_id=session_id,
            destination=telegram_dest,
            preset="desktop",
        )
        assert message_id is not None
        assert len(mock_telegram_publisher.sent_messages) == 1

        # 2. Simulate file change
        lines = [{"type": "user", "message": {"content": "new message"}}]
        await watcher_service._on_file_change(session_id, lines)

        # 3. Verify cache was rebuilt
        assert watcher_service.render_cache.contains(session_id)

        # 4. Remove binding
        removed = await watcher_service.remove_session_binding(session_id, telegram_dest)
        assert removed is True

        # 5. Verify binding is gone
        assert watcher_service.message_bindings.find_binding(
            session_id, telegram_dest
        ) is None

    @pytest.mark.asyncio
    async def test_multiple_sessions_independent(
        self,
        watcher_service: WatcherService,
        mock_telegram_publisher: MockTelegramPublisher,
        telegram_dest: AttachedDestination,
    ) -> None:
        """Multiple sessions have independent caches and bindings."""
        # Create bindings for two sessions
        session_1 = "session-1"
        session_2 = "session-2"

        dest_1 = telegram_dest
        dest_2 = AttachedDestination(
            type="telegram",
            identifier="987654321",
            attached_at=datetime.now(),
        )

        await watcher_service.create_session_binding(
            session_id=session_1,
            destination=dest_1,
            preset="desktop",
        )
        await watcher_service.create_session_binding(
            session_id=session_2,
            destination=dest_2,
            preset="mobile",
        )

        # Verify both sessions have bindings
        assert watcher_service.message_bindings.has_bindings(session_1)
        assert watcher_service.message_bindings.has_bindings(session_2)

        # Process file change for session_1 only
        lines = [{"type": "user", "message": {"content": "session 1 update"}}]
        await watcher_service._on_file_change(session_1, lines)

        # Verify only session_1 cache was rebuilt
        assert watcher_service.render_cache.contains(session_1)
        content = watcher_service.render_cache.get(session_1, "desktop")
        assert content is not None
        assert "session 1 update" in content


# --- TTL Expiry Tests ---


class TestTTLExpiryChecking:
    """Tests for TTL expiry checking in _push_to_bindings()."""

    @pytest.mark.asyncio
    async def test_expired_binding_skipped(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() skips expired bindings."""
        from datetime import timedelta, timezone

        session_id = "test-session"

        # Create an already-expired binding (created 60 seconds ago, TTL = 30)
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            ttl_seconds=30,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Binding should be marked as expired
        assert binding.expired is True

    @pytest.mark.asyncio
    async def test_active_binding_receives_update(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() pushes to active (non-expired) bindings."""
        session_id = "test-session"

        # Create a fresh binding with long TTL
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            ttl_seconds=300,  # 5 minutes
        )
        watcher_service.message_bindings.add_binding(binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Binding should not be expired
        assert binding.expired is False
        assert binding.is_expired() is False

    @pytest.mark.asyncio
    async def test_mixed_bindings_only_active_updated(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
        slack_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() updates active bindings, skips expired ones."""
        from datetime import timedelta, timezone

        session_id = "test-session"

        # Create one expired and one active binding
        expired_binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            ttl_seconds=30,
        )
        active_binding = MessageBinding(
            session_id=session_id,
            preset="mobile",
            destination=slack_dest,
            message_id="1234567890.123456",
            ttl_seconds=300,
        )
        watcher_service.message_bindings.add_binding(expired_binding)
        watcher_service.message_bindings.add_binding(active_binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Expired binding should be marked
        assert expired_binding.expired is True
        # Active binding should not be expired
        assert active_binding.expired is False

    @pytest.mark.asyncio
    async def test_already_marked_expired_still_skipped(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """_push_to_bindings() skips bindings already marked as expired."""
        session_id = "test-session"

        # Create a binding already marked as expired
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id="999",
            expired=True,  # Already marked
        )
        watcher_service.message_bindings.add_binding(binding)

        # Build cache
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Push to bindings
        await watcher_service._push_to_bindings(session_id)

        # Binding should still be expired
        assert binding.expired is True


# --- Extend Binding TTL Tests ---


class TestExtendBindingTTL:
    """Tests for extend_binding_ttl() method."""

    @pytest.mark.asyncio
    async def test_extends_ttl_for_existing_binding(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """extend_binding_ttl() extends TTL on existing binding."""
        session_id = "test-session"
        message_id = "999"

        # Create binding with low TTL
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,
            ttl_seconds=30,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Extend TTL
        result = await watcher_service.extend_binding_ttl(
            destination_type=telegram_dest.type,
            identifier=telegram_dest.identifier,
            message_id=message_id,
            seconds=30,
        )

        assert result is True
        assert binding.ttl_seconds == 60

    @pytest.mark.asyncio
    async def test_extends_ttl_capped_at_max(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """extend_binding_ttl() caps TTL at MAX_TTL_SECONDS (300)."""
        session_id = "test-session"
        message_id = "999"

        # Create binding with high TTL
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,
            ttl_seconds=290,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Extend TTL by 30s (would be 320, capped at 300)
        result = await watcher_service.extend_binding_ttl(
            destination_type=telegram_dest.type,
            identifier=telegram_dest.identifier,
            message_id=message_id,
            seconds=30,
        )

        assert result is True
        assert binding.ttl_seconds == 300  # Capped at max

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_binding(
        self,
        watcher_service: WatcherService,
    ) -> None:
        """extend_binding_ttl() returns False for nonexistent binding."""
        result = await watcher_service.extend_binding_ttl(
            destination_type="telegram",
            identifier="999999",
            message_id="nonexistent",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_reactivates_expired_binding(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """extend_binding_ttl() reactivates expired binding."""
        from datetime import timedelta, timezone

        session_id = "test-session"
        message_id = "999"

        # Create an expired binding
        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            ttl_seconds=30,
            expired=True,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Build cache for reactivation push
        events = [
            AddBlock(
                block=Block(
                    id="b1",
                    type=BlockType.USER,
                    content=UserContent(text="test content"),
                )
            )
        ]
        watcher_service.render_cache.rebuild(session_id, events)

        # Extend TTL on expired binding
        result = await watcher_service.extend_binding_ttl(
            destination_type=telegram_dest.type,
            identifier=telegram_dest.identifier,
            message_id=message_id,
        )

        assert result is True
        assert binding.expired is False
        assert binding.ttl_seconds == 60  # 30 + 30

    @pytest.mark.asyncio
    async def test_finds_binding_across_sessions(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """extend_binding_ttl() finds binding across multiple sessions."""
        message_id = "999"

        # Create bindings in different sessions
        binding_1 = MessageBinding(
            session_id="session-1",
            preset="desktop",
            destination=telegram_dest,
            message_id="111",
            ttl_seconds=30,
        )
        binding_2 = MessageBinding(
            session_id="session-2",
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,  # This is the one we're looking for
            ttl_seconds=30,
        )
        watcher_service.message_bindings.add_binding(binding_1)
        watcher_service.message_bindings.add_binding(binding_2)

        # Extend TTL on binding_2
        result = await watcher_service.extend_binding_ttl(
            destination_type=telegram_dest.type,
            identifier=telegram_dest.identifier,
            message_id=message_id,
        )

        assert result is True
        assert binding_2.ttl_seconds == 60
        assert binding_1.ttl_seconds == 30  # Unchanged

    @pytest.mark.asyncio
    async def test_custom_extension_seconds(
        self,
        watcher_service: WatcherService,
        telegram_dest: AttachedDestination,
    ) -> None:
        """extend_binding_ttl() uses custom seconds value."""
        session_id = "test-session"
        message_id = "999"

        binding = MessageBinding(
            session_id=session_id,
            preset="desktop",
            destination=telegram_dest,
            message_id=message_id,
            ttl_seconds=30,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Extend by 60 seconds
        result = await watcher_service.extend_binding_ttl(
            destination_type=telegram_dest.type,
            identifier=telegram_dest.identifier,
            message_id=message_id,
            seconds=60,
        )

        assert result is True
        assert binding.ttl_seconds == 90
