"""Tests for the EventEmitter class."""

from __future__ import annotations

import asyncio
import logging

import pytest

from claude_session_player.emitter import EventEmitter
from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    Event,
    ToolCallContent,
    UpdateBlock,
    UserContent,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class MockConsumer:
    """A mock consumer for testing."""

    def __init__(self, delay: float = 0) -> None:
        self.events_received: list[Event] = []
        self.delay = delay
        self.call_count = 0

    async def on_event(self, event: Event) -> None:
        """Record received events with optional delay."""
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        self.events_received.append(event)

    def render_block(self, block: Block) -> str:
        """Simple render implementation."""
        return f"[{block.type.value}:{block.id}]"


class FailingConsumer:
    """A consumer that raises exceptions."""

    def __init__(self) -> None:
        self.call_count = 0

    async def on_event(self, event: Event) -> None:
        """Always raise an exception."""
        self.call_count += 1
        raise RuntimeError("Consumer failed intentionally")

    def render_block(self, block: Block) -> str:
        """Simple render implementation."""
        return f"[{block.id}]"


@pytest.fixture
def emitter() -> EventEmitter:
    """Create a fresh EventEmitter instance."""
    return EventEmitter()


@pytest.fixture
def user_block() -> Block:
    """Create a sample user block."""
    return Block(
        id="block-user-1",
        type=BlockType.USER,
        content=UserContent(text="Hello"),
    )


@pytest.fixture
def assistant_block() -> Block:
    """Create a sample assistant block."""
    return Block(
        id="block-assistant-1",
        type=BlockType.ASSISTANT,
        content=AssistantContent(text="Hi there"),
        request_id="req-123",
    )


# ---------------------------------------------------------------------------
# Test subscribe/unsubscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    """Tests for subscribe() method."""

    def test_subscribe_adds_consumer(self, emitter: EventEmitter) -> None:
        """subscribe() adds consumer to list."""
        consumer = MockConsumer()

        emitter.subscribe(consumer)

        assert emitter.subscriber_count == 1

    def test_subscribe_multiple_consumers(self, emitter: EventEmitter) -> None:
        """subscribe() can add multiple consumers."""
        consumer1 = MockConsumer()
        consumer2 = MockConsumer()
        consumer3 = MockConsumer()

        emitter.subscribe(consumer1)
        emitter.subscribe(consumer2)
        emitter.subscribe(consumer3)

        assert emitter.subscriber_count == 3

    def test_subscribe_same_consumer_twice(self, emitter: EventEmitter) -> None:
        """subscribe() allows same consumer twice (list semantics)."""
        consumer = MockConsumer()

        emitter.subscribe(consumer)
        emitter.subscribe(consumer)

        assert emitter.subscriber_count == 2


