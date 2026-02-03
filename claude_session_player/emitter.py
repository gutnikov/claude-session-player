"""Event emitter for dispatching events to multiple consumers.

This module provides the EventEmitter class that dispatches events to
consumers via asyncio.create_task() for concurrent, fire-and-forget processing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .events import Event
    from .protocol import Consumer

logger = logging.getLogger(__name__)


class EventEmitter:
    """Dispatches events to multiple consumers concurrently.

    Events are dispatched via asyncio.create_task() (fire-and-forget).
    The emitter does not wait for consumer callbacks to complete.
    Multiple consumers can subscribe to a single event emitter.
    Consumers process events concurrently and independently.

    Example:
        emitter = EventEmitter()
        emitter.subscribe(markdown_consumer)
        emitter.subscribe(streaming_consumer)

        # Events are dispatched to all consumers concurrently
        await emitter.emit(AddBlock(block=some_block))
    """

    def __init__(self) -> None:
        """Initialize the event emitter with an empty subscriber list."""
        self._consumers: list[Consumer] = []

    def subscribe(self, consumer: Consumer) -> None:
        """Subscribe a consumer to receive events.

        Args:
            consumer: A consumer implementing the Consumer protocol.
        """
        self._consumers.append(consumer)
        logger.debug(
            "consumer_subscribed",
            extra={
                "consumer_type": type(consumer).__name__,
                "total_subscribers": len(self._consumers),
            },
        )

    def unsubscribe(self, consumer: Consumer) -> None:
        """Unsubscribe a consumer from receiving events.

        Args:
            consumer: The consumer to remove.

        Raises:
            ValueError: If the consumer is not subscribed.
        """
        self._consumers.remove(consumer)
        logger.debug(
            "consumer_unsubscribed",
            extra={
                "consumer_type": type(consumer).__name__,
                "total_subscribers": len(self._consumers),
            },
        )

    @property
    def subscriber_count(self) -> int:
        """Return the number of subscribed consumers."""
        return len(self._consumers)

    async def emit(self, event: Event) -> None:
        """Dispatch an event to all subscribed consumers.

        Events are dispatched via asyncio.create_task() for fire-and-forget
        execution. This method returns immediately without waiting for
        consumers to finish processing.

        Args:
            event: The event to dispatch to all consumers.
        """
        event_type = type(event).__name__
        consumer_count = len(self._consumers)

        logger.debug(
            "event_dispatch_started",
            extra={
                "event_type": event_type,
                "consumer_count": consumer_count,
            },
        )

        for consumer in self._consumers:
            task = asyncio.create_task(
                self._dispatch_to_consumer(consumer, event),
                name=f"dispatch_{event_type}_to_{type(consumer).__name__}",
            )
            # Fire-and-forget: we don't await the task
            task.add_done_callback(self._handle_task_completion)

    async def _dispatch_to_consumer(self, consumer: Consumer, event: Event) -> None:
        """Dispatch a single event to a single consumer.

        This wrapper handles exceptions from consumer callbacks.

        Args:
            consumer: The consumer to dispatch to.
            event: The event to dispatch.
        """
        consumer_type = type(consumer).__name__
        event_type = type(event).__name__

        try:
            await consumer.on_event(event)
            logger.debug(
                "event_dispatch_completed",
                extra={
                    "event_type": event_type,
                    "consumer_type": consumer_type,
                },
            )
        except Exception:
            logger.exception(
                "event_dispatch_failed",
                extra={
                    "event_type": event_type,
                    "consumer_type": consumer_type,
                },
            )

    def _handle_task_completion(self, task: asyncio.Task) -> None:
        """Handle task completion for logging purposes.

        This callback is attached to fire-and-forget tasks to ensure
        any unhandled exceptions are logged.

        Args:
            task: The completed task.
        """
        if task.cancelled():
            logger.debug(
                "dispatch_task_cancelled",
                extra={"task_name": task.get_name()},
            )
        elif task.exception() is not None:
            # Exception was already logged in _dispatch_to_consumer,
            # but we log here too in case the exception happened elsewhere
            logger.debug(
                "dispatch_task_exception",
                extra={
                    "task_name": task.get_name(),
                    "exception": str(task.exception()),
                },
            )
