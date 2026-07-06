from collections import deque
from dataclasses import dataclass
from enum import Enum

from loguru import logger

from core.event_bus import EventBus, EventType
from schemas import AgentAnswer, Message, VoteEvent


class EventKind(str, Enum):
    """Type of game event."""

    MESSAGE = 'message'
    ANSWER = 'answer'
    VOTE = 'vote'


@dataclass
class FeedEvent:
    """Event for UI consumption."""

    kind: EventKind
    raw: bytes


class Subscriber:
    """Event adapter for admin panel.

    Subscribes to EventBus events and buffers them in memory for UI
    consumption. Replaces AsyncSubscriber with same interface.

    Args:
        event_bus: EventBus instance to subscribe to.
        max_buffer: Maximum number of events to buffer.

    """

    def __init__(self, event_bus: EventBus, max_buffer: int = 500) -> None:
        self._event_bus = event_bus
        self._buffer: deque[FeedEvent] = deque(maxlen=max_buffer)

    async def start(self) -> None:
        """Subscribe to EventBus events."""
        self._event_bus.subscribe(EventType.MESSAGE, self._on_message)
        self._event_bus.subscribe(EventType.ANSWER, self._on_answer)
        self._event_bus.subscribe(EventType.VOTE, self._on_vote)
        logger.info('Subscriber started')

    async def stop(self) -> None:
        """Unsubscribe from EventBus events."""
        self._event_bus.unsubscribe(EventType.MESSAGE, self._on_message)
        self._event_bus.unsubscribe(EventType.ANSWER, self._on_answer)
        self._event_bus.unsubscribe(EventType.VOTE, self._on_vote)
        self._buffer.clear()
        logger.info('Subscriber stopped')

    def _on_message(self, event_type: EventType, data: Message) -> None:
        """Handle MESSAGE events."""
        raw = data.model_dump_json().encode('utf-8')
        self._buffer.append(FeedEvent(kind=EventKind.MESSAGE, raw=raw))

    def _on_answer(self, event_type: EventType, data: AgentAnswer) -> None:
        """Handle ANSWER events."""
        raw = data.model_dump_json().encode('utf-8')
        self._buffer.append(FeedEvent(kind=EventKind.ANSWER, raw=raw))

    def _on_vote(self, event_type: EventType, data: VoteEvent) -> None:
        """Handle VOTE events."""
        raw = data.model_dump_json().encode('utf-8')
        self._buffer.append(FeedEvent(kind=EventKind.VOTE, raw=raw))

    def get_events(self) -> list[FeedEvent]:
        """Return all buffered events and clear buffer.

        Returns:
            List of FeedEvent objects with kind and raw JSON bytes.

        """
        events = list(self._buffer)
        self._buffer.clear()
        return events