class TestUnsubscribe:
    """Tests for unsubscribe() method."""

    def test_unsubscribe_removes_consumer(self, emitter: EventEmitter) -> None:
        """unsubscribe() removes consumer from list."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)

        emitter.unsubscribe(consumer)

        assert emitter.subscriber_count == 0

    def test_unsubscribe_not_subscribed_raises(self, emitter: EventEmitter) -> None:
        """unsubscribe() raises ValueError for non-subscribed consumer."""
        consumer = MockConsumer()

        with pytest.raises(ValueError):
            emitter.unsubscribe(consumer)

    def test_unsubscribe_one_of_multiple(self, emitter: EventEmitter) -> None:
        """unsubscribe() removes only the specified consumer."""
        consumer1 = MockConsumer()
        consumer2 = MockConsumer()
        emitter.subscribe(consumer1)
        emitter.subscribe(consumer2)

        emitter.unsubscribe(consumer1)

        assert emitter.subscriber_count == 1


# ---------------------------------------------------------------------------
# Test emit
# ---------------------------------------------------------------------------


class TestEmit:
    """Tests for emit() method."""

    @pytest.mark.asyncio
    async def test_emit_dispatches_to_consumer(
        self, emitter: EventEmitter, user_block: Block
    ) -> None:
        """emit() dispatches event to subscribed consumer."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        event = AddBlock(block=user_block)

        await emitter.emit(event)
        # Allow task to complete
        await asyncio.sleep(0.01)

        assert len(consumer.events_received) == 1
        assert consumer.events_received[0] is event

    @pytest.mark.asyncio
    async def test_emit_dispatches_to_multiple_consumers(
        self, emitter: EventEmitter, user_block: Block
    ) -> None:
        """emit() dispatches event to all subscribed consumers."""
        consumer1 = MockConsumer()
        consumer2 = MockConsumer()
        consumer3 = MockConsumer()
        emitter.subscribe(consumer1)
        emitter.subscribe(consumer2)
        emitter.subscribe(consumer3)
        event = AddBlock(block=user_block)

        await emitter.emit(event)
        await asyncio.sleep(0.01)

        assert len(consumer1.events_received) == 1
        assert len(consumer2.events_received) == 1
        assert len(consumer3.events_received) == 1
        assert consumer1.events_received[0] is event
        assert consumer2.events_received[0] is event
        assert consumer3.events_received[0] is event

    @pytest.mark.asyncio
    async def test_emit_fire_and_forget(self, emitter: EventEmitter) -> None:
        """emit() returns immediately without waiting for consumers."""
        # Consumer with a delay to verify fire-and-forget behavior
        slow_consumer = MockConsumer(delay=0.1)
        emitter.subscribe(slow_consumer)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        # emit() should return immediately
        await emitter.emit(event)

        # Yield control to event loop so task starts
        await asyncio.sleep(0)

        # Consumer should have been called but not finished yet
        assert slow_consumer.call_count == 1
        assert len(slow_consumer.events_received) == 0  # Not yet completed

        # Wait for consumer to finish
        await asyncio.sleep(0.15)
        assert len(slow_consumer.events_received) == 1

    @pytest.mark.asyncio
    async def test_emit_no_subscribers(self, emitter: EventEmitter) -> None:
        """emit() works with no subscribers (no-op)."""
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        # Should not raise
        await emitter.emit(event)

    @pytest.mark.asyncio
    async def test_emit_multiple_events(
        self, emitter: EventEmitter, user_block: Block, assistant_block: Block
    ) -> None:
        """emit() can dispatch multiple events in sequence."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)

        await emitter.emit(AddBlock(block=user_block))
        await emitter.emit(AddBlock(block=assistant_block))
        await emitter.emit(ClearAll())
        await asyncio.sleep(0.01)

        assert len(consumer.events_received) == 3
        assert isinstance(consumer.events_received[0], AddBlock)
        assert isinstance(consumer.events_received[1], AddBlock)
        assert isinstance(consumer.events_received[2], ClearAll)


class TestEmitEventTypes:
    """Tests for emit() with different event types."""

    @pytest.mark.asyncio
    async def test_emit_add_block(
        self, emitter: EventEmitter, user_block: Block
    ) -> None:
        """emit() dispatches AddBlock events."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        event = AddBlock(block=user_block)

        await emitter.emit(event)
        await asyncio.sleep(0.01)

        assert isinstance(consumer.events_received[0], AddBlock)
        assert consumer.events_received[0].block is user_block

    @pytest.mark.asyncio
    async def test_emit_update_block(self, emitter: EventEmitter) -> None:
        """emit() dispatches UpdateBlock events."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        content = ToolCallContent(
            tool_name="Read",
            tool_use_id="tool-1",
            label="file.txt",
            result="File contents",
        )
        event = UpdateBlock(block_id="block-1", content=content)

        await emitter.emit(event)
        await asyncio.sleep(0.01)

        assert isinstance(consumer.events_received[0], UpdateBlock)
        assert consumer.events_received[0].block_id == "block-1"

    @pytest.mark.asyncio
    async def test_emit_clear_all(self, emitter: EventEmitter) -> None:
        """emit() dispatches ClearAll events."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        event = ClearAll()

        await emitter.emit(event)
        await asyncio.sleep(0.01)

        assert isinstance(consumer.events_received[0], ClearAll)


