"""Tests for expired binding cleanup in WatcherService.

Tests the background task that periodically removes bindings that have been
expired for more than 24 hours.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from claude_session_player.watcher.debouncer import MessageDebouncer
from claude_session_player.watcher.destinations import AttachedDestination
from claude_session_player.watcher.event_buffer import EventBufferManager
from claude_session_player.watcher.message_binding import (
    MessageBinding,
    MessageBindingManager,
)
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
        is_live: bool = True,
    ) -> bool:
        """Mock updating a session message."""
        self.updated_messages.append({
            "chat_id": chat_id,
            "message_id": message_id,
            "content": content,
            "is_live": is_live,
        })
        return True

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
def telegram_dest() -> AttachedDestination:
    """Create a Telegram destination."""
    return AttachedDestination(
        type="telegram",
        identifier="123456789",
        attached_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def watcher_service(
    temp_config_path: Path,
    temp_state_dir: Path,
    mock_telegram_publisher: MockTelegramPublisher,
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
        host="127.0.0.1",
        port=8950,
    )
    return service


# --- Tests for Cleanup Task Configuration ---


class TestCleanupTaskConfiguration:
    """Tests for cleanup task configuration and defaults."""

    def test_cleanup_interval_default(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Default cleanup interval is 1 hour."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service._cleanup_interval == 3600

    def test_binding_max_expired_age_default(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Default max expired age is 24 hours."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service._binding_max_expired_age == 86400

    def test_cleanup_task_initially_none(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Cleanup task is None before service starts."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        assert service._cleanup_task is None


# --- Tests for Cleanup Logic ---


class TestCleanupExpiredBindings:
    """Tests for _cleanup_expired_bindings method."""

    async def test_removes_binding_expired_more_than_24_hours(
        self, watcher_service: WatcherService, telegram_dest: AttachedDestination
    ) -> None:
        """Bindings expired for more than 24 hours are removed."""
        # Create a binding that expired 25 hours ago
        # (created 25 hours + 30 seconds TTL ago)
        old_created_at = datetime.now(timezone.utc) - timedelta(hours=25, seconds=30)
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="12345",
            created_at=old_created_at,
            ttl_seconds=30,  # Expired immediately after creation
        )
        watcher_service.message_bindings.add_binding(binding)

        # Verify binding exists
        assert watcher_service.message_bindings.get_all_bindings() == [binding]

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # Binding should be removed
        assert watcher_service.message_bindings.get_all_bindings() == []

    async def test_does_not_remove_binding_expired_less_than_24_hours(
        self, watcher_service: WatcherService, telegram_dest: AttachedDestination
    ) -> None:
        """Bindings expired for less than 24 hours are NOT removed."""
        # Create a binding that expired 12 hours ago
        old_created_at = datetime.now(timezone.utc) - timedelta(hours=12, seconds=30)
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="12345",
            created_at=old_created_at,
            ttl_seconds=30,  # Expired immediately after creation
        )
        watcher_service.message_bindings.add_binding(binding)

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # Binding should still exist
        assert watcher_service.message_bindings.get_all_bindings() == [binding]

    async def test_does_not_remove_non_expired_binding(
        self, watcher_service: WatcherService, telegram_dest: AttachedDestination
    ) -> None:
        """Active (non-expired) bindings are NOT removed."""
        # Create a binding with large TTL
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="12345",
            created_at=datetime.now(timezone.utc),
            ttl_seconds=300,  # 5 minutes - not expired
        )
        watcher_service.message_bindings.add_binding(binding)

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # Binding should still exist
        assert watcher_service.message_bindings.get_all_bindings() == [binding]

    async def test_clears_debouncer_state_for_removed_bindings(
        self, watcher_service: WatcherService, telegram_dest: AttachedDestination
    ) -> None:
        """Debouncer state is cleared when binding is removed."""
        # Create an expired binding
        old_created_at = datetime.now(timezone.utc) - timedelta(hours=25, seconds=30)
        binding = MessageBinding(
            session_id="test-session",
            preset="desktop",
            destination=telegram_dest,
            message_id="12345",
            created_at=old_created_at,
            ttl_seconds=30,
        )
        watcher_service.message_bindings.add_binding(binding)

        # Simulate that debouncer has state for this message
        debouncer = watcher_service.message_debouncer
        debouncer._last_pushed_content[
            (telegram_dest.type, telegram_dest.identifier, "12345")
        ] = "old content"

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # Debouncer state should be cleared
        assert debouncer.get_last_pushed_content(
            telegram_dest.type, telegram_dest.identifier, "12345"
        ) is None

    async def test_removes_multiple_expired_bindings(
        self, watcher_service: WatcherService
    ) -> None:
        """Multiple expired bindings are removed in one cleanup."""
        # Create multiple expired bindings
        old_created_at = datetime.now(timezone.utc) - timedelta(hours=30)

        for i in range(3):
            dest = AttachedDestination(
                type="telegram",
                identifier=f"chat_{i}",
                attached_at=datetime.now(timezone.utc),
            )
            binding = MessageBinding(
                session_id=f"session-{i}",
                preset="desktop",
                destination=dest,
                message_id=str(i),
                created_at=old_created_at,
                ttl_seconds=30,
            )
            watcher_service.message_bindings.add_binding(binding)

        assert len(watcher_service.message_bindings.get_all_bindings()) == 3

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # All expired bindings should be removed
        assert len(watcher_service.message_bindings.get_all_bindings()) == 0

    async def test_mixed_bindings_only_old_removed(
        self, watcher_service: WatcherService
    ) -> None:
        """Only bindings expired > 24h are removed, others kept."""
        now = datetime.now(timezone.utc)

        # Create binding that expired 30 hours ago (should be removed)
        old_dest = AttachedDestination(
            type="telegram",
            identifier="old_chat",
            attached_at=now,
        )
        old_binding = MessageBinding(
            session_id="old-session",
            preset="desktop",
            destination=old_dest,
            message_id="old",
            created_at=now - timedelta(hours=30, seconds=30),
            ttl_seconds=30,
        )

        # Create binding that expired 1 hour ago (should be kept)
        recent_dest = AttachedDestination(
            type="telegram",
            identifier="recent_chat",
            attached_at=now,
        )
        recent_binding = MessageBinding(
            session_id="recent-session",
            preset="desktop",
            destination=recent_dest,
            message_id="recent",
            created_at=now - timedelta(hours=1, seconds=30),
            ttl_seconds=30,
        )

        # Create active binding (should be kept)
        active_dest = AttachedDestination(
            type="telegram",
            identifier="active_chat",
            attached_at=now,
        )
        active_binding = MessageBinding(
            session_id="active-session",
            preset="desktop",
            destination=active_dest,
            message_id="active",
            created_at=now,
            ttl_seconds=300,
        )

        watcher_service.message_bindings.add_binding(old_binding)
        watcher_service.message_bindings.add_binding(recent_binding)
        watcher_service.message_bindings.add_binding(active_binding)

        assert len(watcher_service.message_bindings.get_all_bindings()) == 3

        # Run cleanup
        await watcher_service._cleanup_expired_bindings()

        # Only old binding should be removed
        remaining = watcher_service.message_bindings.get_all_bindings()
        assert len(remaining) == 2
        session_ids = {b.session_id for b in remaining}
        assert "old-session" not in session_ids
        assert "recent-session" in session_ids
        assert "active-session" in session_ids

    async def test_handles_no_bindings_gracefully(
        self, watcher_service: WatcherService
    ) -> None:
        """Cleanup handles empty bindings list gracefully."""
        # No bindings exist
        assert len(watcher_service.message_bindings.get_all_bindings()) == 0

        # Should not raise
        await watcher_service._cleanup_expired_bindings()

        assert len(watcher_service.message_bindings.get_all_bindings()) == 0

    async def test_handles_no_message_bindings_manager(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Cleanup handles missing message_bindings gracefully."""
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )
        service.message_bindings = None

        # Should not raise
        await service._cleanup_expired_bindings()


