"""Consumer protocol for event-driven rendering.

This module defines the async Consumer protocol that all consumers must implement.
Consumers process events concurrently and independently via the EventEmitter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .events import Block, Event


@runtime_checkable
class Consumer(Protocol):
    """Protocol for event consumers.

    All consumers implement this async protocol. Sync consumers simply don't
    await internally within their method implementations.

    Consumers are responsible for:
    1. Processing events via on_event()
    2. Rendering blocks to string via render_block()
    """

    async def on_event(self, event: Event) -> None:
        """Process a single event.

        This method is called by the EventEmitter for each event dispatched.
        Implementations should handle AddBlock, UpdateBlock, and ClearAll events.

        Args:
            event: The event to process (AddBlock, UpdateBlock, or ClearAll).
        """
        ...

    def render_block(self, block: Block) -> str:
        """Render a block to its string representation.

        Each consumer implements its own rendering logic for blocks.
        This allows different output formats (markdown, plain text, HTML, etc.).

        Args:
            block: The block to render.

        Returns:
            String representation of the block.
        """
        ...