class TestEmitConcurrency:
    """Tests for concurrent event processing."""

    @pytest.mark.asyncio
    async def test_consumers_process_concurrently(
        self, emitter: EventEmitter
    ) -> None:
        """Multiple consumers process events concurrently."""
        # Two slow consumers that each take 0.1s
        consumer1 = MockConsumer(delay=0.1)
        consumer2 = MockConsumer(delay=0.1)
        emitter.subscribe(consumer1)
        emitter.subscribe(consumer2)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        start_time = asyncio.get_event_loop().time()
        await emitter.emit(event)
        # Wait for both consumers to finish
        await asyncio.sleep(0.15)
        end_time = asyncio.get_event_loop().time()

        # Both consumers should have received the event
        assert len(consumer1.events_received) == 1
        assert len(consumer2.events_received) == 1

        # Total time should be ~0.15s (not 0.25s if sequential)
        # allowing some margin for test timing
        assert end_time - start_time < 0.2


class TestEmitErrorHandling:
    """Tests for error handling in emit()."""

    @pytest.mark.asyncio
    async def test_failing_consumer_does_not_affect_others(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failing consumer does not prevent other consumers from receiving events."""
        good_consumer = MockConsumer()
        failing_consumer = FailingConsumer()
        another_good_consumer = MockConsumer()

        emitter.subscribe(good_consumer)
        emitter.subscribe(failing_consumer)
        emitter.subscribe(another_good_consumer)

        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        with caplog.at_level(logging.DEBUG):
            await emitter.emit(event)
            await asyncio.sleep(0.01)

        # Good consumers should have received the event
        assert len(good_consumer.events_received) == 1
        assert len(another_good_consumer.events_received) == 1

        # Failing consumer was called
        assert failing_consumer.call_count == 1

    @pytest.mark.asyncio
    async def test_emit_logs_failures(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """emit() logs when a consumer fails."""
        failing_consumer = FailingConsumer()
        emitter.subscribe(failing_consumer)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        with caplog.at_level(logging.ERROR):
            await emitter.emit(event)
            await asyncio.sleep(0.01)

        # Should have logged the failure
        assert "event_dispatch_failed" in caplog.text


class TestEmitLogging:
    """Tests for emit() logging."""

    @pytest.mark.asyncio
    async def test_emit_logs_dispatch_started(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """emit() logs when dispatch starts."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        with caplog.at_level(logging.DEBUG):
            await emitter.emit(event)
            await asyncio.sleep(0.01)

        assert "event_dispatch_started" in caplog.text

    @pytest.mark.asyncio
    async def test_emit_logs_dispatch_completed(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """emit() logs when dispatch completes."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        with caplog.at_level(logging.DEBUG):
            await emitter.emit(event)
            await asyncio.sleep(0.01)

        assert "event_dispatch_completed" in caplog.text

    @pytest.mark.asyncio
    async def test_subscribe_logs_subscription(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """subscribe() logs when consumer is added."""
        consumer = MockConsumer()

        with caplog.at_level(logging.DEBUG):
            emitter.subscribe(consumer)

        assert "consumer_subscribed" in caplog.text

    @pytest.mark.asyncio
    async def test_unsubscribe_logs_unsubscription(
        self, emitter: EventEmitter, caplog: pytest.LogCaptureFixture
    ) -> None:
        """unsubscribe() logs when consumer is removed."""
        consumer = MockConsumer()
        emitter.subscribe(consumer)

        with caplog.at_level(logging.DEBUG):
            emitter.unsubscribe(consumer)

        assert "consumer_unsubscribed" in caplog.text
