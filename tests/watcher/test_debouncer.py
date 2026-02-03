"""Tests for MessageDebouncer."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from claude_session_player.watcher.debouncer import MessageDebouncer, PendingUpdate


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def debouncer() -> MessageDebouncer:
    """Create a debouncer with short delays for testing."""
    return MessageDebouncer(telegram_delay_ms=50, slack_delay_ms=100)


@pytest.fixture
def fast_debouncer() -> MessageDebouncer:
    """Create a debouncer with very short delays for faster tests."""
    return MessageDebouncer(telegram_delay_ms=10, slack_delay_ms=20)


# ---------------------------------------------------------------------------
# Test MessageDebouncer Initialization
# ---------------------------------------------------------------------------


class TestMessageDebouncerInit:
    """Tests for MessageDebouncer initialization."""

    def test_default_delays(self) -> None:
        """Test default delay values."""
        debouncer = MessageDebouncer()
        assert debouncer._telegram_delay == 0.5  # 500ms
        assert debouncer._slack_delay == 2.0  # 2000ms

    def test_custom_delays(self) -> None:
        """Test custom delay values."""
        debouncer = MessageDebouncer(telegram_delay_ms=100, slack_delay_ms=500)
        assert debouncer._telegram_delay == 0.1
        assert debouncer._slack_delay == 0.5

    def test_empty_pending_on_init(self) -> None:
        """Test that pending dict is empty on initialization."""
        debouncer = MessageDebouncer()
        assert debouncer.pending_count() == 0
        assert debouncer._pending == {}


# ---------------------------------------------------------------------------
# Test Delay Selection
# ---------------------------------------------------------------------------


class TestGetDelay:
    """Tests for delay selection based on destination type."""

    def test_telegram_delay(self) -> None:
        """Test Telegram uses telegram delay."""
        debouncer = MessageDebouncer(telegram_delay_ms=100, slack_delay_ms=200)
        assert debouncer._get_delay("telegram") == 0.1

    def test_slack_delay(self) -> None:
        """Test Slack uses slack delay."""
        debouncer = MessageDebouncer(telegram_delay_ms=100, slack_delay_ms=200)
        assert debouncer._get_delay("slack") == 0.2


# ---------------------------------------------------------------------------
# Test Single Update Execution
# ---------------------------------------------------------------------------


class TestSingleUpdate:
    """Tests for single update execution after delay."""

    @pytest.mark.asyncio
    async def test_single_update_executes_after_delay(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that a single update executes after the delay."""
        update_fn = AsyncMock()
        content = {"text": "test content"}

        await fast_debouncer.schedule_update(
            destination_type="telegram",
            identifier="123",
            message_id="msg1",
            update_fn=update_fn,
            content=content,
        )

        # Should be pending initially
        assert fast_debouncer.pending_count() == 1
        assert fast_debouncer.has_pending("telegram", "123", "msg1")
        update_fn.assert_not_called()

        # Wait for delay to expire
        await asyncio.sleep(0.02)  # 20ms > 10ms telegram delay

        # Should have executed
        update_fn.assert_called_once()
        assert fast_debouncer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_slack_update_uses_longer_delay(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that Slack updates use the longer delay."""
        update_fn = AsyncMock()

        await fast_debouncer.schedule_update(
            destination_type="slack",
            identifier="C123",
            message_id="ts123",
            update_fn=update_fn,
            content="test",
        )

        # Wait less than slack delay but more than telegram delay
        await asyncio.sleep(0.015)  # 15ms

        # Should still be pending (slack delay is 20ms)
        assert fast_debouncer.pending_count() == 1
        update_fn.assert_not_called()

        # Wait for slack delay to complete
        await asyncio.sleep(0.015)  # total 30ms > 20ms

        update_fn.assert_called_once()


# ---------------------------------------------------------------------------
# Test Rapid Update Coalescing
# ---------------------------------------------------------------------------


class TestRapidUpdateCoalescing:
    """Tests for coalescing rapid updates to the same message."""

    @pytest.mark.asyncio
    async def test_rapid_updates_coalesced(self, fast_debouncer: MessageDebouncer) -> None:
        """Test that rapid updates to the same message are coalesced."""
        call_order = []

        async def update1() -> None:
            call_order.append("update1")

        async def update2() -> None:
            call_order.append("update2")

        async def update3() -> None:
            call_order.append("update3")

        # Schedule three rapid updates
        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update1, "content1"
        )
        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update2, "content2"
        )
        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update3, "content3"
        )

        # Should only have one pending update
        assert fast_debouncer.pending_count() == 1

        # Latest content should be stored
        assert fast_debouncer.get_pending_content("telegram", "123", "msg1") == "content3"

        # Wait for execution
        await asyncio.sleep(0.02)

        # Only the last update should have executed
        assert call_order == ["update3"]

    @pytest.mark.asyncio
    async def test_different_messages_not_coalesced(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that updates to different messages are not coalesced."""
        update1 = AsyncMock()
        update2 = AsyncMock()

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update1, "content1"
        )
        await fast_debouncer.schedule_update(
            "telegram", "123", "msg2", update2, "content2"
        )

        # Both should be pending
        assert fast_debouncer.pending_count() == 2
        assert fast_debouncer.has_pending("telegram", "123", "msg1")
        assert fast_debouncer.has_pending("telegram", "123", "msg2")

        # Wait for execution
        await asyncio.sleep(0.02)

        # Both should have executed
        update1.assert_called_once()
        update2.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_identifiers_not_coalesced(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that updates to different identifiers are not coalesced."""
        update1 = AsyncMock()
        update2 = AsyncMock()

        await fast_debouncer.schedule_update(
            "telegram", "chat1", "msg1", update1, "content1"
        )
        await fast_debouncer.schedule_update(
            "telegram", "chat2", "msg1", update2, "content2"
        )

        # Both should be pending
        assert fast_debouncer.pending_count() == 2

        # Wait for execution
        await asyncio.sleep(0.02)

        # Both should have executed
        update1.assert_called_once()
        update2.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_destinations_not_coalesced(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that updates to different destination types are not coalesced."""
        telegram_update = AsyncMock()
        slack_update = AsyncMock()

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", telegram_update, "content1"
        )
        await fast_debouncer.schedule_update(
            "slack", "123", "msg1", slack_update, "content2"
        )

        # Both should be pending
        assert fast_debouncer.pending_count() == 2

        # Wait for both delays
        await asyncio.sleep(0.03)

        # Both should have executed
        telegram_update.assert_called_once()
        slack_update.assert_called_once()