# --- Tests for Debouncer clear_message ---


class TestDebouncerClearMessage:
    """Tests for MessageDebouncer.clear_message method."""

    async def test_clears_pending_update(self) -> None:
        """clear_message cancels any pending update."""
        debouncer = MessageDebouncer()

        # Schedule an update
        call_count = 0

        async def update_fn() -> None:
            nonlocal call_count
            call_count += 1

        await debouncer.schedule_update(
            destination_type="telegram",
            identifier="123",
            message_id="456",
            update_fn=update_fn,
            content="test content",
        )

        assert debouncer.has_pending("telegram", "123", "456")

        # Clear the message
        await debouncer.clear_message("telegram", "123", "456")

        assert not debouncer.has_pending("telegram", "123", "456")

        # Wait a bit to ensure the update would have fired
        await asyncio.sleep(0.6)
        assert call_count == 0  # Update should not have been called

    async def test_clears_last_pushed_content(self) -> None:
        """clear_message removes content tracking."""
        debouncer = MessageDebouncer()

        # Set some content tracking manually
        debouncer._last_pushed_content[("telegram", "123", "456")] = "old content"

        # Clear the message
        await debouncer.clear_message("telegram", "123", "456")

        assert debouncer.get_last_pushed_content("telegram", "123", "456") is None

    async def test_handles_nonexistent_message(self) -> None:
        """clear_message handles non-existent message gracefully."""
        debouncer = MessageDebouncer()

        # Should not raise
        await debouncer.clear_message("telegram", "nonexistent", "message")

    async def test_clears_both_pending_and_content(self) -> None:
        """clear_message clears both pending update and content tracking."""
        debouncer = MessageDebouncer(telegram_delay_ms=1000)

        # Schedule an update (which sets pending)
        async def update_fn() -> None:
            pass

        await debouncer.schedule_update(
            destination_type="telegram",
            identifier="123",
            message_id="456",
            update_fn=update_fn,
            content="test content",
        )

        # Also set last pushed content
        debouncer._last_pushed_content[("telegram", "123", "456")] = "previous"

        # Clear the message
        await debouncer.clear_message("telegram", "123", "456")

        # Both should be cleared
        assert not debouncer.has_pending("telegram", "123", "456")
        assert debouncer.get_last_pushed_content("telegram", "123", "456") is None


