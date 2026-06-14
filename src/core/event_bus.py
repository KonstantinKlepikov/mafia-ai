"""Internal event bus for game service events.

This module provides a simple publish-subscribe mechanism for internal
communication between GameService and UI components, replacing RabbitMQ
for local event distribution.
"""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from enum import Enum
from typing import Any

from loguru import logger


class EventType(str, Enum):
    """Types of events published by game service."""

    MESSAGE = 'message'
    VOTE = 'vote'
    ANSWER = 'answer'
    STATE_CHANGE = 'state_change'


EventCallback = Callable[[EventType, Any], None]


class EventBus:
    """Internal event bus for game service events.

    Provides synchronous and asynchronous subscription mechanisms for events
    published by the game service. Used to replace RabbitMQ for internal
    communication between game logic and UI components.

    Example:
        bus = EventBus()

        def on_message(event_type: EventType, data: dict) -> None:
            print(f'Received {event_type}: {data}')

        bus.subscribe(EventType.MESSAGE, on_message)
        bus.publish(EventType.MESSAGE, {'text': 'hello'})
        await bus.publish_async(EventType.MESSAGE, {'text': 'world'})

    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventCallback]] = defaultdict(list)
        self._async_queues: dict[EventType, list[asyncio.Queue[Any]]] = defaultdict(
            list
        )

    def subscribe(self, event_type: EventType, callback: EventCallback) -> None:
        """Subscribe to events of specific type.

        Args:
            event_type: Type of event to subscribe to.
            callback: Callable invoked when event is published.
                      Signature: (event_type: EventType, data: Any) -> None

        """
        self._subscribers[event_type].append(callback)
        logger.debug(f'Subscriber added for {event_type}')

    def unsubscribe(self, event_type: EventType, callback: EventCallback) -> None:
        """Unsubscribe callback from event type.

        Args:
            event_type: Type of event to unsubscribe from.
            callback: Callback to remove.

        """
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f'Subscriber removed for {event_type}')

    def create_queue(self, event_type: EventType) -> asyncio.Queue[Any]:
        """Create async queue for receiving events.

        Args:
            event_type: Type of event to receive.

        Returns:
            Queue that will receive all events of specified type.

        """
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._async_queues[event_type].append(queue)
        logger.debug(f'Queue created for {event_type}')
        return queue

    def remove_queue(self, event_type: EventType, queue: asyncio.Queue[Any]) -> None:
        """Remove async queue from subscriptions.

        Args:
            event_type: Type of event.
            queue: Queue to remove.

        """
        if queue in self._async_queues[event_type]:
            self._async_queues[event_type].remove(queue)
            logger.debug(f'Queue removed for {event_type}')

    def publish(self, event_type: EventType, data: Any) -> None:
        """Publish event synchronously.

        Invokes all registered callbacks immediately in current thread.

        Args:
            event_type: Type of event being published.
            data: Event data (typically dict or Pydantic model).

        """
        logger.debug(f'Publishing {event_type}')

        for callback in self._subscribers[event_type]:
            try:
                callback(event_type, data)
            except Exception as exc:
                logger.error(f'Error in event callback for {event_type}: {exc}')

        for queue in self._async_queues[event_type]:
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                logger.warning(f'Queue full for {event_type}, dropping event')

    async def publish_async(self, event_type: EventType, data: Any) -> None:
        """Publish event asynchronously.

        Invokes all registered callbacks and puts data into queues.
        Callbacks are executed synchronously but this method can be awaited.

        Args:
            event_type: Type of event being published.
            data: Event data (typically dict or Pydantic model).

        """
        self.publish(event_type, data)
        await asyncio.sleep(0)

    def clear_subscribers(self, event_type: EventType | None = None) -> None:
        """Clear all subscribers for event type or all types.

        Args:
            event_type: Type to clear. If None, clear all types.

        """
        if event_type is None:
            self._subscribers.clear()
            self._async_queues.clear()
            logger.debug('All subscribers cleared')
        else:
            self._subscribers[event_type].clear()
            self._async_queues[event_type].clear()
            logger.debug(f'Subscribers cleared for {event_type}')