# ---------------------------------------------------------------------------
# Test Flush
# ---------------------------------------------------------------------------


class TestFlush:
    """Tests for flush functionality."""

    @pytest.mark.asyncio
    async def test_flush_executes_immediately(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that flush executes pending updates immediately."""
        update_fn = AsyncMock()

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update_fn, "content"
        )

        # Still pending
        assert fast_debouncer.pending_count() == 1
        update_fn.assert_not_called()

        # Flush immediately
        await fast_debouncer.flush()

        # Should have executed immediately
        update_fn.assert_called_once()
        assert fast_debouncer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_flush_executes_multiple_updates(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that flush executes all pending updates."""
        updates = [AsyncMock() for _ in range(3)]

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", updates[0], "content1"
        )
        await fast_debouncer.schedule_update(
            "slack", "C123", "ts1", updates[1], "content2"
        )
        await fast_debouncer.schedule_update(
            "telegram", "456", "msg2", updates[2], "content3"
        )

        assert fast_debouncer.pending_count() == 3

        await fast_debouncer.flush()

        # All should have executed
        for update in updates:
            update.assert_called_once()
        assert fast_debouncer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_flush_empty_is_noop(self, fast_debouncer: MessageDebouncer) -> None:
        """Test that flush on empty debouncer is a no-op."""
        assert fast_debouncer.pending_count() == 0
        await fast_debouncer.flush()  # Should not raise
        assert fast_debouncer.pending_count() == 0

    @pytest.mark.asyncio
    async def test_flush_handles_update_failure(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that flush continues if an update fails."""
        successful_update = AsyncMock()
        failing_update = AsyncMock(side_effect=Exception("API error"))

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", failing_update, "content1"
        )
        await fast_debouncer.schedule_update(
            "telegram", "456", "msg2", successful_update, "content2"
        )

        await fast_debouncer.flush()

        # Both should have been called (failing one should not stop the other)
        failing_update.assert_called_once()
        successful_update.assert_called_once()
        assert fast_debouncer.pending_count() == 0


# ---------------------------------------------------------------------------
# Test Cancel All
# ---------------------------------------------------------------------------


class TestCancelAll:
    """Tests for cancel_all functionality."""

    @pytest.mark.asyncio
    async def test_cancel_prevents_execution(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that cancel_all prevents pending updates from executing."""
        update_fn = AsyncMock()

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", update_fn, "content"
        )

        assert fast_debouncer.pending_count() == 1

        await fast_debouncer.cancel_all()

        # Should be cancelled
        assert fast_debouncer.pending_count() == 0

        # Wait to ensure it doesn't execute
        await asyncio.sleep(0.02)
        update_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_multiple_pending(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that cancel_all cancels all pending updates."""
        updates = [AsyncMock() for _ in range(3)]

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", updates[0], "content1"
        )
        await fast_debouncer.schedule_update(
            "slack", "C123", "ts1", updates[1], "content2"
        )
        await fast_debouncer.schedule_update(
            "telegram", "456", "msg2", updates[2], "content3"
        )

        await fast_debouncer.cancel_all()

        assert fast_debouncer.pending_count() == 0

        # Wait and verify none executed
        await asyncio.sleep(0.03)
        for update in updates:
            update.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_empty_is_noop(self, fast_debouncer: MessageDebouncer) -> None:
        """Test that cancel_all on empty debouncer is a no-op."""
        assert fast_debouncer.pending_count() == 0
        await fast_debouncer.cancel_all()  # Should not raise
        assert fast_debouncer.pending_count() == 0


# ---------------------------------------------------------------------------
# Test Error Handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling during update execution."""

    @pytest.mark.asyncio
    async def test_update_failure_logged_not_raised(
        self, fast_debouncer: MessageDebouncer
    ) -> None:
        """Test that update failures are logged but don't raise."""
        failing_update = AsyncMock(side_effect=Exception("API error"))

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", failing_update, "content"
        )

        # Wait for execution - should not raise
        await asyncio.sleep(0.02)

        failing_update.assert_called_once()
        assert fast_debouncer.pending_count() == 0


