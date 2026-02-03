"""Tests for the Consumer protocol."""

from __future__ import annotations

import pytest

from claude_session_player.events import (
    AddBlock,
    AssistantContent,
    Block,
    BlockType,
    ClearAll,
    Event,
    UpdateBlock,
    UserContent,
)
from claude_session_player.protocol import Consumer


# ---------------------------------------------------------------------------
# Test Consumer protocol implementation
# ---------------------------------------------------------------------------


class MockConsumer:
    """A mock consumer that implements the Consumer protocol."""

    def __init__(self) -> None:
        self.events_received: list[Event] = []
        self.blocks_rendered: list[Block] = []

    async def on_event(self, event: Event) -> None:
        """Record received events."""
        self.events_received.append(event)

    def render_block(self, block: Block) -> str:
        """Record rendered blocks and return simple string."""
        self.blocks_rendered.append(block)
        return f"[{block.type.value}:{block.id}]"


class SyncConsumer:
    """A consumer that doesn't await internally (sync-style)."""

    def __init__(self) -> None:
        self.events_received: list[Event] = []

    async def on_event(self, event: Event) -> None:
        """Process event synchronously (no await)."""
        # Sync processing - no await needed
        self.events_received.append(event)

    def render_block(self, block: Block) -> str:
        """Render block synchronously."""
        return f"sync:{block.id}"


class TestConsumerProtocol:
    """Tests for Consumer protocol compliance."""

    def test_mock_consumer_is_consumer(self) -> None:
        """MockConsumer implements Consumer protocol."""
        consumer = MockConsumer()
        assert isinstance(consumer, Consumer)

    def test_sync_consumer_is_consumer(self) -> None:
        """SyncConsumer implements Consumer protocol."""
        consumer = SyncConsumer()
        assert isinstance(consumer, Consumer)

    def test_non_consumer_is_not_consumer(self) -> None:
        """Objects without required methods are not Consumers."""

        class NotAConsumer:
            pass

        obj = NotAConsumer()
        assert not isinstance(obj, Consumer)

    def test_partial_consumer_is_not_consumer(self) -> None:
        """Objects with only some methods are not Consumers."""

        class PartialConsumer:
            async def on_event(self, event: Event) -> None:
                pass

            # Missing render_block

        obj = PartialConsumer()
        assert not isinstance(obj, Consumer)


class TestMockConsumerOnEvent:
    """Tests for on_event() method."""

    @pytest.mark.asyncio
    async def test_on_event_receives_add_block(self) -> None:
        """on_event receives AddBlock events."""
        consumer = MockConsumer()
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        event = AddBlock(block=block)

        await consumer.on_event(event)

        assert len(consumer.events_received) == 1
        assert consumer.events_received[0] is event

    @pytest.mark.asyncio
    async def test_on_event_receives_update_block(self) -> None:
        """on_event receives UpdateBlock events."""
        consumer = MockConsumer()
        content = AssistantContent(text="Updated text")
        event = UpdateBlock(block_id="block-1", content=content)

        await consumer.on_event(event)

        assert len(consumer.events_received) == 1
        assert consumer.events_received[0] is event

    @pytest.mark.asyncio
    async def test_on_event_receives_clear_all(self) -> None:
        """on_event receives ClearAll events."""
        consumer = MockConsumer()
        event = ClearAll()

        await consumer.on_event(event)

        assert len(consumer.events_received) == 1
        assert isinstance(consumer.events_received[0], ClearAll)

    @pytest.mark.asyncio
    async def test_on_event_receives_multiple_events(self) -> None:
        """on_event can receive multiple events in sequence."""
        consumer = MockConsumer()
        block1 = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="First"),
        )
        block2 = Block(
            id="block-2",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Second"),
        )

        await consumer.on_event(AddBlock(block=block1))
        await consumer.on_event(AddBlock(block=block2))
        await consumer.on_event(ClearAll())

        assert len(consumer.events_received) == 3


class TestMockConsumerRenderBlock:
    """Tests for render_block() method."""

    def test_render_block_returns_string(self) -> None:
        """render_block returns a string."""
        consumer = MockConsumer()
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )

        result = consumer.render_block(block)

        assert isinstance(result, str)
        assert result == "[user:block-1]"

    def test_render_block_records_block(self) -> None:
        """render_block records the block it rendered."""
        consumer = MockConsumer()
        block = Block(
            id="block-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Response"),
        )

        consumer.render_block(block)

        assert len(consumer.blocks_rendered) == 1
        assert consumer.blocks_rendered[0] is block

    def test_render_block_handles_different_block_types(self) -> None:
        """render_block handles different block types."""
        consumer = MockConsumer()

        user_block = Block(
            id="user-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )
        assistant_block = Block(
            id="assistant-1",
            type=BlockType.ASSISTANT,
            content=AssistantContent(text="Hi"),
        )

        user_result = consumer.render_block(user_block)
        assistant_result = consumer.render_block(assistant_block)

        assert user_result == "[user:user-1]"
        assert assistant_result == "[assistant:assistant-1]"


class TestSyncConsumer:
    """Tests for sync-style consumer."""

    @pytest.mark.asyncio
    async def test_sync_consumer_on_event(self) -> None:
        """Sync consumer works without internal awaits."""
        consumer = SyncConsumer()
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )

        await consumer.on_event(AddBlock(block=block))

        assert len(consumer.events_received) == 1

    def test_sync_consumer_render_block(self) -> None:
        """Sync consumer render_block works."""
        consumer = SyncConsumer()
        block = Block(
            id="block-1",
            type=BlockType.USER,
            content=UserContent(text="Hello"),
        )

        result = consumer.render_block(block)

        assert result == "sync:block-1"
