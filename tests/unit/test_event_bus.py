import asyncio

from core.event_bus import EventBus, EventType
from schemas import GamePhase, Message


class TestEventBus:
    """Test EventBus functionality."""

    async def test_subscribe_and_publish(self) -> None:
        """Test basic subscribe and publish workflow."""
        bus = EventBus()
        received_events = []

        def callback(event_type: EventType, data: dict) -> None:
            received_events.append((event_type, data))

        bus.subscribe(EventType.MESSAGE, callback)
        bus.publish(EventType.MESSAGE, {'test': 'data'})

        assert len(received_events) == 1
        assert received_events[0][0] == EventType.MESSAGE
        assert received_events[0][1] == {'test': 'data'}

    async def test_publish_async(self) -> None:
        """Test async publish workflow."""
        bus = EventBus()
        received_events = []

        def callback(event_type: EventType, data: dict) -> None:
            received_events.append((event_type, data))

        bus.subscribe(EventType.MESSAGE, callback)
        await bus.publish_async(EventType.MESSAGE, {'test': 'async'})

        assert len(received_events) == 1
        assert received_events[0][1] == {'test': 'async'}

    async def test_multiple_subscribers(self) -> None:
        """Test multiple subscribers receive same event."""
        bus = EventBus()
        received1 = []
        received2 = []

        def callback1(event_type: EventType, data: dict) -> None:
            received1.append(data)

        def callback2(event_type: EventType, data: dict) -> None:
            received2.append(data)

        bus.subscribe(EventType.MESSAGE, callback1)
        bus.subscribe(EventType.MESSAGE, callback2)
        bus.publish(EventType.MESSAGE, {'test': 'multi'})

        assert len(received1) == 1
        assert len(received2) == 1
        assert received1[0] == received2[0]

    async def test_unsubscribe(self) -> None:
        """Test unsubscribe removes callback."""
        bus = EventBus()
        received = []

        def callback(event_type: EventType, data: dict) -> None:
            received.append(data)

        bus.subscribe(EventType.MESSAGE, callback)
        bus.publish(EventType.MESSAGE, {'test': '1'})

        bus.unsubscribe(EventType.MESSAGE, callback)
        bus.publish(EventType.MESSAGE, {'test': '2'})

        assert len(received) == 1
        assert received[0] == {'test': '1'}

    async def test_queue_subscription(self) -> None:
        """Test async queue subscription."""
        bus = EventBus()
        queue = bus.create_queue(EventType.MESSAGE)

        bus.publish(EventType.MESSAGE, {'test': 'queue'})

        data = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert data == {'test': 'queue'}

        bus.remove_queue(EventType.MESSAGE, queue)

    async def test_event_isolation(self) -> None:
        """Test events are isolated by type."""
        bus = EventBus()
        message_events = []
        vote_events = []

        def message_callback(event_type: EventType, data: dict) -> None:
            message_events.append(data)

        def vote_callback(event_type: EventType, data: dict) -> None:
            vote_events.append(data)

        bus.subscribe(EventType.MESSAGE, message_callback)
        bus.subscribe(EventType.VOTE, vote_callback)

        bus.publish(EventType.MESSAGE, {'type': 'msg'})
        bus.publish(EventType.VOTE, {'type': 'vote'})

        assert len(message_events) == 1
        assert len(vote_events) == 1
        assert message_events[0] == {'type': 'msg'}
        assert vote_events[0] == {'type': 'vote'}

    async def test_clear_subscribers(self) -> None:
        """Test clearing all subscribers."""
        bus = EventBus()
        received = []

        def callback(event_type: EventType, data: dict) -> None:
            received.append(data)

        bus.subscribe(EventType.MESSAGE, callback)
        bus.clear_subscribers(EventType.MESSAGE)
        bus.publish(EventType.MESSAGE, {'test': 'cleared'})

        assert len(received) == 0

    async def test_with_pydantic_models(self) -> None:
        """Test EventBus with Pydantic models."""
        bus = EventBus()
        received = []

        def callback(event_type: EventType, data: Message) -> None:
            received.append(data)

        bus.subscribe(EventType.MESSAGE, callback)

        message = Message(
            sender_id='agent-1',
            agent_id='agent-1',
            round=1,
            phase=GamePhase.DAY,
            content='Test message',
        )

        bus.publish(EventType.MESSAGE, message)

        assert len(received) == 1
        assert received[0].sender_id == 'agent-1'
        assert received[0].content == 'Test message'