# ---------------------------------------------------------------------------
# Test Utility Methods
# ---------------------------------------------------------------------------


class TestUtilityMethods:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_pending_count(self, fast_debouncer: MessageDebouncer) -> None:
        """Test pending_count returns correct count."""
        assert fast_debouncer.pending_count() == 0

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", AsyncMock(), "content1"
        )
        assert fast_debouncer.pending_count() == 1

        await fast_debouncer.schedule_update(
            "telegram", "456", "msg2", AsyncMock(), "content2"
        )
        assert fast_debouncer.pending_count() == 2

    @pytest.mark.asyncio
    async def test_has_pending(self, fast_debouncer: MessageDebouncer) -> None:
        """Test has_pending returns correct status."""
        assert not fast_debouncer.has_pending("telegram", "123", "msg1")

        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", AsyncMock(), "content"
        )

        assert fast_debouncer.has_pending("telegram", "123", "msg1")
        assert not fast_debouncer.has_pending("telegram", "123", "msg2")
        assert not fast_debouncer.has_pending("slack", "123", "msg1")

    @pytest.mark.asyncio
    async def test_get_pending_content(self, fast_debouncer: MessageDebouncer) -> None:
        """Test get_pending_content returns correct content."""
        assert fast_debouncer.get_pending_content("telegram", "123", "msg1") is None

        content = {"data": "test"}
        await fast_debouncer.schedule_update(
            "telegram", "123", "msg1", AsyncMock(), content
        )

        assert fast_debouncer.get_pending_content("telegram", "123", "msg1") == content
        assert fast_debouncer.get_pending_content("telegram", "123", "msg2") is None


# ---------------------------------------------------------------------------
# Test PendingUpdate Dataclass
# ---------------------------------------------------------------------------


class TestPendingUpdate:
    """Tests for PendingUpdate dataclass."""

    @pytest.mark.asyncio
    async def test_pending_update_creation(self) -> None:
        """Test PendingUpdate can be created."""
        async def dummy() -> None:
            pass

        task = asyncio.create_task(dummy())
        update_fn = AsyncMock()
        content = {"test": "data"}

        pending = PendingUpdate(task=task, update_fn=update_fn, content=content)

        assert pending.task is task
        assert pending.update_fn is update_fn
        assert pending.content == content

        await task  # Clean up


# ---------------------------------------------------------------------------
# Test Module Imports
# ---------------------------------------------------------------------------


class TestModuleImports:
    """Tests for module imports."""

    def test_import_from_debouncer_module(self) -> None:
        """Test direct import from debouncer module."""
        from claude_session_player.watcher.debouncer import (
            MessageDebouncer,
            PendingUpdate,
        )

        assert MessageDebouncer is not None
        assert PendingUpdate is not None

    def test_import_from_watcher_package(self) -> None:
        """Test import from watcher package."""
        from claude_session_player.watcher import MessageDebouncer, PendingUpdate

        assert MessageDebouncer is not None
        assert PendingUpdate is not None

    def test_in_all(self) -> None:
        """Test MessageDebouncer and PendingUpdate are in __all__."""
        from claude_session_player import watcher

        assert "MessageDebouncer" in watcher.__all__
        assert "PendingUpdate" in watcher.__all__
