"""Async RabbitMQ subscriber for real-time game events."""

from collections import deque
from dataclasses import dataclass
from enum import Enum

from loguru import logger

from shared.messaging import MessagingClient


class EventKind(str, Enum):
    """Type of game event."""

    MESSAGE = 'message'
    ANSWER = 'answer'
    VOTE = 'vote'


@dataclass
class FeedEvent:
    """Raw RabbitMQ event from game."""

    kind: EventKind
    raw: bytes


class AsyncSubscriber:
    """Async RabbitMQ subscriber for admin panel.

    Subscribes to message.*, host.answer.*, vote.* routing keys
    and buffers events in memory for UI consumption.

    """

    def __init__(self, amqp_url: str, max_buffer: int = 500) -> None:
        self._amqp_url = amqp_url
        self._messaging: MessagingClient | None = None
        self._buffer: deque[FeedEvent] = deque(maxlen=max_buffer)

    async def start(self) -> None:
        """Connect to RabbitMQ and subscribe to game events."""
        if self._messaging is not None:
            logger.warning('AsyncSubscriber already started')
            return

        self._messaging = MessagingClient(self._amqp_url)
        await self._messaging.connect()

        await self._messaging.subscribe('message.*', self._on_message)
        await self._messaging.subscribe('host.answer.*', self._on_answer)
        await self._messaging.subscribe('vote.*', self._on_vote)

        logger.info('AsyncSubscriber started')

    async def stop(self) -> None:
        """Close RabbitMQ connection."""
        if self._messaging is not None:
            await self._messaging.close()
            self._messaging = None
        logger.info('AsyncSubscriber stopped')

    async def _on_message(self, routing_key: str, body: bytes) -> None:
        """Handle message.* events."""
        self._buffer.append(FeedEvent(kind=EventKind.MESSAGE, raw=body))

    async def _on_answer(self, routing_key: str, body: bytes) -> None:
        """Handle host.answer.* events."""
        self._buffer.append(FeedEvent(kind=EventKind.ANSWER, raw=body))

    async def _on_vote(self, routing_key: str, body: bytes) -> None:
        """Handle vote.* events."""
        self._buffer.append(FeedEvent(kind=EventKind.VOTE, raw=body))

    def get_events(self) -> list[FeedEvent]:
        """Return all buffered events and clear buffer."""
        events = list(self._buffer)
        self._buffer.clear()
        return events