# --- Tests for Cleanup Loop Behavior ---


class TestCleanupLoopBehavior:
    """Tests for _cleanup_expired_bindings_loop behavior."""

    async def test_loop_handles_cancelled_error(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Cleanup loop exits gracefully on CancelledError."""
        # Create service without starting it
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        # Start only the cleanup task directly
        task = asyncio.create_task(service._cleanup_expired_bindings_loop())

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Cancel the task
        task.cancel()

        # Wait for it to finish - should not raise
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Task should be cancelled or done
        assert task.cancelled() or task.done()

    async def test_cleanup_method_called_in_loop(
        self, temp_config_path: Path, temp_state_dir: Path
    ) -> None:
        """Cleanup method is called periodically in the loop."""
        # Create service without starting it
        service = WatcherService(
            config_path=temp_config_path,
            state_dir=temp_state_dir,
        )

        # Set a very short interval for testing
        service._cleanup_interval = 0.01  # 10ms

        # Track cleanup calls
        cleanup_call_count = 0
        original_cleanup = service._cleanup_expired_bindings

        async def mock_cleanup() -> None:
            nonlocal cleanup_call_count
            cleanup_call_count += 1
            await original_cleanup()

        service._cleanup_expired_bindings = mock_cleanup

        # Start the cleanup task directly
        task = asyncio.create_task(service._cleanup_expired_bindings_loop())

        # Wait for a few cleanup cycles
        await asyncio.sleep(0.05)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have been called at least once
        assert cleanup_call_count >= 1
