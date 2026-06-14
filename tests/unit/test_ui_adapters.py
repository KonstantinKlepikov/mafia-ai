import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from core.event_bus import EventBus, EventType
from core.service import GameService
from shared.models import (
    GamePhase,
    GameState,
    HostDecision,
    HostDecisionAction,
    Message,
    VoteEvent,
)
from ui.event_adapter import EventAdapter
from ui.service_adapter import (
    GameServiceAdapter,
    GameServiceAdapterError,
)


class TestGameServiceAdapter:
    """Test GameServiceAdapter functionality."""

    async def test_start_game_success(self) -> None:
        """Test successful game start."""
        mock_service = AsyncMock(spec=GameService)
        mock_service.begin_game = AsyncMock()

        adapter = GameServiceAdapter(mock_service)
        await adapter.start_game()

        mock_service.begin_game.assert_awaited_once()

    async def test_start_game_error(self) -> None:
        """Test game start error handling."""
        mock_service = AsyncMock(spec=GameService)
        mock_service.begin_game = AsyncMock(side_effect=ValueError('Test error'))

        adapter = GameServiceAdapter(mock_service)

        with pytest.raises(GameServiceAdapterError, match='Test error'):
            await adapter.start_game()

    async def test_get_state(self) -> None:
        """Test getting game state."""
        mock_service = AsyncMock(spec=GameService)
        expected_state = GameState(
            phase=GamePhase.NIGHT,
            round=0,
            alive_agents=[],
            eliminated=[],
        )
        mock_service.get_game_state = Mock(return_value=expected_state)

        adapter = GameServiceAdapter(mock_service)
        state = await adapter.get_state()

        assert state == expected_state
        mock_service.get_game_state.assert_called_once()

    async def test_post_decision(self) -> None:
        """Test posting host decision."""
        mock_service = AsyncMock(spec=GameService)
        mock_service.submit_host_decision = Mock()

        adapter = GameServiceAdapter(mock_service)
        decision = HostDecision(
            action=HostDecisionAction.APPROVE,
            target_id='agent-1',
        )
        await adapter.post_decision(decision)

        mock_service.submit_host_decision.assert_called_once_with(decision)

    async def test_get_agents(self) -> None:
        """Test getting agents list."""
        mock_service = AsyncMock(spec=GameService)
        expected_agents = {'agent-1': 'Citizen', 'agent-2': 'Mafia'}
        mock_service.get_agents_info = AsyncMock(return_value=expected_agents)

        adapter = GameServiceAdapter(mock_service)
        agents = await adapter.get_agents()

        assert agents == expected_agents
        mock_service.get_agents_info.assert_awaited_once()

    async def test_ask_agent_success(self) -> None:
        """Test asking agent successfully."""
        mock_service = AsyncMock(spec=GameService)
        mock_service.ask_agent = AsyncMock(return_value='Test answer')

        adapter = GameServiceAdapter(mock_service)
        await adapter.ask_agent('agent-1', 'Test question?')

        mock_service.ask_agent.assert_awaited_once_with('agent-1', 'Test question?')


class TestEventAdapter:
    """Test EventAdapter functionality."""

    async def test_start_and_stop(self) -> None:
        """Test starting and stopping event adapter."""
        bus = EventBus()
        adapter = EventAdapter(bus)

        await adapter.start()
        await adapter.stop()

        assert True  # No exceptions raised

    async def test_receive_message_event(self) -> None:
        """Test receiving MESSAGE event."""
        bus = EventBus()
        adapter = EventAdapter(bus)

        await adapter.start()

        message = Message(
            sender_id='agent-1',
            agent_id='agent-1',
            round=1,
            phase=GamePhase.DAY,
            content='Test message',
        )

        bus.publish(EventType.MESSAGE, message)

        # Wait for event to be processed
        await asyncio.sleep(0.1)

        events = adapter.get_events()
        await adapter.stop()

        assert len(events) > 0
        # Verify event contains expected data
        assert events[0].raw is not None

    async def test_receive_vote_event(self) -> None:
        """Test receiving VOTE event."""
        bus = EventBus()
        adapter = EventAdapter(bus)

        await adapter.start()

        vote = VoteEvent(
            voter_id='agent-1',
            target_id='agent-2',
            round=1,
            phase=GamePhase.DAY,
        )

        bus.publish(EventType.VOTE, vote)

        await asyncio.sleep(0.1)

        events = adapter.get_events()
        await adapter.stop()

        assert len(events) > 0
        # Verify event contains expected data
        assert events[0].raw is not None

    async def test_get_events_clears_buffer(self) -> None:
        """Test that get_events clears the buffer."""
        bus = EventBus()
        adapter = EventAdapter(bus)

        await adapter.start()

        message = Message(
            sender_id='agent-1',
            agent_id='agent-1',
            round=1,
            phase=GamePhase.DAY,
            content='Test',
        )

        bus.publish(EventType.MESSAGE, message)
        await asyncio.sleep(0.1)

        events1 = adapter.get_events()
        events2 = adapter.get_events()

        await adapter.stop()

        assert len(events1) > 0
        assert len(events2) == 0

    async def test_multiple_events(self) -> None:
        """Test receiving multiple events."""
        bus = EventBus()
        adapter = EventAdapter(bus)

        await adapter.start()

        message = Message(
            sender_id='agent-1',
            agent_id='agent-1',
            round=1,
            phase=GamePhase.DAY,
            content='Message 1',
        )

        vote = VoteEvent(
            voter_id='agent-2',
            target_id='agent-1',
            round=1,
            phase=GamePhase.DAY,
        )

        bus.publish(EventType.MESSAGE, message)
        bus.publish(EventType.VOTE, vote)

        await asyncio.sleep(0.1)

        events = adapter.get_events()
        await adapter.stop()

        assert len(events) >= 2
